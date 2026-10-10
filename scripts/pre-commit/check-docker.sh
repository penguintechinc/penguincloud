#!/bin/bash
# Docker Build & Run Pre-Commit Checks
# Validates Dockerfiles and tests container builds

set -e

PROJECT_ROOT="${1:-.}"

echo "Docker Build & Run Pre-Commit Checks"
echo "====================================="
echo "Project: ${PROJECT_ROOT}"
echo ""

FAILED=0

# Find Dockerfiles
DOCKERFILES=()
while IFS= read -r -d '' dockerfile; do
    DOCKERFILES+=("$dockerfile")
done < <(find "$PROJECT_ROOT" -name "Dockerfile" -type f -print0 2>/dev/null)

if [ ${#DOCKERFILES[@]} -eq 0 ]; then
    echo "No Dockerfiles found. Skipping."
    exit 0
fi

echo "Found Dockerfiles:"
printf '%s\n' "${DOCKERFILES[@]}"
echo ""

# Lint Dockerfiles
echo "--- Dockerfile Linting ---"

if command -v hadolint &> /dev/null; then
    echo "Running hadolint..."
    for dockerfile in "${DOCKERFILES[@]}"; do
        echo "Linting $dockerfile..."
        if ! hadolint "$dockerfile" 2>&1; then
            echo "hadolint found issues in $dockerfile"
            ((FAILED++))
        fi
    done
else
    echo "hadolint not installed, skipping Dockerfile linting"
fi

echo ""
echo "--- Base Image Verification ---"

for dockerfile in "${DOCKERFILES[@]}"; do
    echo "Checking $dockerfile..."

    # Check for debian-slim base (not alpine)
    if grep -qE "^FROM.*alpine" "$dockerfile"; then
        echo "WARNING: $dockerfile uses alpine base image. Use debian-slim instead."
        ((FAILED++))
    fi

    # Verify slim images are used
    if grep -qE "^FROM.*(python|node|golang)" "$dockerfile"; then
        if ! grep -qE "^FROM.*(slim|bookworm-slim|bullseye-slim)" "$dockerfile"; then
            echo "WARNING: $dockerfile may not be using slim base. Consider using -slim variant."
        fi
    fi
done

echo ""
echo "--- Docker Build Test ---"

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Docker not available, skipping build test"
else
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        echo "Docker daemon not running, skipping build test"
    else
        for dockerfile in "${DOCKERFILES[@]}"; do
            dir=$(dirname "$dockerfile")
            name=$(basename "$dir")
            tag="pre-commit-test-${name}:latest"

            echo "Building $dockerfile as $tag..."

            if ! docker build -t "$tag" -f "$dockerfile" "$dir" 2>&1; then
                echo "Docker build failed for $dockerfile"
                ((FAILED++))
            else
                echo "Build successful: $tag"

                # Quick run test (start and immediately stop)
                echo "Testing container startup..."
                container_id=$(docker run -d --rm "$tag" sleep 5 2>/dev/null || true)
                if [ -n "$container_id" ]; then
                    # Give it a moment to start
                    sleep 2
                    # Check if still running (didn't crash immediately)
                    if docker ps -q --filter "id=$container_id" | grep -q .; then
                        echo "Container started successfully"
                        docker stop "$container_id" > /dev/null 2>&1 || true
                    else
                        echo "WARNING: Container may have exited unexpectedly"
                    fi
                fi

                # Cleanup test image
                docker rmi "$tag" > /dev/null 2>&1 || true
            fi
            echo ""
        done
    fi
fi

# Docker Compose check
echo "--- Docker Compose Validation ---"

COMPOSE_FILES=()
while IFS= read -r -d '' composefile; do
    COMPOSE_FILES+=("$composefile")
done < <(find "$PROJECT_ROOT" -name "docker-compose*.yml" -o -name "docker-compose*.yaml" -type f -print0 2>/dev/null)

if [ ${#COMPOSE_FILES[@]} -gt 0 ]; then
    for composefile in "${COMPOSE_FILES[@]}"; do
        echo "Validating $composefile..."
        if command -v docker-compose &> /dev/null; then
            if ! docker-compose -f "$composefile" config > /dev/null 2>&1; then
                echo "docker-compose config validation failed for $composefile"
                ((FAILED++))
            else
                echo "Valid: $composefile"
            fi
        elif docker compose version &> /dev/null; then
            if ! docker compose -f "$composefile" config > /dev/null 2>&1; then
                echo "docker compose config validation failed for $composefile"
                ((FAILED++))
            else
                echo "Valid: $composefile"
            fi
        else
            echo "docker-compose not available, skipping validation"
        fi
    done
else
    echo "No docker-compose files found"
fi

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
    echo "All Docker checks passed!"
    exit 0
else
    echo "Docker checks failed: $FAILED issues found"
    exit 1
fi
