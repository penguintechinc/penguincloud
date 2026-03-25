#!/bin/bash
# Pre-Commit Checklist Runner
# Runs all pre-commit checks and logs output to /tmp
# Usage: ./scripts/pre-commit/pre-commit.sh [service-dir]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_NAME=$(basename "$PROJECT_ROOT")
EPOCH=$(date +%s)
LOG_DIR="/tmp/pre-commit-${PROJECT_NAME}-${EPOCH}"
SUMMARY_LOG="${LOG_DIR}/summary.log"

# Export for child scripts
export LOG_DIR
export EPOCH

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create log directory
mkdir -p "$LOG_DIR"

echo "=============================================="
echo "Pre-Commit Checklist Runner"
echo "=============================================="
echo "Project: ${PROJECT_ROOT}"
echo "Logs: ${LOG_DIR}"
echo "=============================================="
echo ""

# Initialize summary
{
    echo "Pre-Commit Summary - $(date)"
    echo "Project: ${PROJECT_NAME}"
    echo "======================================"
    echo ""
} > "$SUMMARY_LOG"

FAILED=0
PASSED=0

# Function to run a check and log results
run_check() {
    local name="$1"
    local script="$2"
    local service_dir="$3"
    local log_file="${LOG_DIR}/${name}-${EPOCH}.log"

    echo -n "Running ${name}... "

    if [ -x "$script" ]; then
        if "$script" "$service_dir" > "$log_file" 2>&1; then
            echo -e "${GREEN}PASSED${NC}"
            echo "[PASS] ${name}" >> "$SUMMARY_LOG"
            echo "       Log: ${log_file}" >> "$SUMMARY_LOG"
            ((PASSED++)) || true
            return 0
        else
            echo -e "${RED}FAILED${NC}"
            echo "[FAIL] ${name}" >> "$SUMMARY_LOG"
            echo "       Log: ${log_file}" >> "$SUMMARY_LOG"
            ((FAILED++)) || true
            return 1
        fi
    else
        echo -e "${YELLOW}SKIPPED${NC} (script not found)"
        echo "[SKIP] ${name}" >> "$SUMMARY_LOG"
        return 0
    fi
}

# Main execution
main() {
    local target_service="$1"
    local all_passed=true

    echo "Step 1: Linting"
    echo "----------------"

    # Check for Python services
    if [ -d "$PROJECT_ROOT/services/flask-backend" ] || find "$PROJECT_ROOT" -name "*.py" -type f 2>/dev/null | head -1 | grep -q .; then
        run_check "python-lint" "$SCRIPT_DIR/check-python.sh" "$PROJECT_ROOT" || all_passed=false
    fi

    # Check for Go services
    if [ -d "$PROJECT_ROOT/services/go-backend" ] || find "$PROJECT_ROOT" -name "go.mod" -type f 2>/dev/null | head -1 | grep -q .; then
        run_check "go-lint" "$SCRIPT_DIR/check-go.sh" "$PROJECT_ROOT" || all_passed=false
    fi

    # Check for Node.js services
    if [ -d "$PROJECT_ROOT/services/webui" ] || [ -f "$PROJECT_ROOT/package.json" ]; then
        run_check "node-lint" "$SCRIPT_DIR/check-node.sh" "$PROJECT_ROOT" || all_passed=false
    fi

    echo ""
    echo "Step 2: Security Scans"
    echo "----------------------"
    run_check "security" "$SCRIPT_DIR/check-security.sh" "$PROJECT_ROOT" || all_passed=false

    echo ""
    echo "Step 3: Secret Detection"
    echo "------------------------"
    run_check "secrets" "$SCRIPT_DIR/check-secrets.sh" "$PROJECT_ROOT" || all_passed=false

    echo ""
    echo "Step 4: Build & Run"
    echo "-------------------"
    run_check "docker-build" "$SCRIPT_DIR/check-docker.sh" "$PROJECT_ROOT" || all_passed=false

    echo ""
    echo "Step 5: Smoke Tests"
    echo "------------------"
    if [ -f "$PROJECT_ROOT/tests/smoke/run-all.sh" ] && [ -x "$PROJECT_ROOT/tests/smoke/run-all.sh" ]; then
        if "$PROJECT_ROOT/tests/smoke/run-all.sh" > "${LOG_DIR}/smoke-tests-${EPOCH}.log" 2>&1; then
            echo -e "${GREEN}PASSED${NC}"
            echo "[PASS] smoke-tests" >> "$SUMMARY_LOG"
            echo "       Log: ${LOG_DIR}/smoke-tests-${EPOCH}.log" >> "$SUMMARY_LOG"
            ((PASSED++)) || true
        else
            echo -e "${RED}FAILED${NC}"
            echo "[FAIL] smoke-tests" >> "$SUMMARY_LOG"
            echo "       Log: ${LOG_DIR}/smoke-tests-${EPOCH}.log" >> "$SUMMARY_LOG"
            ((FAILED++)) || true
            all_passed=false
        fi
    else
        echo -e "${YELLOW}SKIPPED${NC} (smoke test script not found)"
        echo "[SKIP] smoke-tests" >> "$SUMMARY_LOG"
    fi

    echo ""
    echo "Step 6: Full Tests"
    echo "------------------"
    run_check "tests" "$SCRIPT_DIR/check-tests.sh" "$PROJECT_ROOT" || all_passed=false

    echo ""
    echo "=============================================="
    echo "Summary"
    echo "=============================================="
    echo -e "Passed: ${GREEN}${PASSED}${NC}"
    echo -e "Failed: ${RED}${FAILED}${NC}"
    echo ""

    # Append final status to summary
    {
        echo ""
        echo "======================================"
        echo "Total Passed: ${PASSED}"
        echo "Total Failed: ${FAILED}"
    } >> "$SUMMARY_LOG"

    if [ "$all_passed" = true ] && [ "$FAILED" -eq 0 ]; then
        echo -e "${GREEN}All checks passed! Ready to commit.${NC}"
        echo "Status: READY TO COMMIT" >> "$SUMMARY_LOG"
        echo ""
        echo "Results in: ${SUMMARY_LOG}"
        return 0
    else
        echo -e "${RED}Some checks failed. Please fix issues before committing.${NC}"
        echo "Status: NOT READY - FIX ISSUES" >> "$SUMMARY_LOG"
        echo ""
        echo "Results in: ${SUMMARY_LOG}"
        echo "Individual logs in: ${LOG_DIR}/"
        return 1
    fi
}

main "$@"
