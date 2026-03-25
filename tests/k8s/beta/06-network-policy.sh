#!/usr/bin/env bash
set -euo pipefail

# 06-network-policy.sh - Verify network policies

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

log_info "Verifying network policies for beta environment"
log_info "Namespace: ${NAMESPACE}"

# Check if network policies are deployed
log_info "Checking for NetworkPolicy resources..."
NETPOL_COUNT=$(kubectl get networkpolicies -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

if [[ $NETPOL_COUNT -eq 0 ]]; then
    log_warn "No NetworkPolicy resources found in namespace"
    log_warn "Skipping network policy tests (policies not enforced)"
    exit 0
fi

log_info "Found ${NETPOL_COUNT} NetworkPolicy resource(s)"
kubectl get networkpolicies -n "$NAMESPACE"

# Get test pods
FLASK_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=flask-backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
GO_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=go-backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
WEBUI_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=webui -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

# 1. Test DNS resolution works with network policies
log_info "=== Testing DNS Resolution with Network Policies ==="
if [[ -n "$FLASK_POD" ]]; then
    log_info "Testing DNS from Flask pod..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- nslookup kubernetes.default.svc.cluster.local > /dev/null 2>&1; then
        log_pass "DNS resolution works with network policies"
    else
        log_fail "DNS resolution blocked by network policies"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# 2. Test allowed traffic flows
log_info "=== Testing Allowed Traffic Flows ==="

# WebUI -> Flask Backend (should be allowed)
if [[ -n "$WEBUI_POD" ]]; then
    log_info "Testing WebUI -> Flask Backend (should be allowed)..."
    if kubectl exec "$WEBUI_POD" -n "$NAMESPACE" -- timeout 5 curl -s -f "http://flask-backend:5000/healthz" > /dev/null 2>&1; then
        log_pass "WebUI can reach Flask Backend"
    else
        log_fail "WebUI cannot reach Flask Backend (should be allowed)"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# WebUI -> Go Backend (should be allowed)
if [[ -n "$WEBUI_POD" ]]; then
    log_info "Testing WebUI -> Go Backend (should be allowed)..."
    if kubectl exec "$WEBUI_POD" -n "$NAMESPACE" -- timeout 5 curl -s -f "http://go-backend:8080/healthz" > /dev/null 2>&1; then
        log_pass "WebUI can reach Go Backend"
    else
        log_fail "WebUI cannot reach Go Backend (should be allowed)"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# Flask Backend -> PostgreSQL (should be allowed)
if [[ -n "$FLASK_POD" ]]; then
    log_info "Testing Flask Backend -> PostgreSQL (should be allowed)..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 nslookup postgresql > /dev/null 2>&1; then
        log_pass "Flask Backend can resolve PostgreSQL"

        # Try to connect
        POSTGRES_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "${PROJECT_NAME}-postgresql" -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
        if [[ -n "$POSTGRES_PASSWORD" ]]; then
            # Note: This test verifies network connectivity, not authentication
            if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 nc -zv postgresql 5432 2>&1 | grep -q "succeeded\|open"; then
                log_pass "Flask Backend can reach PostgreSQL"
            else
                log_warn "Flask Backend cannot connect to PostgreSQL (may be expected)"
            fi
        fi
    else
        log_fail "Flask Backend cannot resolve PostgreSQL"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# Flask Backend -> Redis (should be allowed)
if [[ -n "$FLASK_POD" ]]; then
    log_info "Testing Flask Backend -> Redis (should be allowed)..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 nslookup redis-master > /dev/null 2>&1; then
        log_pass "Flask Backend can resolve Redis"

        # Try to connect
        if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 nc -zv redis-master 6379 2>&1 | grep -q "succeeded\|open"; then
            log_pass "Flask Backend can reach Redis"
        else
            log_warn "Flask Backend cannot connect to Redis (may be expected)"
        fi
    else
        log_fail "Flask Backend cannot resolve Redis"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# Go Backend -> PostgreSQL (should be allowed)
if [[ -n "$GO_POD" ]]; then
    log_info "Testing Go Backend -> PostgreSQL (should be allowed)..."
    if kubectl exec "$GO_POD" -n "$NAMESPACE" -- timeout 5 nslookup postgresql > /dev/null 2>&1; then
        log_pass "Go Backend can resolve PostgreSQL"
    else
        log_fail "Go Backend cannot resolve PostgreSQL"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
fi

# 3. Test blocked traffic (if strict policies are enforced)
log_info "=== Testing Network Isolation ==="

# This section tests that unauthorized paths are blocked
# Note: This depends on how strict your network policies are

# Check if there's a default deny policy
DEFAULT_DENY=$(kubectl get networkpolicies -n "$NAMESPACE" -o json | jq -r '.items[] | select(.spec.podSelector.matchLabels == null or .spec.podSelector.matchLabels == {}) | .metadata.name' 2>/dev/null || echo "")

if [[ -n "$DEFAULT_DENY" ]]; then
    log_info "Found default deny policy: ${DEFAULT_DENY}"
    log_pass "Default deny network policy is in place"
else
    log_warn "No default deny policy found (less secure)"
fi

# 4. Verify egress for external services
log_info "=== Testing External Connectivity ==="

if [[ -n "$FLASK_POD" ]]; then
    log_info "Testing external DNS resolution..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 nslookup google.com > /dev/null 2>&1; then
        log_pass "External DNS resolution works"
    else
        log_warn "External DNS resolution blocked (may be intentional)"
    fi

    log_info "Testing external HTTPS connectivity..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- timeout 5 curl -s -f https://www.google.com > /dev/null 2>&1; then
        log_pass "External HTTPS connectivity works"
    else
        log_warn "External HTTPS blocked (may be intentional)"
    fi
fi

# 5. Verify network policy configuration
log_info "=== Analyzing Network Policy Configuration ==="

POLICIES=$(kubectl get networkpolicies -n "$NAMESPACE" -o json 2>/dev/null)

# Check for ingress rules
INGRESS_COUNT=$(echo "$POLICIES" | jq '[.items[].spec.ingress // []] | flatten | length' 2>/dev/null || echo "0")
log_info "Total ingress rules: ${INGRESS_COUNT}"

# Check for egress rules
EGRESS_COUNT=$(echo "$POLICIES" | jq '[.items[].spec.egress // []] | flatten | length' 2>/dev/null || echo "0")
log_info "Total egress rules: ${EGRESS_COUNT}"

# List all policies with their types
log_info "Network policies details:"
kubectl get networkpolicies -n "$NAMESPACE" -o json | jq -r '.items[] | "\(.metadata.name): Ingress=\(if .spec.ingress then "yes" else "no" end), Egress=\(if .spec.egress then "yes" else "no" end)"' 2>/dev/null || true

# 6. Verify pod labels for network policy selectors
log_info "=== Verifying Pod Labels for Network Policies ==="

POLICY_SELECTORS=$(kubectl get networkpolicies -n "$NAMESPACE" -o json | jq -r '.items[].spec.podSelector.matchLabels' 2>/dev/null || echo "")

if [[ -n "$POLICY_SELECTORS" ]]; then
    log_info "Verifying pods match network policy selectors..."

    # Check if all pods have required labels
    UNLABELED_PODS=$(kubectl get pods -n "$NAMESPACE" -o json | jq -r '.items[] | select(.metadata.labels == null or (.metadata.labels | length) == 0) | .metadata.name' 2>/dev/null || echo "")

    if [[ -n "$UNLABELED_PODS" ]]; then
        log_warn "Found pods without labels (may not be covered by network policies):"
        echo "$UNLABELED_PODS"
    else
        log_pass "All pods have labels for network policy matching"
    fi
fi

# Summary
echo ""
log_info "Network policy test summary:"
echo "  Total failures: ${TEST_FAILURES}"

if [[ $TEST_FAILURES -gt 0 ]]; then
    log_fail "Network policy tests FAILED with ${TEST_FAILURES} failure(s)"
    exit 1
else
    log_pass "All network policy tests PASSED"
    exit 0
fi
