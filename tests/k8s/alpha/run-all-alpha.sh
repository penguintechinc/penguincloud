#!/usr/bin/env bash
set -euo pipefail

# Alpha Smoke Test Suite - Orchestrator
# Runs all alpha smoke tests in sequence
# Exits on first failure

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$(cd "$SCRIPT_DIR/../../.." && pwd)")"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
}

log_header() {
    echo ""
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}$*${NC}"
    echo -e "${YELLOW}========================================${NC}"
}

run_test() {
    local script="$1"
    local description="$2"

    log_header "$description"

    if [[ ! -f "$SCRIPT_DIR/$script" ]]; then
        log_fail "Script not found: $script"
        return 1
    fi

    if bash "$SCRIPT_DIR/$script"; then
        log_pass "$description completed successfully"
        return 0
    else
        log_fail "$description failed"
        return 1
    fi
}

main() {
    log_header "Alpha Smoke Test Suite for $PROJECT_NAME"
    log_info "Starting full alpha smoke test suite..."

    local start_time=$(date +%s)

    # Run all tests in order
    run_test "01-build-images.sh" "Step 1: Build Docker Images" || exit 1
    run_test "02-deploy-helm.sh" "Step 2: Deploy Helm Chart" || exit 1
    run_test "03-wait-ready.sh" "Step 3: Wait for Pods Ready" || exit 1
    run_test "04-health-check.sh" "Step 4: Health Checks" || exit 1
    run_test "05-unit-tests.sh" "Step 5: Unit Tests" || exit 1
    run_test "06-api-integration.sh" "Step 6: API Integration Tests" || exit 1
    run_test "07-page-load.sh" "Step 7: Page Load Tests" || exit 1
    run_test "08-cleanup.sh" "Step 8: Cleanup" || exit 1

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_header "All Alpha Smoke Tests Passed!"
    log_info "Total duration: ${duration}s"
    log_pass "Alpha environment is verified and cleaned up"
}

main "$@"
