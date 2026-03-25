#!/bin/bash

################################################################################
# Smoke Tests Orchestrator
# Runs all smoke tests in sequence and reports results
################################################################################

set -o pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
RUN_DIR="${SCRIPT_DIR}/run"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0
FAILED_TESTS=()

# Flags
BUILD_ONLY=false
MOBILE_ONLY=false

################################################################################
# Functions
################################################################################

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build-only)
                BUILD_ONLY=true
                shift
                ;;
            --mobile-only)
                MOBILE_ONLY=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# Display usage information
usage() {
    cat << 'USAGE'
Usage: ./run-all.sh [OPTIONS]

Options:
    --build-only    Run only build tests
    --mobile-only   Run only mobile tests
    -h, --help      Show this help message

Description:
    Runs all smoke tests in sequence and reports results.
    Executes all test scripts in tests/smoke/build/ and tests/smoke/run/ directories.
    Exits with 0 if all tests pass, non-zero if any test fails.
USAGE
}

# Execute a single test and track results
run_test() {
    local test_file="$1"
    local test_name=$(basename "$test_file")
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    echo -n "Running $test_name ... "
    
    if "$test_file"; then
        echo -e "${GREEN}✅ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}❌ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("$test_name")
    fi
}

# Display test summary
print_summary() {
    echo ""
    echo "================================================================================"
    echo "Smoke Test Summary"
    echo "================================================================================"
    echo -e "Total tests:  $TESTS_TOTAL"
    echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"
    
    if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
        echo ""
        echo "Failed tests:"
        for test in "${FAILED_TESTS[@]}"; do
            echo -e "  ${RED}❌${NC} $test"
        done
    fi
    echo "================================================================================"
}

################################################################################
# Main Execution
################################################################################

# Show help if requested
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 0
fi

# Parse arguments
parse_args "$@"

cd "$PROJECT_ROOT" || exit 1

echo "Smoke Test Suite Starting"
echo "Project root: $PROJECT_ROOT"
echo "Build tests:  $BUILD_DIR"
echo "Run tests:    $RUN_DIR"
echo ""

# Run build tests
if [ "$MOBILE_ONLY" = false ]; then
    if [ -d "$BUILD_DIR" ]; then
        echo "Running build tests..."
        echo "--------------------------------------------------------------------------------"
        
        # Find and run all executable shell scripts
        while IFS= read -r -d '' test_file; do
            if [ -x "$test_file" ]; then
                run_test "$test_file"
            fi
        done < <(find "$BUILD_DIR" -maxdepth 1 -name "*.sh" -print0 2>/dev/null)
        
        if [ $TESTS_TOTAL -eq 0 ]; then
            echo "No build tests found in $BUILD_DIR"
        fi
        echo ""
    else
        if [ "$BUILD_ONLY" = false ]; then
            echo "Warning: Build tests directory not found: $BUILD_DIR"
            echo ""
        fi
    fi
fi

# Run runtime tests (if not build-only)
if [ "$BUILD_ONLY" = false ]; then
    if [ -d "$RUN_DIR" ]; then
        echo "Running runtime tests..."
        echo "--------------------------------------------------------------------------------"
        
        # Find and run all executable shell scripts
        while IFS= read -r -d '' test_file; do
            if [ -x "$test_file" ]; then
                run_test "$test_file"
            fi
        done < <(find "$RUN_DIR" -maxdepth 1 -name "*.sh" -print0 2>/dev/null)
        
        if [ $TESTS_TOTAL -eq 0 ]; then
            echo "No runtime tests found in $RUN_DIR"
        fi
        echo ""
    fi
fi

# Print summary
print_summary

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ] && [ $TESTS_TOTAL -gt 0 ]; then
    exit 0
elif [ $TESTS_TOTAL -eq 0 ]; then
    echo "Warning: No tests were run"
    exit 1
else
    exit 1
fi
