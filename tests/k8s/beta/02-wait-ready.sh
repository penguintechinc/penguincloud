#!/usr/bin/env bash
set -euo pipefail

# 02-wait-ready.sh - Wait for all pods to be ready

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
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

# Configuration
PROJECT_NAME="${PROJECT_NAME:-project-template}"
NAMESPACE="${PROJECT_NAME}-beta"
TIMEOUT=300

log_info "Waiting for all pods to be ready in namespace: ${NAMESPACE}"
log_info "Timeout: ${TIMEOUT}s"

# Verify namespace exists
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_fail "Namespace does not exist: ${NAMESPACE}"
    exit 1
fi

# Expected services/deployments
EXPECTED_SERVICES=(
    "flask-backend"
    "go-backend"
    "webui"
    "postgresql"
    "redis-master"
)

log_info "Expected services: ${EXPECTED_SERVICES[*]}"

# Check if any pods exist
log_info "Checking for pods in namespace..."
POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

if [[ $POD_COUNT -eq 0 ]]; then
    log_fail "No pods found in namespace ${NAMESPACE}"
    exit 1
fi

log_info "Found ${POD_COUNT} pods in namespace"

# Show current pod status
log_info "Current pod status:"
kubectl get pods -n "$NAMESPACE"

# Wait for all pods to be ready
log_info "Waiting for all pods to be ready (timeout: ${TIMEOUT}s)..."

if kubectl wait --for=condition=ready pod \
    --all \
    --namespace="$NAMESPACE" \
    --timeout="${TIMEOUT}s"; then
    log_pass "All pods are ready"
else
    log_fail "Timeout waiting for pods to be ready"
    log_info "Pod status:"
    kubectl get pods -n "$NAMESPACE"
    log_info "Pod descriptions for failed pods:"
    kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name | while read -r pod; do
        echo "--- ${pod} ---"
        kubectl describe "$pod" -n "$NAMESPACE" || true
    done
    exit 1
fi

# Verify expected deployments exist
log_info "Verifying expected deployments..."
MISSING_SERVICES=()

for service in "${EXPECTED_SERVICES[@]}"; do
    # Check for deployment or statefulset
    if kubectl get deployment "$service" -n "$NAMESPACE" &> /dev/null; then
        log_pass "Deployment found: ${service}"
    elif kubectl get statefulset "$service" -n "$NAMESPACE" &> /dev/null; then
        log_pass "StatefulSet found: ${service}"
    else
        log_fail "Service not found: ${service}"
        MISSING_SERVICES+=("$service")
    fi
done

if [[ ${#MISSING_SERVICES[@]} -gt 0 ]]; then
    log_fail "Missing services: ${MISSING_SERVICES[*]}"
    exit 1
fi

# Verify all pods have passed readiness probes
log_info "Verifying pod readiness..."
NOT_READY=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running --no-headers 2>/dev/null | wc -l)

if [[ $NOT_READY -gt 0 ]]; then
    log_fail "${NOT_READY} pods are not in Running state"
    kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running
    exit 1
fi

# Check for any restarts
log_info "Checking for pod restarts..."
RESTART_COUNT=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.status.containerStatuses[*].restartCount}{"\n"}{end}' | awk '{s+=$1} END {print s}')

if [[ -z "$RESTART_COUNT" ]]; then
    RESTART_COUNT=0
fi

if [[ $RESTART_COUNT -gt 0 ]]; then
    log_fail "Detected ${RESTART_COUNT} pod restart(s)"
    kubectl get pods -n "$NAMESPACE" -o wide
    exit 1
else
    log_pass "No pod restarts detected"
fi

# Final status check
log_info "Final pod status:"
kubectl get pods -n "$NAMESPACE" -o wide

log_pass "All pods are ready and healthy"
exit 0
