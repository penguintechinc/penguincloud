#!/bin/bash
# Test Runner Pre-Commit Checks
# Runs unit tests for all languages

set -e

PROJECT_ROOT="${1:-.}"

echo "Test Runner Pre-Commit Checks"
echo "=============================="
echo "Project: ${PROJECT_ROOT}"
echo ""

FAILED=0
TESTS_RUN=0

# Python Tests
if find "$PROJECT_ROOT" -name "*.py" -type f -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | head -1 | grep -q .; then
    echo "--- Python Tests ---"

    # Look for pytest
    if command -v pytest &> /dev/null; then
        # Find test directories
        TEST_DIRS=$(find "$PROJECT_ROOT" -type d \( -name "tests" -o -name "test" \) -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null)

        if [ -n "$TEST_DIRS" ]; then
            echo "Running pytest..."
            for test_dir in $TEST_DIRS; do
                if find "$test_dir" -name "test_*.py" -o -name "*_test.py" 2>/dev/null | head -1 | grep -q .; then
                    echo "Testing: $test_dir"
                    if ! pytest "$test_dir" -v --tb=short 2>&1; then
                        echo "pytest failed in $test_dir"
                        ((FAILED++))
                    fi
                    ((TESTS_RUN++))
                fi
            done
        else
            echo "No Python test directories found"
        fi
    else
        echo "pytest not installed"
    fi
    echo ""
fi

# Go Tests
if find "$PROJECT_ROOT" -name "go.mod" -type f 2>/dev/null | head -1 | grep -q .; then
    echo "--- Go Tests ---"

    while IFS= read -r -d '' gomod; do
        dir=$(dirname "$gomod")
        echo "Testing: $dir"
        cd "$dir"

        # Check if there are test files
        if find . -name "*_test.go" -type f 2>/dev/null | head -1 | grep -q .; then
            echo "Running go test..."
            if ! go test -v -short ./... 2>&1; then
                echo "go test failed in $dir"
                ((FAILED++))
            fi
            ((TESTS_RUN++))
        else
            echo "No Go test files found in $dir"
        fi

        cd - > /dev/null
    done < <(find "$PROJECT_ROOT" -name "go.mod" -type f -print0 2>/dev/null)
    echo ""
fi

# Node.js Tests
if find "$PROJECT_ROOT" -name "package.json" -type f -not -path "*/node_modules/*" 2>/dev/null | head -1 | grep -q .; then
    echo "--- Node.js Tests ---"

    while IFS= read -r -d '' pkg; do
        dir=$(dirname "$pkg")
        if [[ "$dir" != *"node_modules"* ]]; then
            cd "$dir"

            # Check if test script exists
            if [ -f "package.json" ] && grep -q '"test"' package.json; then
                # Skip if test script is just "echo" or placeholder
                test_script=$(grep '"test"' package.json | head -1)
                if [[ "$test_script" != *"echo"* ]] && [[ "$test_script" != *"no test"* ]]; then
                    echo "Testing: $dir"
                    echo "Running npm test..."
                    if ! npm test 2>&1; then
                        echo "npm test failed in $dir"
                        ((FAILED++))
                    fi
                    ((TESTS_RUN++))
                else
                    echo "Skipping $dir (no real test script)"
                fi
            else
                echo "No test script in $dir"
            fi

            cd - > /dev/null
        fi
    done < <(find "$PROJECT_ROOT" -name "package.json" -type f -not -path "*/node_modules/*" -print0 2>/dev/null)
    echo ""
fi

# API Tests (if they exist)
if [ -d "$PROJECT_ROOT/tests/api" ]; then
    echo "--- API Tests ---"

    for service_dir in "$PROJECT_ROOT/tests/api"/*/; do
        if [ -d "$service_dir" ]; then
            service_name=$(basename "$service_dir")
            echo "Running API tests for: $service_name"

            # Look for test scripts
            if [ -f "$service_dir/run-tests.sh" ]; then
                if ! bash "$service_dir/run-tests.sh" 2>&1; then
                    echo "API tests failed for $service_name"
                    ((FAILED++))
                fi
                ((TESTS_RUN++))
            elif [ -f "$service_dir/package.json" ]; then
                cd "$service_dir"
                if ! npm test 2>&1; then
                    echo "API tests failed for $service_name"
                    ((FAILED++))
                fi
                ((TESTS_RUN++))
                cd - > /dev/null
            fi
        fi
    done
    echo ""
fi

echo "========================================"
echo "Tests run: $TESTS_RUN"

if [ "$TESTS_RUN" -eq 0 ]; then
    echo "WARNING: No tests were run"
    exit 0
fi

if [ "$FAILED" -eq 0 ]; then
    echo "All tests passed!"
    exit 0
else
    echo "Tests failed: $FAILED test suites had failures"
    exit 1
fi
