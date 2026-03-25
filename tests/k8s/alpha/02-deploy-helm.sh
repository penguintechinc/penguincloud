#!/usr/bin/env bash
set -euo pipefail

# Deploy Helm chart with alpha configuration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_NAME="$(basename "$REPO_ROOT")"
NAMESPACE="${PROJECT_NAME}-alpha"
HELM_DIR="$REPO_ROOT/k8s/helm/$PROJECT_NAME"
RELEASE_NAME="$PROJECT_NAME"

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

main() {
    log_info "Deploying Helm chart for $PROJECT_NAME to alpha environment"
    log_info "Namespace: $NAMESPACE"
    log_info "Helm directory: $HELM_DIR"

    # Verify Helm chart exists
    if [[ ! -d "$HELM_DIR" ]]; then
        log_fail "Helm chart directory not found: $HELM_DIR"
        exit 1
    fi

    if [[ ! -f "$HELM_DIR/Chart.yaml" ]]; then
        log_fail "Chart.yaml not found in $HELM_DIR"
        exit 1
    fi

    # Create namespace if it doesn't exist
    log_info "Creating namespace $NAMESPACE..."
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        log_info "Namespace $NAMESPACE already exists"
    else
        kubectl create namespace "$NAMESPACE"
        log_pass "Created namespace $NAMESPACE"
    fi

    # Update Helm dependencies
    log_info "Updating Helm dependencies..."
    if helm dependency update "$HELM_DIR"; then
        log_pass "Helm dependencies updated"
    else
        log_fail "Failed to update Helm dependencies"
        exit 1
    fi

    # Deploy with Helm
    log_info "Installing/upgrading Helm release: $RELEASE_NAME"

    local values_file="$HELM_DIR/values-alpha.yaml"
    if [[ ! -f "$values_file" ]]; then
        log_info "Alpha values file not found, using default values.yaml"
        values_file="$HELM_DIR/values.yaml"
    fi

    if helm upgrade --install "$RELEASE_NAME" "$HELM_DIR" \
        --namespace "$NAMESPACE" \
        --values "$values_file" \
        --wait \
        --timeout 5m; then
        log_pass "Helm chart deployed successfully"
    else
        log_fail "Helm deployment failed"
        exit 1
    fi

    # Show deployment status
    log_info "Deployment status:"
    kubectl get pods -n "$NAMESPACE"

    log_pass "Helm deployment completed"
}

main "$@"
