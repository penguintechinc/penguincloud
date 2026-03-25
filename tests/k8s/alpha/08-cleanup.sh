#!/usr/bin/env bash
set -euo pipefail

# Cleanup alpha environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_NAME="$(basename "$REPO_ROOT")"
NAMESPACE="${PROJECT_NAME}-alpha"
RELEASE_NAME="$PROJECT_NAME"

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

cleanup_port_forwards() {
    log_info "Cleaning up any remaining port-forward processes..."

    # Kill any kubectl port-forward processes for this namespace
    local pids=$(pgrep -f "kubectl port-forward.*$NAMESPACE" || echo "")

    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs -r kill 2>/dev/null || true
        log_info "Killed port-forward processes: $pids"
    else
        log_info "No port-forward processes found"
    fi
}

uninstall_helm_release() {
    log_info "Uninstalling Helm release: $RELEASE_NAME"

    # Check if release exists
    if ! helm list -n "$NAMESPACE" 2>/dev/null | grep -q "$RELEASE_NAME"; then
        log_info "Helm release $RELEASE_NAME not found in namespace $NAMESPACE"
        return 0
    fi

    # Uninstall
    if helm uninstall "$RELEASE_NAME" -n "$NAMESPACE"; then
        log_pass "Helm release uninstalled"
    else
        log_warn "Failed to uninstall Helm release (may already be gone)"
    fi

    # Wait for pods to terminate
    log_info "Waiting for pods to terminate..."
    local max_wait=60
    local waited=0

    while kubectl get pods -n "$NAMESPACE" 2>/dev/null | grep -qv "^NAME"; do
        if [[ $waited -ge $max_wait ]]; then
            log_warn "Some pods still exist after ${max_wait}s"
            kubectl get pods -n "$NAMESPACE"
            break
        fi
        sleep 2
        ((waited+=2))
    done

    log_pass "Pods terminated"
}

delete_namespace() {
    log_info "Deleting namespace: $NAMESPACE"

    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        log_info "Namespace $NAMESPACE does not exist"
        return 0
    fi

    # Delete namespace
    if kubectl delete namespace "$NAMESPACE" --timeout=60s; then
        log_pass "Namespace deleted"
    else
        log_warn "Failed to delete namespace gracefully, forcing..."
        kubectl delete namespace "$NAMESPACE" --grace-period=0 --force 2>/dev/null || true
    fi
}

cleanup_docker_images() {
    log_info "Optionally cleaning up Docker images..."

    # List images (but don't delete them automatically)
    local images=$(docker images | grep "${PROJECT_NAME}.*alpha" || echo "")

    if [[ -n "$images" ]]; then
        log_info "Found alpha images (not deleting automatically):"
        echo "$images"
        log_info "To clean up images manually, run: docker rmi ${PROJECT_NAME}/flask-backend:alpha ${PROJECT_NAME}/go-backend:alpha ${PROJECT_NAME}/webui:alpha"
    else
        log_info "No alpha Docker images found"
    fi
}

main() {
    log_info "Cleaning up alpha environment for $PROJECT_NAME"

    # Cleanup in order
    cleanup_port_forwards
    uninstall_helm_release
    delete_namespace
    cleanup_docker_images

    log_pass "Alpha environment cleanup completed"
    log_info "Namespace $NAMESPACE has been removed"
}

main "$@"
