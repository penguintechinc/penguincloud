#!/usr/bin/env bash
set -euo pipefail

# Wait for all pods to be ready

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_NAME="$(basename "$REPO_ROOT")"
NAMESPACE="${PROJECT_NAME}-alpha"
TIMEOUT=300

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

check_pod_exists() {
    local pod_pattern="$1"
    if kubectl get pods -n "$NAMESPACE" 2>/dev/null | grep -q "$pod_pattern"; then
        return 0
    else
        return 1
    fi
}

main() {
    log_info "Waiting for pods to be ready in namespace: $NAMESPACE"
    log_info "Timeout: ${TIMEOUT}s"

    # Verify namespace exists
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        log_fail "Namespace $NAMESPACE does not exist"
        exit 1
    fi

    # Show current pod status
    log_info "Current pod status:"
    kubectl get pods -n "$NAMESPACE"

    # Check that expected pods exist
    log_info "Checking for expected service pods..."
    local expected_pods=("flask-backend" "go-backend" "webui")
    local missing_pods=()

    for pod in "${expected_pods[@]}"; do
        if check_pod_exists "$pod"; then
            log_pass "Found pod matching: $pod"
        else
            log_warn "No pod found matching: $pod"
            missing_pods+=("$pod")
        fi
    done

    # Wait for all pods to be ready
    log_info "Waiting for all pods to be ready..."
    if kubectl wait --for=condition=ready pods --all \
        -n "$NAMESPACE" \
        --timeout="${TIMEOUT}s"; then
        log_pass "All pods are ready"
    else
        log_fail "Pods did not become ready within ${TIMEOUT}s"
        log_info "Final pod status:"
        kubectl get pods -n "$NAMESPACE"
        log_info "Describing failed pods:"
        kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name | \
            xargs -r -I {} kubectl describe {} -n "$NAMESPACE"
        exit 1
    fi

    # Final status check
    log_info "Final pod status:"
    kubectl get pods -n "$NAMESPACE"

    # Count running pods
    local total_pods=$(kubectl get pods -n "$NAMESPACE" --no-headers | wc -l)
    local running_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers | wc -l)

    log_info "Running pods: $running_pods/$total_pods"

    if [[ ${#missing_pods[@]} -gt 0 ]]; then
        log_warn "Some expected pods were not found: ${missing_pods[*]}"
        log_warn "This may be expected if services are disabled in alpha environment"
    fi

    log_pass "Pod readiness check completed"
}

main "$@"
