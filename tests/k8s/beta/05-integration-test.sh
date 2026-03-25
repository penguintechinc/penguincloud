#!/usr/bin/env bash
set -euo pipefail

# 05-integration-test.sh - Real integration tests against beta endpoints

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

# Trap cleanup on exit
trap cleanup_port_forwards EXIT INT TERM

# Helper function to start port-forward
start_port_forward() {
    local service=$1
    local local_port=$2
    local remote_port=$3

    log_info "Starting port-forward for ${service}: ${local_port} -> ${remote_port}"
    kubectl port-forward -n "$NAMESPACE" "service/${service}" "${local_port}:${remote_port}" > /dev/null 2>&1 &
    local pid=$!
    PORT_FORWARDS+=("$pid")

    # Wait for port-forward to be ready
    sleep 2

    if kill -0 "$pid" 2>/dev/null; then
        log_pass "Port-forward ready for ${service}"
        return 0
    else
        log_fail "Port-forward failed for ${service}"
        return 1
    fi
}

# Helper function to test HTTP endpoint
test_http_endpoint() {
    local url=$1
    local expected_status=${2:-200}
    local description=$3

    log_info "Testing: ${description}"
    log_info "  URL: ${url}"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "$expected_status" ]]; then
        log_pass "  HTTP ${HTTP_CODE} - ${description}"
        return 0
    else
        log_fail "  Expected HTTP ${expected_status}, got ${HTTP_CODE} - ${description}"
        return 1
    fi
}

log_info "Running integration tests for beta environment"
log_info "Namespace: ${NAMESPACE}"

# 1. Test Flask Backend
log_info "=== Testing Flask Backend ==="
if start_port_forward "flask-backend" 15000 5000; then
    sleep 2

    # Test health endpoint
    if test_http_endpoint "http://localhost:15000/healthz" 200 "Flask health endpoint"; then
        log_pass "Flask backend health check passed"
    else
        log_fail "Flask backend health check failed"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Test database connectivity through Flask
    log_info "Testing Flask database connectivity..."
    DB_RESPONSE=$(curl -s "http://localhost:15000/healthz" 2>/dev/null || echo "")
    if [[ -n "$DB_RESPONSE" ]]; then
        log_pass "Flask can connect to backend services"
    else
        log_fail "Flask backend not responding"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
else
    log_fail "Failed to set up port-forward for flask-backend"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# 2. Test Go Backend
log_info "=== Testing Go Backend ==="
if start_port_forward "go-backend" 18080 8080; then
    sleep 2

    # Test health endpoint
    if test_http_endpoint "http://localhost:18080/healthz" 200 "Go health endpoint"; then
        log_pass "Go backend health check passed"
    else
        log_fail "Go backend health check failed"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Test API endpoint
    log_info "Testing Go backend API..."
    API_RESPONSE=$(curl -s "http://localhost:18080/healthz" 2>/dev/null || echo "")
    if [[ -n "$API_RESPONSE" ]]; then
        log_pass "Go backend API responding"
    else
        log_fail "Go backend API not responding"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
else
    log_fail "Failed to set up port-forward for go-backend"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# 3. Test WebUI
log_info "=== Testing WebUI ==="
if start_port_forward "webui" 13000 3000; then
    sleep 2

    # Test health endpoint
    if test_http_endpoint "http://localhost:13000/healthz" 200 "WebUI health endpoint"; then
        log_pass "WebUI health check passed"
    else
        log_fail "WebUI health check failed"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
else
    log_fail "Failed to set up port-forward for webui"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# 4. Test Database Connectivity
log_info "=== Testing PostgreSQL Connectivity ==="
POSTGRES_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$POSTGRES_POD" ]]; then
    log_info "Testing PostgreSQL from pod: ${POSTGRES_POD}"

    # Get postgres password from secret
    POSTGRES_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "${PROJECT_NAME}-postgresql" -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

    if [[ -n "$POSTGRES_PASSWORD" ]]; then
        # Test connection
        if kubectl exec "$POSTGRES_POD" -n "$NAMESPACE" -- env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -c "SELECT 1" > /dev/null 2>&1; then
            log_pass "PostgreSQL connection successful"
        else
            log_fail "PostgreSQL connection failed"
            TEST_FAILURES=$((TEST_FAILURES + 1))
        fi
    else
        log_warn "Could not retrieve PostgreSQL password"
    fi
else
    log_fail "PostgreSQL pod not found"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# 5. Test Redis Connectivity
log_info "=== Testing Redis Connectivity ==="
REDIS_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$REDIS_POD" ]]; then
    log_info "Testing Redis from pod: ${REDIS_POD}"

    # Get redis password from secret
    REDIS_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "${PROJECT_NAME}-redis" -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

    if [[ -n "$REDIS_PASSWORD" ]]; then
        # Test connection
        if kubectl exec "$REDIS_POD" -n "$NAMESPACE" -- redis-cli -a "$REDIS_PASSWORD" PING 2>/dev/null | grep -q "PONG"; then
            log_pass "Redis connection successful"
        else
            log_fail "Redis connection failed"
            TEST_FAILURES=$((TEST_FAILURES + 1))
        fi
    else
        log_warn "Could not retrieve Redis password"
    fi
else
    log_fail "Redis pod not found"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# 6. Test Inter-Service Communication
log_info "=== Testing Inter-Service Communication ==="
FLASK_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=flask-backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$FLASK_POD" ]]; then
    log_info "Testing service-to-service communication from Flask pod"

    # Test Flask -> Go Backend
    log_info "Testing Flask -> Go Backend communication..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- curl -s -f -m 5 "http://go-backend:8080/healthz" > /dev/null 2>&1; then
        log_pass "Flask can reach Go Backend via DNS"
    else
        log_fail "Flask cannot reach Go Backend via DNS"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Test Flask -> PostgreSQL
    log_info "Testing Flask -> PostgreSQL DNS resolution..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- nslookup postgresql > /dev/null 2>&1; then
        log_pass "Flask can resolve PostgreSQL via DNS"
    else
        log_fail "Flask cannot resolve PostgreSQL via DNS"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi

    # Test Flask -> Redis
    log_info "Testing Flask -> Redis DNS resolution..."
    if kubectl exec "$FLASK_POD" -n "$NAMESPACE" -- nslookup redis-master > /dev/null 2>&1; then
        log_pass "Flask can resolve Redis via DNS"
    else
        log_fail "Flask cannot resolve Redis via DNS"
        TEST_FAILURES=$((TEST_FAILURES + 1))
    fi
else
    log_fail "Flask pod not found for inter-service tests"
    TEST_FAILURES=$((TEST_FAILURES + 1))
fi

# Cleanup port forwards
cleanup_port_forwards

# Summary
echo ""
log_info "Integration test summary:"
echo "  Total failures: ${TEST_FAILURES}"

if [[ $TEST_FAILURES -gt 0 ]]; then
    log_fail "Integration tests FAILED with ${TEST_FAILURES} failure(s)"
    exit 1
else
    log_pass "All integration tests PASSED"
    exit 0
fi
