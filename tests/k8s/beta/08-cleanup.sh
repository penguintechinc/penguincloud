#!/usr/bin/env bash
set -euo pipefail

# 08-cleanup.sh - Cleanup beta environment resources

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

# Configuration
PROJECT_NAME="${PROJECT_NAME:-project-template}"
NAMESPACE="${PROJECT_NAME}-beta"
RELEASE_NAME="${PROJECT_NAME}"

log_info "Cleaning up beta environment resources"
log_info "Namespace: ${NAMESPACE}"
log_info "Release: ${RELEASE_NAME}"

# Kill any lingering port-forwards
log_info "Killing any lingering port-forward processes..."
PORT_FORWARD_PIDS=$(pgrep -f "kubectl port-forward.*${NAMESPACE}" || echo "")

if [[ -n "$PORT_FORWARD_PIDS" ]]; then
    log_info "Found port-forward processes: ${PORT_FORWARD_PIDS}"
    for pid in $PORT_FORWARD_PIDS; do
        if kill "$pid" 2>/dev/null; then
            log_pass "Killed port-forward process: ${pid}"
        else
            log_warn "Could not kill process: ${pid}"
        fi
    done
else
    log_info "No port-forward processes found"
fi

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_warn "Namespace ${NAMESPACE} does not exist, nothing to clean up"
    exit 0
fi

# Uninstall Helm release
log_info "Uninstalling Helm release: ${RELEASE_NAME}"
if helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
    if helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" --wait --timeout 5m; then
        log_pass "Helm release uninstalled successfully"
    else
        log_fail "Failed to uninstall Helm release"
        log_info "Attempting to force cleanup..."
        helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" --no-hooks || true
    fi
else
    log_warn "Helm release ${RELEASE_NAME} not found in namespace ${NAMESPACE}"
fi

# Wait for pods to terminate
log_info "Waiting for pods to terminate..."
TIMEOUT=60
ELAPSED=0

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

    if [[ $POD_COUNT -eq 0 ]]; then
        log_pass "All pods terminated"
        break
    fi

    log_info "Waiting for ${POD_COUNT} pod(s) to terminate... (${ELAPSED}s/${TIMEOUT}s)"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
    log_warn "Timeout waiting for pods to terminate"
    log_info "Remaining pods:"
    kubectl get pods -n "$NAMESPACE" || true

    log_info "Force deleting remaining pods..."
    kubectl delete pods --all -n "$NAMESPACE" --force --grace-period=0 || true
fi

# Delete PVCs (persistent volume claims)
log_info "Checking for PVCs..."
PVC_COUNT=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

if [[ $PVC_COUNT -gt 0 ]]; then
    log_info "Found ${PVC_COUNT} PVC(s), deleting..."
    kubectl get pvc -n "$NAMESPACE"

    if kubectl delete pvc --all -n "$NAMESPACE" --timeout=60s; then
        log_pass "PVCs deleted successfully"
    else
        log_warn "Failed to delete some PVCs"
        kubectl get pvc -n "$NAMESPACE" || true
    fi
else
    log_info "No PVCs found"
fi

# Delete any remaining resources
log_info "Checking for remaining resources..."
REMAINING_RESOURCES=$(kubectl get all -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

if [[ $REMAINING_RESOURCES -gt 0 ]]; then
    log_warn "Found ${REMAINING_RESOURCES} remaining resource(s)"
    kubectl get all -n "$NAMESPACE" || true

    log_info "Deleting all remaining resources..."
    kubectl delete all --all -n "$NAMESPACE" --timeout=60s || true
fi

# Delete ConfigMaps
log_info "Deleting ConfigMaps..."
kubectl delete configmaps --all -n "$NAMESPACE" --ignore-not-found=true || true

# Delete Secrets (excluding default service account tokens)
log_info "Deleting Secrets..."
kubectl delete secrets --all -n "$NAMESPACE" --ignore-not-found=true --field-selector type!=kubernetes.io/service-account-token || true

# Delete NetworkPolicies
log_info "Deleting NetworkPolicies..."
kubectl delete networkpolicies --all -n "$NAMESPACE" --ignore-not-found=true || true

# Delete ServiceAccounts (excluding default)
log_info "Deleting ServiceAccounts..."
kubectl get serviceaccounts -n "$NAMESPACE" --no-headers | grep -v "^default " | awk '{print $1}' | xargs -r kubectl delete serviceaccount -n "$NAMESPACE" || true

# Delete RoleBindings and Roles
log_info "Deleting RoleBindings and Roles..."
kubectl delete rolebindings --all -n "$NAMESPACE" --ignore-not-found=true || true
kubectl delete roles --all -n "$NAMESPACE" --ignore-not-found=true || true

# Final check
log_info "Final resource check..."
FINAL_RESOURCES=$(kubectl get all,configmaps,secrets,networkpolicies,pvc -n "$NAMESPACE" --no-headers 2>/dev/null | grep -v "^service/kubernetes" | wc -l)

if [[ $FINAL_RESOURCES -gt 0 ]]; then
    log_warn "Still ${FINAL_RESOURCES} resource(s) remaining:"
    kubectl get all,configmaps,secrets,networkpolicies,pvc -n "$NAMESPACE" || true
fi

# Delete namespace
log_info "Deleting namespace: ${NAMESPACE}"
if kubectl delete namespace "$NAMESPACE" --timeout=120s; then
    log_pass "Namespace deleted successfully"
else
    log_fail "Failed to delete namespace"
    log_info "Checking namespace status..."
    kubectl get namespace "$NAMESPACE" -o yaml || true

    # Try to force cleanup
    log_warn "Attempting to force delete namespace..."
    kubectl delete namespace "$NAMESPACE" --force --grace-period=0 || true
fi

# Verify namespace is gone
sleep 2
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_fail "Namespace still exists after deletion attempt"
    log_info "Namespace may be stuck in 'Terminating' state"
    log_info "You may need to manually remove finalizers"
    exit 1
else
    log_pass "Namespace successfully removed"
fi

log_pass "Cleanup completed successfully"
exit 0
