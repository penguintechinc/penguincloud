#!/usr/bin/env bash
set -euo pipefail

# Run unit tests inside pods

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

get_pod_for_service() {
    local service="$1"
    local pod

    pod=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -z "$pod" ]]; then
        # Try alternative label
        pod=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi

    echo "$pod"
}

run_flask_tests() {
    log_info "Running Python unit tests for flask-backend..."

    local pod=$(get_pod_for_service "flask-backend")
    if [[ -z "$pod" ]]; then
        log_warn "No pod found for flask-backend, skipping tests"
        return 0
    fi

    log_info "Found pod: $pod"

    # Check if tests directory exists
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- test -d tests 2>/dev/null; then
        log_warn "No tests directory found in flask-backend, skipping"
        return 0
    fi

    # Check if pytest is installed
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- which pytest &>/dev/null; then
        log_warn "pytest not found in flask-backend, skipping"
        return 0
    fi

    # Run pytest
    if kubectl exec -n "$NAMESPACE" "$pod" -- python -m pytest tests/ -x --tb=short; then
        log_pass "Flask-backend unit tests passed"
        return 0
    else
        log_fail "Flask-backend unit tests failed"
        return 1
    fi
}

run_go_tests() {
    log_info "Running Go unit tests for go-backend..."

    local pod=$(get_pod_for_service "go-backend")
    if [[ -z "$pod" ]]; then
        log_warn "No pod found for go-backend, skipping tests"
        return 0
    fi

    log_info "Found pod: $pod"

    # Check if Go is available
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- which go &>/dev/null; then
        log_warn "Go not found in go-backend pod, skipping tests"
        return 0
    fi

    # Check if any test files exist
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- sh -c 'find . -name "*_test.go" | head -1' 2>/dev/null | grep -q "_test.go"; then
        log_warn "No Go test files found in go-backend, skipping"
        return 0
    fi

    # Run go test
    if kubectl exec -n "$NAMESPACE" "$pod" -- go test ./... -short; then
        log_pass "Go-backend unit tests passed"
        return 0
    else
        log_fail "Go-backend unit tests failed"
        return 1
    fi
}

run_node_tests() {
    log_info "Running Node.js unit tests for webui..."

    local pod=$(get_pod_for_service "webui")
    if [[ -z "$pod" ]]; then
        log_warn "No pod found for webui, skipping tests"
        return 0
    fi

    log_info "Found pod: $pod"

    # Check if npm is available
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- which npm &>/dev/null; then
        log_warn "npm not found in webui pod, skipping tests"
        return 0
    fi

    # Check if test script exists in package.json
    if ! kubectl exec -n "$NAMESPACE" "$pod" -- sh -c 'test -f package.json && grep -q "\"test\"" package.json' 2>/dev/null; then
        log_warn "No test script found in package.json, skipping"
        return 0
    fi

    # Run npm test
    if kubectl exec -n "$NAMESPACE" "$pod" -- npm test -- --watchAll=false --passWithNoTests; then
        log_pass "Webui unit tests passed"
        return 0
    else
        log_fail "Webui unit tests failed"
        return 1
    fi
}

main() {
    log_info "Running unit tests for all services in namespace: $NAMESPACE"

    local failed=0

    # Run tests for each service
    if ! run_flask_tests; then
        ((failed++))
    fi

    if ! run_go_tests; then
        ((failed++))
    fi

    if ! run_node_tests; then
        ((failed++))
    fi

    # Summary
    if [[ $failed -eq 0 ]]; then
        log_pass "All unit tests passed or skipped gracefully"
        return 0
    else
        log_fail "$failed unit test suite(s) failed"
        return 1
    fi
}

main "$@"
