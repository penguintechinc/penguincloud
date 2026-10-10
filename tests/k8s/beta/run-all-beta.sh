#!/usr/bin/env bash
set -euo pipefail

# run-all-beta.sh - Orchestrator for beta smoke test suite
# Runs all beta tests in order, exits on first failure

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging functions
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

# Test suite metadata
TESTS=(
    "01-deploy-helm.sh:Deploy Helm chart with beta values"
    "02-wait-ready.sh:Wait for all pods to be ready"
    "03-hardcoded-check.sh:Check for hardcoded IPs/ports"
    "04-dns-resolution.sh:Verify DNS resolution"
    "05-integration-test.sh:Run integration tests"
    "06-network-policy.sh:Verify network policies"
    "07-scaling-test.sh:Test horizontal scaling"
    "08-cleanup.sh:Cleanup resources"
)

# Track results
PASSED=0
FAILED=0
START_TIME=$(date +%s)

echo ""
log_info "========================================="
log_info "Beta Smoke Test Suite - Project Template"
log_info "========================================="
echo ""

# Run each test in order
for test_entry in "${TESTS[@]}"; do
    IFS=':' read -r test_script test_description <<< "$test_entry"
    test_path="${SCRIPT_DIR}/${test_script}"

    echo ""
    log_info "Running: ${test_description}"
    log_info "Script: ${test_script}"
    echo ""

    if [[ ! -f "$test_path" ]]; then
        log_fail "Test script not found: ${test_path}"
        FAILED=$((FAILED + 1))
        break
    fi

    if [[ ! -x "$test_path" ]]; then
        log_info "Making script executable: ${test_script}"
        chmod +x "$test_path"
    fi

    # Run the test
    if "$test_path"; then
        log_pass "${test_description} - PASSED"
        PASSED=$((PASSED + 1))
    else
        log_fail "${test_description} - FAILED"
        FAILED=$((FAILED + 1))

        # Stop on first failure (except cleanup)
        if [[ "$test_script" != "08-cleanup.sh" ]]; then
            echo ""
            log_fail "Test suite stopped due to failure"
            log_info "Running cleanup..."
            if [[ -f "${SCRIPT_DIR}/08-cleanup.sh" ]]; then
                "${SCRIPT_DIR}/08-cleanup.sh" || true
            fi
            break
        fi
    fi
done

# Calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Print summary
echo ""
echo "========================================="
echo "Test Suite Summary"
echo "========================================="
echo "Passed: ${PASSED}"
echo "Failed: ${FAILED}"
echo "Duration: ${DURATION}s"
echo "========================================="
echo ""

if [[ $FAILED -eq 0 ]]; then
    log_pass "All beta smoke tests PASSED"
    exit 0
else
    log_fail "Beta smoke tests FAILED"
    exit 1
fi
