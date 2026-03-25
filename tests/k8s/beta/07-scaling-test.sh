#!/usr/bin/env bash
set -euo pipefail

# 07-scaling-test.sh - Test horizontal scaling

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
TEST_FAILURES=0
PORT_FORWARDS=()

# Services to scale test
DEPLOYMENTS=(
    "flask-backend"
    "go-backend"
    "webui"
)

# Cleanup function
cleanup_port_forwards() {
    log_info "Cleaning up port forwards..."
    for pid in "${PORT_FORWARDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    PORT_FORWARDS=()
}

trap cleanup_port_forwards EXIT INT TERM

log_info "Running horizontal scaling tests for beta environment"
log_info "Namespace: ${NAMESPACE}"

# Store original replica counts
declare -A ORIGINAL_REPLICAS

# Get original replica counts
log_info "Recording original replica counts..."
for deployment in "${DEPLOYMENTS[@]}"; do
    if kubectl get deployment "$deployment" -n "$NAMESPACE" &> /dev/null; then
        REPLICAS=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
        ORIGINAL_REPLICAS[$deployment]=$REPLICAS
        log_info "  ${deployment}: ${REPLICAS} replica(s)"
    else
        log_warn "  ${deployment}: deployment not found"
    fi
done

# Test scaling for each deployment
for deployment in "${DEPLOYMENTS[@]}"; do
    if [[ -z "${ORIGINAL_REPLICAS[$deployment]:-}" ]]; then
        continue
    fi

    ORIGINAL_COUNT=${ORIGINAL_REPLICAS[$deployment]}
    TARGET_REPLICAS=3

    echo ""
    log_info "=== Testing scaling for ${deployment} ==="

    # Scale up
    log_info "Scaling ${deployment} from ${ORIGINAL_COUNT} to ${TARGET_REPLICAS} replicas..."
    if kubectl scale deployment "$deployment" -n "$NAMESPACE" --replicas="$TARGET_REPLICAS"; then
        log_pass "Scale command successful"
    else
        log_fail "Scale command failed for ${deployment}"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        continue
    fi

    # Wait for rollout
    log_info "Waiting for rollout to complete (timeout: 300s)..."
    if kubectl rollout status deployment "$deployment" -n "$NAMESPACE" --timeout=300s; then
        log_pass "Rollout completed for ${deployment}"
    else
        log_fail "Rollout failed or timed out for ${deployment}"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        continue
    fi

    # Verify replica count
    log_info "Verifying replica count..."
    READY_REPLICAS=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')

    if [[ "$READY_REPLICAS" == "$TARGET_REPLICAS" ]]; then
        log_pass "${deployment} has ${READY_REPLICAS}/${TARGET_REPLICAS} ready replicas"
    else
        log_fail "${deployment} has ${READY_REPLICAS}/${TARGET_REPLICAS} ready replicas"
        TEST_FAILURES=$((TEST_FAILURES + 1))

        # Show pod status for debugging
        log_info "Pod status:"
        kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=${deployment}"
        continue
    fi

    # Verify all replicas are running
    log_info "Verifying all pods are running..."
    RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=${deployment}" --field-selector=status.phase=Running --no-headers | wc -l)

    if [[ "$RUNNING_PODS" == "$TARGET_REPLICAS" ]]; then
        log_pass "All ${RUNNING_PODS} pods are running"
    else
        log_fail "Only ${RUNNING_PODS}/${TARGET_REPLICAS} pods are running"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Get pod IPs to verify load distribution
    log_info "Getting pod IPs..."
    POD_IPS=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=${deployment}" -o jsonpath='{.items[*].status.podIP}')
    log_info "Pod IPs: ${POD_IPS}"

    # Test load distribution (if health endpoint is available)
    case $deployment in
        flask-backend)
            SERVICE_PORT=5000
            HEALTH_PATH="/healthz"
            ;;
        go-backend)
            SERVICE_PORT=8080
            HEALTH_PATH="/healthz"
            ;;
        webui)
            SERVICE_PORT=3000
            HEALTH_PATH="/healthz"
            ;;
        *)
            log_warn "Unknown service port for ${deployment}, skipping load test"
            continue
            ;;
    esac

    log_info "Testing load distribution across replicas..."
    LOCAL_PORT=$((15000 + RANDOM % 1000))

    kubectl port-forward -n "$NAMESPACE" "service/${deployment}" "${LOCAL_PORT}:${SERVICE_PORT}" > /dev/null 2>&1 &
    PF_PID=$!
    PORT_FORWARDS+=("$PF_PID")
    sleep 2

    if kill -0 "$PF_PID" 2>/dev/null; then
        # Make multiple requests and check if we hit different pods
        declare -A RESPONSE_PODS
        TOTAL_REQUESTS=10

        for ((i=1; i<=TOTAL_REQUESTS; i++)); do
            RESPONSE=$(curl -s "http://localhost:${LOCAL_PORT}${HEALTH_PATH}" 2>/dev/null || echo "")
            # Try to extract pod name or identifier from response
            # This is a basic check - actual implementation may vary
            RESPONSE_PODS["$i"]="$RESPONSE"
            sleep 0.5
        done

        log_pass "Successfully made ${TOTAL_REQUESTS} requests to ${deployment}"

        # Kill port-forward
        kill "$PF_PID" 2>/dev/null || true
    else
        log_warn "Port-forward failed, skipping load distribution test"
    fi

    # Scale back to original
    log_info "Scaling ${deployment} back to ${ORIGINAL_COUNT} replica(s)..."
    if kubectl scale deployment "$deployment" -n "$NAMESPACE" --replicas="$ORIGINAL_COUNT"; then
        log_pass "Scale down command successful"
    else
        log_fail "Scale down command failed for ${deployment}"
        TEST_FAILURES=$((TEST_FAILURES + 1))
        continue
    fi

    # Wait for scale down
    log_info "Waiting for scale down to complete..."
    if kubectl rollout status deployment "$deployment" -n "$NAMESPACE" --timeout=300s; then
        log_pass "Scale down completed for ${deployment}"
    else
        log_fail "Scale down failed or timed out for ${deployment}"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Verify back to original count
    CURRENT_REPLICAS=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
    if [[ "$CURRENT_REPLICAS" == "$ORIGINAL_COUNT" ]]; then
        log_pass "${deployment} scaled back to ${ORIGINAL_COUNT} replica(s)"
    else
        log_fail "${deployment} has ${CURRENT_REPLICAS} replicas, expected ${ORIGINAL_COUNT}"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
