#!/bin/bash
# Security Scanning Pre-Commit Checks
# Runs security scanners for all languages

set -e

PROJECT_ROOT="${1:-.}"

echo "Security Pre-Commit Checks"
echo "=========================="
echo "Project: ${PROJECT_ROOT}"
echo ""

FAILED=0

# Python Security
if find "$PROJECT_ROOT" -name "*.py" -type f -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | head -1 | grep -q .; then
    echo "--- Python Security ---"

    # bandit
    if command -v bandit &> /dev/null; then
        echo "Running bandit..."
        if ! bandit -r "$PROJECT_ROOT" -ll -q -x "**/venv/**,**/.venv/**,**/node_modules/**" 2>&1; then
            echo "bandit found security issues"
            FAILED=$((FAILED+1))
        fi
    else
        echo "bandit not installed"
    fi
    echo ""
fi

# Node.js Security
if find "$PROJECT_ROOT" -name "package.json" -type f -not -path "*/node_modules/*" 2>/dev/null | head -1 | grep -q .; then
    echo "--- Node.js Security ---"

    echo "Running npm audit..."
    while IFS= read -r -d '' pkg; do
        dir=$(dirname "$pkg")
        if [[ "$dir" != *"node_modules"* ]]; then
            echo "Checking $dir..."
            cd "$dir"
            if [ -d "node_modules" ] || [ -f "package-lock.json" ]; then
                if ! npm audit --audit-level=high 2>&1; then
                    echo "npm audit found vulnerabilities in $dir"
                    FAILED=$((FAILED+1))
                fi
            fi
            cd - > /dev/null
        fi
    done < <(find "$PROJECT_ROOT" -name "package.json" -type f -not -path "*/node_modules/*" -print0 2>/dev/null)
    echo ""
fi

# Docker Security (Trivy if available)
if find "$PROJECT_ROOT" -name "Dockerfile" -type f 2>/dev/null | head -1 | grep -q .; then
    echo "--- Docker Security ---"

    if command -v trivy &> /dev/null; then
        echo "Running trivy on Dockerfiles..."
        while read -r dockerfile; do
            echo "Scanning $dockerfile..."
            if ! trivy config --severity HIGH,CRITICAL "$dockerfile" 2>&1; then
                echo "trivy found issues in $dockerfile"
                FAILED=$((FAILED+1))
            fi
        done < <(find "$PROJECT_ROOT" -name "Dockerfile" -type f)
    else
        echo "trivy not installed, skipping container scanning"
    fi
    echo ""
fi

echo "========================================"
if [ "$FAILED" -eq 0 ]; then
    echo "All security checks passed!"
    exit 0
else
    echo "Security checks failed: $FAILED issues found"
    exit 1
fi
