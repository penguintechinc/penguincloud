#!/usr/bin/env bash
set -euo pipefail

# 04-dns-resolution.sh - Verify Kubernetes DNS resolution for all services

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

# Services to verify
SERVICES=(
    "flask-backend"
    "go-backend"
    "webui"
    "postgresql"
    "redis-master"
)

log_info "Verifying DNS resolution for all services"
log_info "Namespace: ${NAMESPACE}"

# Get a pod to run DNS tests from
log_info "Finding a pod to run DNS tests..."
TEST_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=flask-backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "$TEST_POD" ]]; then
    # Try go-backend
    TEST_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=go-backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

if [[ -z "$TEST_POD" ]]; then
    # Try webui
    TEST_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=webui -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

if [[ -z "$TEST_POD" ]]; then
    # Try any pod
    TEST_POD=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

if [[ -z "$TEST_POD" ]]; then
    log_fail "No pods found in namespace ${NAMESPACE}"
    exit 1
fi

log_info "Using pod for DNS tests: ${TEST_POD}"

# Verify pod is running
POD_STATUS=$(kubectl get pod "$TEST_POD" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
if [[ "$POD_STATUS" != "Running" ]]; then
    log_fail "Pod ${TEST_POD} is not running (status: ${POD_STATUS})"
    exit 1
fi

DNS_FAILURES=0

# Test DNS resolution for each service
for service in "${SERVICES[@]}"; do
    log_info "Testing DNS resolution for: ${service}"

    # Check if service exists
    if ! kubectl get service "$service" -n "$NAMESPACE" &> /dev/null; then
        log_fail "Service does not exist: ${service}"
        DNS_FAILURES=$((DNS_FAILURES + 1))
        continue
    fi

    # Test short name resolution (service-name)
    log_info "  Testing short name: ${service}"
    if kubectl exec "$TEST_POD" -n "$NAMESPACE" -- nslookup "$service" > /dev/null 2>&1; then
        log_pass "  Short name resolves: ${service}"
    else
        log_fail "  Short name does not resolve: ${service}"
        DNS_FAILURES=$((DNS_FAILURES + 1))
    fi

    # Test FQDN resolution (service-name.namespace.svc.cluster.local)
    FQDN="${service}.${NAMESPACE}.svc.cluster.local"
    log_info "  Testing FQDN: ${FQDN}"
    if kubectl exec "$TEST_POD" -n "$NAMESPACE" -- nslookup "$FQDN" > /dev/null 2>&1; then
        log_pass "  FQDN resolves: ${FQDN}"
    else
        log_fail "  FQDN does not resolve: ${FQDN}"
        DNS_FAILURES=$((DNS_FAILURES + 1))
    fi

    # Get service IP and verify it matches DNS resolution
    SERVICE_IP=$(kubectl get service "$service" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    if [[ -n "$SERVICE_IP" ]] && [[ "$SERVICE_IP" != "None" ]]; then
        RESOLVED_IP=$(kubectl exec "$TEST_POD" -n "$NAMESPACE" -- nslookup "$service" 2>/dev/null | grep "Address:" | tail -n1 | awk '{print $2}' || echo "")

        if [[ "$RESOLVED_IP" == "$SERVICE_IP" ]]; then
            log_pass "  DNS resolves to correct IP: ${SERVICE_IP}"
        else
            log_fail "  DNS IP mismatch - Expected: ${SERVICE_IP}, Got: ${RESOLVED_IP}"
            DNS_FAILURES=$((DNS_FAILURES + 1))
        fi
    fi

    echo ""
done

# Test cross-namespace resolution
log_info "Testing cross-namespace DNS resolution..."
log_info "Resolving kubernetes.default.svc.cluster.local"
if kubectl exec "$TEST_POD" -n "$NAMESPACE" -- nslookup kubernetes.default.svc.cluster.local > /dev/null 2>&1; then
    log_pass "Cross-namespace resolution works"
else
    log_fail "Cross-namespace resolution failed"
    DNS_FAILURES=$((DNS_FAILURES + 1))
fi

# Test general DNS resolution (external)
log_info "Testing external DNS resolution..."
if kubectl exec "$TEST_POD" -n "$NAMESPACE" -- nslookup google.com > /dev/null 2>&1; then
    log_pass "External DNS resolution works"
else
    log_fail "External DNS resolution failed"
    DNS_FAILURES=$((DNS_FAILURES + 1))
fi

# Verify CoreDNS is running
log_info "Verifying CoreDNS is running..."
COREDNS_PODS=$(kubectl get pods -n kube-system -l k8s-app=kube-dns -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
if [[ -n "$COREDNS_PODS" ]]; then
    log_pass "CoreDNS pods found: ${COREDNS_PODS}"
else
    log_fail "No CoreDNS pods found"
    DNS_FAILURES=$((DNS_FAILURES + 1))
fi

# Check DNS configuration in pod
log_info "Checking DNS configuration in test pod..."
DNS_CONFIG=$(kubectl exec "$TEST_POD" -n "$NAMESPACE" -- cat /etc/resolv.conf 2>/dev/null || echo "")
if [[ -n "$DNS_CONFIG" ]]; then
    log_info "DNS configuration:"
    echo "$DNS_CONFIG" | while IFS= read -r line; do
        echo "    $line"
    done

    if echo "$DNS_CONFIG" | grep -q "search.*svc.cluster.local"; then
        log_pass "DNS search domains configured correctly"
    else
        log_fail "DNS search domains not configured correctly"
        DNS_FAILURES=$((DNS_FAILURES + 1))
    fi
else
    log_fail "Could not read DNS configuration"
    DNS_FAILURES=$((DNS_FAILURES + 1))
fi

# Summary
echo ""
log_info "DNS resolution test summary:"
echo "  Total failures: ${DNS_FAILURES}"

if [[ $DNS_FAILURES -gt 0 ]]; then
    log_fail "DNS resolution test FAILED with ${DNS_FAILURES} failure(s)"
    exit 1
else
    log_pass "All DNS resolution tests PASSED"
    exit 0
fi
