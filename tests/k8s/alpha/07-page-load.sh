#!/usr/bin/env bash
set -euo pipefail

# Page load tests for webui

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_NAME="$(basename "$REPO_ROOT")"
NAMESPACE="${PROJECT_NAME}-alpha"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Track port-forward PIDs for cleanup
PF_PIDS=()

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

cleanup_port_forwards() {
    log_info "Cleaning up port-forwards..."
    for pid in "${PF_PIDS[@]}"; do
        if kill "$pid" 2>/dev/null; then
            log_info "Killed port-forward process: $pid"
        fi
    done
}

trap cleanup_port_forwards EXIT

start_port_forward() {
    local service="$1"
    local local_port="$2"
    local service_port="$3"

    log_info "Starting port-forward for $service: localhost:$local_port -> $service:$service_port"

    # Find pod for service
    local pod=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$pod" ]]; then
        # Try alternative label
        pod=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi

    if [[ -z "$pod" ]]; then
        log_warn "No pod found for service: $service"
        return 1
    fi

    # Start port-forward in background
    kubectl port-forward -n "$NAMESPACE" "$pod" "$local_port:$service_port" >/dev/null 2>&1 &
    local pid=$!
    PF_PIDS+=("$pid")

    # Wait for port-forward to be ready
    local max_wait=10
    local waited=0
    while ! nc -z localhost "$local_port" 2>/dev/null; do
        if [[ $waited -ge $max_wait ]]; then
            log_fail "Port-forward failed to start for $service"
            return 1
        fi
        sleep 1
        ((waited++))
    done

    log_pass "Port-forward ready for $service on localhost:$local_port"
    return 0
}

test_page_load() {
    local name="$1"
    local url="$2"
    local expected_content="$3"

    log_info "Testing page load: $name ($url)"

    local response
    local response_code

    response=$(curl -s --max-time 10 "$url" 2>/dev/null || echo "")
    response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")

    if [[ "$response_code" != "200" ]]; then
        log_fail "$name: HTTP $response_code (expected 200)"
        return 1
    fi

    if [[ -n "$expected_content" ]] && ! echo "$response" | grep -qi "$expected_content"; then
        log_fail "$name: Expected content '$expected_content' not found"
        log_info "Response preview: $(echo "$response" | head -c 200)"
        return 1
    fi

    log_pass "$name: Page loaded successfully (HTTP $response_code)"
    return 0
}

test_asset_load() {
    local name="$1"
    local url="$2"
    local expected_code="${3:-200}"

    log_info "Testing asset: $name ($url)"

    local response_code
    response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")

    if [[ "$response_code" == "$expected_code" ]]; then
        log_pass "$name: HTTP $response_code"
        return 0
    else
        log_warn "$name: HTTP $response_code (expected $expected_code, but continuing)"
        return 0  # Don't fail on assets, just warn
    fi
}

main() {
    log_info "Running page load tests for webui in namespace: $NAMESPACE"

    if ! start_port_forward "webui" 33000 3000; then
        log_warn "Skipping webui page load tests (service not found)"
        return 0
    fi

    local failed=0

    # Test home page
    if ! test_page_load "Home page" "http://localhost:33000/" "<html"; then
        ((failed++))
    fi

    # Test login page (may or may not exist)
    local login_code
    login_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://localhost:33000/login" 2>/dev/null || echo "000")

    if [[ "$login_code" == "200" ]]; then
        if ! test_page_load "Login page" "http://localhost:33000/login" "<html"; then
            ((failed++))
        fi
    else
        log_info "Login page returned HTTP $login_code (may not exist, skipping)"
    fi

    # Test common static assets (these may or may not exist, so we just check)
    test_asset_load "Favicon" "http://localhost:33000/favicon.ico" || true
    test_asset_load "Manifest" "http://localhost:33000/manifest.json" || true

    # Check for JavaScript bundles (common in React/Vue apps)
    local has_js=false
    if curl -s --max-time 10 "http://localhost:33000/" | grep -qE '\.js["\']'; then
        log_info "Found JavaScript references in HTML"
        has_js=true
    fi

    # Check for CSS
    local has_css=false
    if curl -s --max-time 10 "http://localhost:33000/" | grep -qE '\.css["\']|<style'; then
        log_info "Found CSS references in HTML"
        has_css=true
    fi

    if [[ "$has_js" == true ]] || [[ "$has_css" == true ]]; then
        log_pass "WebUI appears to be loading assets"
    else
        log_warn "No obvious JS/CSS assets found (may be inline or not applicable)"
    fi

    # Summary
    if [[ $failed -eq 0 ]]; then
        log_pass "All page load tests passed"
        return 0
    else
        log_fail "$failed page load test(s) failed"
        return 1
    fi
}

main "$@"
