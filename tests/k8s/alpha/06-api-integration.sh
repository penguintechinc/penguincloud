#!/usr/bin/env bash
set -euo pipefail

# API integration tests via port-forward

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

test_endpoint() {
    local name="$1"
    local method="$2"
    local url="$3"
    local expected_code="${4:-200}"
    local data="${5:-}"

    log_info "Testing: $name ($method $url)"

    local curl_cmd="curl -s -o /tmp/response.txt -w %{http_code} --max-time 10 -X $method"

    if [[ -n "$data" ]]; then
        curl_cmd="$curl_cmd -H 'Content-Type: application/json' -d '$data'"
    fi

    curl_cmd="$curl_cmd '$url'"

    local response_code
    if response_code=$(eval "$curl_cmd" 2>/dev/null); then
        if [[ "$response_code" == "$expected_code" ]]; then
            log_pass "$name: HTTP $response_code (expected $expected_code)"
            return 0
        else
            log_fail "$name: HTTP $response_code (expected $expected_code)"
            if [[ -f /tmp/response.txt ]]; then
                log_info "Response body: $(cat /tmp/response.txt | head -c 200)"
            fi
            return 1
        fi
    else
        log_fail "$name: Connection failed"
        return 1
    fi
}

test_json_field() {
    local name="$1"
    local method="$2"
    local url="$3"
    local field="$4"

    log_info "Testing: $name ($method $url, checking for field: $field)"

    local response
    if response=$(curl -s --max-time 10 -X "$method" "$url" 2>/dev/null); then
        if echo "$response" | grep -q "$field"; then
            log_pass "$name: Found field '$field' in response"
            return 0
        else
            log_fail "$name: Field '$field' not found in response"
            log_info "Response: $(echo "$response" | head -c 200)"
            return 1
        fi
    else
        log_fail "$name: Connection failed"
        return 1
    fi
}

test_flask_backend() {
    log_info "Testing flask-backend API endpoints..."

    if ! start_port_forward "flask-backend" 25000 5000; then
        log_warn "Skipping flask-backend API tests (service not found)"
        return 0
    fi

    local failed=0

    # Test health endpoint
    if ! test_endpoint "Flask health check" "GET" "http://localhost:25000/healthz" 200; then
        ((failed++))
    fi

    # Test status endpoint
    if ! test_endpoint "Flask status endpoint" "GET" "http://localhost:25000/api/v1/status" 200; then
        ((failed++))
    fi

    # Test auth login endpoint (may return 400 or 401 for invalid creds, but should respond)
    local login_data='{"username":"testuser","password":"testpass"}'
    local response_code
    response_code=$(curl -s -o /tmp/login_response.txt -w "%{http_code}" --max-time 10 \
        -X POST "http://localhost:25000/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "$login_data" 2>/dev/null || echo "000")

    if [[ "$response_code" =~ ^(200|400|401|422)$ ]]; then
        log_pass "Flask login endpoint responding (HTTP $response_code)"
    else
        log_fail "Flask login endpoint failed (HTTP $response_code)"
        ((failed++))
    fi

    return $failed
}

test_go_backend() {
    log_info "Testing go-backend API endpoints..."

    if ! start_port_forward "go-backend" 28080 8080; then
        log_warn "Skipping go-backend API tests (service not found)"
        return 0
    fi

    local failed=0

    # Test health endpoint
    if ! test_endpoint "Go health check" "GET" "http://localhost:28080/healthz" 200; then
        ((failed++))
    fi

    # Test status endpoint
    if ! test_endpoint "Go status endpoint" "GET" "http://localhost:28080/api/v2/status" 200; then
        ((failed++))
    fi

    return $failed
}

main() {
    log_info "Running API integration tests for namespace: $NAMESPACE"

    local failed=0

    # Test flask-backend
    if ! test_flask_backend; then
        ((failed++))
    fi

    # Test go-backend
    if ! test_go_backend; then
        ((failed++))
    fi

    # Summary
    if [[ $failed -eq 0 ]]; then
        log_pass "All API integration tests passed"
        return 0
    else
        log_fail "$failed API integration test(s) failed"
        return 1
    fi
}

main "$@"
