#!/usr/bin/env bash
set -euo pipefail

# Health check for all services via port-forward

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

health_check() {
    local service="$1"
    local port="$2"
    local health_path="${3:-/healthz}"

    log_info "Health check: $service on port $port ($health_path)"

    local url="http://localhost:$port$health_path"
    local response_code

    if response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null); then
        if [[ "$response_code" == "200" ]]; then
            log_pass "$service health check passed (HTTP $response_code)"
            return 0
        else
            log_fail "$service health check failed (HTTP $response_code)"
            return 1
        fi
    else
        log_fail "$service health check failed (connection error)"
        return 1
    fi
}

main() {
    log_info "Running health checks for all services in namespace: $NAMESPACE"

    local failed=0

    # Health check: flask-backend
    if start_port_forward "flask-backend" 15000 5000; then
        if ! health_check "flask-backend" 15000 "/healthz"; then
            ((failed++))
        fi
    else
        log_warn "Skipping flask-backend health check (service not found)"
    fi

    # Health check: go-backend
    if start_port_forward "go-backend" 18080 8080; then
        if ! health_check "go-backend" 18080 "/healthz"; then
            ((failed++))
        fi
    else
        log_warn "Skipping go-backend health check (service not found)"
    fi

    # Health check: webui
    if start_port_forward "webui" 13000 3000; then
        if ! health_check "webui" 13000 "/healthz"; then
            ((failed++))
        fi
    else
        log_warn "Skipping webui health check (service not found)"
    fi

    # Summary
    if [[ $failed -eq 0 ]]; then
        log_pass "All health checks passed"
        return 0
    else
        log_fail "$failed health check(s) failed"
        return 1
    fi
}

main "$@"
