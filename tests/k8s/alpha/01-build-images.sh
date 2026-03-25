#!/usr/bin/env bash
set -euo pipefail

# Build Docker images for all services and import to microk8s

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_NAME="$(basename "$REPO_ROOT")"
TAG="alpha"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
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

build_and_import() {
    local service="$1"
    local service_dir="$REPO_ROOT/$service"
    local image_name="${PROJECT_NAME}/${service}:${TAG}"

    if [[ ! -d "$service_dir" ]]; then
        log_info "Service directory not found: $service_dir (skipping)"
        return 0
    fi

    if [[ ! -f "$service_dir/Dockerfile" ]]; then
        log_info "No Dockerfile found for $service (skipping)"
        return 0
    fi

    log_info "Building $service..."
    if docker build -t "$image_name" "$service_dir"; then
        log_pass "Built $image_name"
    else
        log_fail "Failed to build $image_name"
        return 1
    fi

    log_info "Importing $image_name to microk8s..."
    if docker save "$image_name" | microk8s ctr image import -; then
        log_pass "Imported $image_name to microk8s"
    else
        log_fail "Failed to import $image_name to microk8s"
        return 1
    fi
}

main() {
    log_info "Building Docker images for $PROJECT_NAME (tag: $TAG)"
    log_info "Repository root: $REPO_ROOT"

    # Build each service
    build_and_import "flask-backend"
    build_and_import "go-backend"
    build_and_import "webui"

    log_pass "All images built and imported successfully"

    # Verify images in microk8s
    log_info "Verifying images in microk8s..."
    microk8s ctr images ls | grep "$PROJECT_NAME" || true
}

main "$@"
