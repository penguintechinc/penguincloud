#!/bin/bash
# Go Pre-Commit Checks
# Runs linting, security, and build checks for Go code

set -e

PROJECT_ROOT="${1:-.}"
GO_DIRS=()

echo "Go Pre-Commit Checks"
echo "===================="
echo "Project: ${PROJECT_ROOT}"
echo ""

# Find Go directories (directories with go.mod)
while IFS= read -r -d '' gomod; do
    GO_DIRS+=("$(dirname "$gomod")")
done < <(find "$PROJECT_ROOT" -name "go.mod" -type f -print0 2>/dev/null)

# Also check services/go-backend specifically
if [ -d "$PROJECT_ROOT/services/go-backend" ] && [ -f "$PROJECT_ROOT/services/go-backend/go.mod" ]; then
    # Already found via find, skip
    :
elif [ -d "$PROJECT_ROOT/services/go-backend" ]; then
    GO_DIRS+=("$PROJECT_ROOT/services/go-backend")
fi

if [ ${#GO_DIRS[@]} -eq 0 ]; then
    echo "No Go modules found. Skipping."
    exit 0
fi

echo "Found Go directories:"
printf '%s\n' "${GO_DIRS[@]}"
echo ""

FAILED=0

# Linting
echo "--- Linting ---"

for dir in "${GO_DIRS[@]}"; do
    echo "Checking $dir..."
    cd "$dir"

    # go fmt check
    echo "Running go fmt check..."
    if [ -n "$(gofmt -l . 2>/dev/null)" ]; then
        echo "go fmt found unformatted files in $dir"
        gofmt -l .
        ((FAILED++))
    fi

    # go vet
    echo "Running go vet..."
    if ! go vet ./... 2>&1; then
        echo "go vet found issues in $dir"
        ((FAILED++))
    fi

    # golangci-lint (if available)
    if command -v golangci-lint &> /dev/null; then
        echo "Running golangci-lint..."
        if ! golangci-lint run --timeout 5m 2>&1; then
            echo "golangci-lint found issues in $dir"
            ((FAILED++))
        fi
    else
        echo "golangci-lint not installed, skipping"
    fi

    cd - > /dev/null
done

echo ""
echo "--- Security ---"

# gosec
if command -v gosec &> /dev/null; then
    echo "Running gosec..."
    for dir in "${GO_DIRS[@]}"; do
        cd "$dir"
        if ! gosec -quiet -severity high ./... 2>&1; then
            echo "gosec found security issues in $dir"
            ((FAILED++))
        fi
        cd - > /dev/null
    done
else
    echo "gosec not installed, skipping"
fi

echo ""
echo "--- Build Check ---"

for dir in "${GO_DIRS[@]}"; do
    echo "Building $dir..."
    cd "$dir"

    # Download dependencies
    echo "Running go mod download..."
    go mod download 2>&1 || true

    # Build
    echo "Running go build..."
    if ! go build ./... 2>&1; then
        echo "go build failed in $dir"
        ((FAILED++))
    fi

    cd - > /dev/null
done

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "All Go checks passed!"
    exit 0
else
    echo "Go checks failed: $FAILED issues found"
    exit 1
fi
