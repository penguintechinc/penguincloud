#!/usr/bin/env bash
set -euo pipefail

# 01-deploy-helm.sh - Deploy Helm chart with beta values

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

# Configuration
PROJECT_NAME="${PROJECT_NAME:-project-template}"
NAMESPACE="${PROJECT_NAME}-beta"
RELEASE_NAME="${PROJECT_NAME}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HELM_DIR="${REPO_ROOT}/k8s/helm/${PROJECT_NAME}"
VALUES_FILE="${HELM_DIR}/values-beta.yaml"

log_info "Deploying Helm chart for beta environment"
log_info "Namespace: ${NAMESPACE}"
log_info "Release: ${RELEASE_NAME}"
log_info "Helm directory: ${HELM_DIR}"

# Verify Helm chart exists
if [[ ! -d "$HELM_DIR" ]]; then
    log_fail "Helm chart directory not found: ${HELM_DIR}"
    exit 1
fi

if [[ ! -f "${HELM_DIR}/Chart.yaml" ]]; then
    log_fail "Chart.yaml not found in: ${HELM_DIR}"
    exit 1
fi

if [[ ! -f "$VALUES_FILE" ]]; then
    log_fail "Beta values file not found: ${VALUES_FILE}"
    exit 1
fi

log_info "Helm chart directory verified"

# Create namespace if it doesn't exist
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    log_info "Creating namespace: ${NAMESPACE}"
    kubectl create namespace "$NAMESPACE"
    log_pass "Namespace created"
else
    log_info "Namespace already exists: ${NAMESPACE}"
fi

# Update Helm dependencies
log_info "Updating Helm dependencies..."
if ! helm dependency update "$HELM_DIR"; then
    log_fail "Failed to update Helm dependencies"
    exit 1
fi
log_pass "Helm dependencies updated"

# Deploy with Helm
log_info "Deploying Helm chart..."
log_info "Command: helm upgrade --install ${RELEASE_NAME} ${HELM_DIR} -n ${NAMESPACE} -f ${VALUES_FILE} --wait --timeout 5m --create-namespace"

if helm upgrade --install "$RELEASE_NAME" "$HELM_DIR" \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --wait \
    --timeout 5m \
    --create-namespace; then
    log_pass "Helm chart deployed successfully"
else
    log_fail "Helm deployment failed"
    log_info "Showing pod status for debugging:"
    kubectl get pods -n "$NAMESPACE" || true
    exit 1
fi

# Verify deployment
log_info "Verifying deployment..."
if helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
    log_pass "Release ${RELEASE_NAME} is deployed"
else
    log_fail "Release ${RELEASE_NAME} not found"
    exit 1
fi

# Show deployed resources
log_info "Deployed resources:"
kubectl get all -n "$NAMESPACE"

log_pass "Helm deployment completed successfully"
exit 0