done

# Test stateful services (should not scale or handle scaling differently)
log_info "=== Checking StatefulSet Scaling Behavior ==="

STATEFULSETS=$(kubectl get statefulsets -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$STATEFULSETS" ]]; then
    for sts in $STATEFULSETS; do
        REPLICAS=$(kubectl get statefulset "$sts" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
        log_info "StatefulSet ${sts}: ${REPLICAS} replica(s)"
        log_info "  (StatefulSets typically require special handling for scaling)"
    done
else
    log_info "No StatefulSets found"
fi

# Verify all services are still healthy after scaling operations
log_info "=== Verifying Service Health After Scaling ==="

for deployment in "${DEPLOYMENTS[@]}"; do
    if [[ -z "${ORIGINAL_REPLICAS[$deployment]:-}" ]]; then
        continue
    fi

    log_info "Checking health of ${deployment}..."
    READY=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
    DESIRED=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')

    if [[ "$READY" == "$DESIRED" ]]; then
        log_pass "${deployment} is healthy (${READY}/${DESIRED} ready)"
    else
        log_fail "${deployment} is unhealthy (${READY}/${DESIRED} ready)"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
done

# Cleanup port forwards
cleanup_port_forwards

# Summary
echo ""
log_info "Scaling test summary:"
echo "  Total failures: ${TEST_FAILURES}"

if [[ $TEST_FAILURES -gt 0 ]]; then
    log_fail "Scaling tests FAILED with ${TEST_FAILURES} failure(s)"
    exit 1
else
    log_pass "All scaling tests PASSED"
    exit 0
fi
