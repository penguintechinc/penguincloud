#!/bin/bash
# Node.js/React Pre-Commit Checks
# Runs linting, security, and build checks for Node.js code

set -e

PROJECT_ROOT="${1:-.}"
NODE_DIRS=()

echo "Node.js/React Pre-Commit Checks"
echo "================================"
echo "Project: ${PROJECT_ROOT}"
echo ""

# Find Node.js directories (directories with package.json)
while IFS= read -r -d '' pkg; do
    dir=$(dirname "$pkg")
    # Skip node_modules
    if [[ "$dir" != *"node_modules"* ]]; then
        NODE_DIRS+=("$dir")
    fi
done < <(find "$PROJECT_ROOT" -name "package.json" -type f -not -path "*/node_modules/*" -print0 2>/dev/null)

if [ ${#NODE_DIRS[@]} -eq 0 ]; then
    echo "No Node.js projects found. Skipping."
    exit 0
fi

echo "Found Node.js directories:"
printf '%s\n' "${NODE_DIRS[@]}"
echo ""

FAILED=0

for dir in "${NODE_DIRS[@]}"; do
    echo "========================================"
    echo "Checking: $dir"
    echo "========================================"
    cd "$dir"

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "Installing dependencies..."
        npm ci --silent 2>&1 || npm install --silent 2>&1 || true
    fi

    # Linting
    echo ""
    echo "--- Linting ---"

    if [ -f "package.json" ] && grep -q '"lint"' package.json; then
        echo "Running npm run lint..."
        if ! npm run lint 2>&1; then
            echo "npm run lint failed"
            ((FAILED++))
        fi
    elif command -v eslint &> /dev/null; then
        echo "Running eslint..."
        if ! npx eslint . --ext .js,.jsx,.ts,.tsx 2>&1; then
            echo "eslint failed"
            ((FAILED++))
        fi
    else
        echo "No linter configured, skipping"
    fi

    # Security
    echo ""
    echo "--- Security (npm audit) ---"
    echo "Running npm audit..."
    if ! npm audit --audit-level=high 2>&1; then
        echo "npm audit found HIGH/CRITICAL vulnerabilities"
        echo "Run 'npm audit fix' to attempt auto-fix"
        ((FAILED++))
    fi

    # Build
    echo ""
    echo "--- Build Check ---"
    if [ -f "package.json" ] && grep -q '"build"' package.json; then
        echo "Running npm run build..."
        if ! npm run build 2>&1; then
            echo "npm run build failed"
            ((FAILED++))
        fi
    else
        echo "No build script found, skipping"
    fi

    cd - > /dev/null
done

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
    echo "All Node.js checks passed!"
    exit 0
else
    echo "Node.js checks failed: $FAILED issues found"
    exit 1
fi
