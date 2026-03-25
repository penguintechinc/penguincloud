#!/usr/bin/env bash
set -euo pipefail

# 03-hardcoded-check.sh - CRITICAL test for hardcoded IPs and ports
# Scans deployed resources and source config for hardcoded values

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

# Configuration
PROJECT_NAME="${PROJECT_NAME:-project-template}"
NAMESPACE="${PROJECT_NAME}-beta"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Patterns to detect
LOCALHOST_PATTERN='(localhost|127\.0\.0\.1)'
PRIVATE_IP_PATTERN='192\.168\.[0-9]+\.[0-9]+'
ZERO_IP_PATTERN='0\.0\.0\.0'
HARDCODED_PORT_PATTERN=':(5000|8080|3000|5432|6379)[^0-9]'

VIOLATIONS_FOUND=0
TEMP_FILE=$(mktemp)

log_info "Scanning for hardcoded IPs and ports in beta environment"
log_info "Namespace: ${NAMESPACE}"

# Function to check for violations
check_violations() {
    local resource_type=$1
    local output=$2
    local description=$3

    log_info "Checking ${description}..."

    # Check for localhost/127.0.0.1
    if echo "$output" | grep -iE "$LOCALHOST_PATTERN" | grep -v "# " | grep -v "metadata:" > "$TEMP_FILE" 2>/dev/null; then
        if [[ -s "$TEMP_FILE" ]]; then
            # Filter out legitimate bind addresses (0.0.0.0:port is OK for services)
            if echo "$output" | grep -E "$LOCALHOST_PATTERN" | grep -vE "bind|listen|BIND|LISTEN" > /dev/null 2>&1; then
                log_fail "Found localhost/127.0.0.1 in ${description}"
                grep -iE "$LOCALHOST_PATTERN" <<< "$output" | grep -v "# " | grep -v "metadata:"
                VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
            fi
        fi
    fi

    # Check for 192.168.x.x
    if echo "$output" | grep -E "$PRIVATE_IP_PATTERN" | grep -v "# " | grep -v "metadata:" > "$TEMP_FILE" 2>/dev/null; then
        if [[ -s "$TEMP_FILE" ]]; then
            log_fail "Found private IP (192.168.x.x) in ${description}"
            grep -E "$PRIVATE_IP_PATTERN" <<< "$output" | grep -v "# " | grep -v "metadata:"
            VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
        fi
    fi

    # Check for hardcoded ports in connection strings
    if echo "$output" | grep -E "http://.*$HARDCODED_PORT_PATTERN" > "$TEMP_FILE" 2>/dev/null; then
        if [[ -s "$TEMP_FILE" ]]; then
            log_fail "Found hardcoded port in connection string in ${description}"
            grep -E "http://.*$HARDCODED_PORT_PATTERN" <<< "$output"
            VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
        fi
    fi
}

# 1. Check ConfigMaps
log_info "Scanning ConfigMaps..."
if CONFIGMAPS=$(kubectl get configmaps -n "$NAMESPACE" -o yaml 2>/dev/null); then
    check_violations "configmap" "$CONFIGMAPS" "ConfigMaps"
else
    log_warn "No ConfigMaps found or unable to retrieve"
fi

# 2. Check Deployments environment variables
log_info "Scanning Deployments..."
if DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" -o yaml 2>/dev/null); then
    check_violations "deployment" "$DEPLOYMENTS" "Deployments"
else
    log_warn "No Deployments found or unable to retrieve"
fi

# 3. Check StatefulSets
log_info "Scanning StatefulSets..."
if STATEFULSETS=$(kubectl get statefulsets -n "$NAMESPACE" -o yaml 2>/dev/null); then
    check_violations "statefulset" "$STATEFULSETS" "StatefulSets"
else
    log_warn "No StatefulSets found or unable to retrieve"
fi

# 4. Check Services (should use DNS names, not IPs)
log_info "Scanning Services..."
if SERVICES=$(kubectl get services -n "$NAMESPACE" -o yaml 2>/dev/null); then
    # Services can have clusterIP, but check annotations and labels
    if echo "$SERVICES" | grep -E "$LOCALHOST_PATTERN" | grep -v "clusterIP" | grep -v "# " > "$TEMP_FILE" 2>/dev/null; then
        if [[ -s "$TEMP_FILE" ]]; then
            log_fail "Found localhost in Service definitions"
            cat "$TEMP_FILE"
            VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
        fi
    fi
fi

# 5. Check Secrets (base64 decoded)
log_info "Scanning Secrets (decoded)..."
if SECRETS=$(kubectl get secrets -n "$NAMESPACE" -o json 2>/dev/null); then
    # Decode and check secret values
    SECRET_NAMES=$(echo "$SECRETS" | jq -r '.items[].metadata.name' 2>/dev/null || echo "")
    for secret_name in $SECRET_NAMES; do
        if [[ -n "$secret_name" ]]; then
            SECRET_DATA=$(kubectl get secret "$secret_name" -n "$NAMESPACE" -o json 2>/dev/null | jq -r '.data | to_entries[] | .value' 2>/dev/null || echo "")
            for encoded_value in $SECRET_DATA; do
                if [[ -n "$encoded_value" ]]; then
                    decoded_value=$(echo "$encoded_value" | base64 -d 2>/dev/null || echo "")
                    if echo "$decoded_value" | grep -qE "$LOCALHOST_PATTERN|$PRIVATE_IP_PATTERN"; then
                        log_fail "Found hardcoded IP in secret: ${secret_name}"
                        VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
                    fi
                fi
            done
        fi
    done
fi

# 6. Check source config files for hardcoded values
log_info "Scanning source configuration files..."
CONFIG_DIRS=(
    "${REPO_ROOT}/k8s/helm/${PROJECT_NAME}/values-beta.yaml"
    "${REPO_ROOT}/k8s/helm/${PROJECT_NAME}/templates"
)

for config_path in "${CONFIG_DIRS[@]}"; do
    if [[ -e "$config_path" ]]; then
        log_info "Scanning: ${config_path}"

        if [[ -f "$config_path" ]]; then
            # Single file
            if grep -E "$LOCALHOST_PATTERN|$PRIVATE_IP_PATTERN" "$config_path" | grep -v "# " | grep -v "example" | grep -v "TODO" > "$TEMP_FILE" 2>/dev/null; then
                if [[ -s "$TEMP_FILE" ]]; then
                    log_fail "Found hardcoded IP in config file: ${config_path}"
                    cat "$TEMP_FILE"
                    VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
                fi
            fi
        elif [[ -d "$config_path" ]]; then
            # Directory - scan recursively
            if grep -rE "$LOCALHOST_PATTERN|$PRIVATE_IP_PATTERN" "$config_path" | grep -v "# " | grep -v "example" | grep -v "TODO" | grep -v ".git" > "$TEMP_FILE" 2>/dev/null; then
                if [[ -s "$TEMP_FILE" ]]; then
                    log_fail "Found hardcoded IP in config directory: ${config_path}"
                    cat "$TEMP_FILE"
                    VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
                fi
            fi
        fi
    fi
done

# 7. Verify services are using DNS names
log_info "Verifying DNS-based service discovery..."
ENV_VARS=$(kubectl get deployments -n "$NAMESPACE" -o json | jq -r '.items[].spec.template.spec.containers[].env[]? | select(.name | contains("URL") or contains("HOST") or contains("ENDPOINT")) | .value' 2>/dev/null || echo "")

if [[ -n "$ENV_VARS" ]]; then
    while IFS= read -r env_value; do
        if [[ -n "$env_value" ]]; then
            # Check if it contains an IP instead of a service name
            if echo "$env_value" | grep -qE "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"; then
                log_fail "Found IP address in service URL/HOST env var: ${env_value}"
                VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
            fi

            # Verify it uses service DNS pattern (service-name or service-name.namespace.svc.cluster.local)
            if echo "$env_value" | grep -qE "http://[a-z0-9-]+(:|\.)"; then
                log_pass "Found DNS-based service reference: ${env_value}"
            fi
        fi
    done <<< "$ENV_VARS"
fi

# Cleanup
rm -f "$TEMP_FILE"

# Final verdict
echo ""
log_info "Hardcoded check summary:"
echo "  Violations found: ${VIOLATIONS_FOUND}"

if [[ $VIOLATIONS_FOUND -gt 0 ]]; then
    log_fail "Hardcoded IP/port check FAILED - found ${VIOLATIONS_FOUND} violation(s)"
    log_info "Beta environment must use DNS-based service discovery"
    log_info "Examples of correct patterns:"
    log_info "  - http://flask-backend:5000"
    log_info "  - http://go-backend.${NAMESPACE}.svc.cluster.local:8080"
    log_info "  - postgresql:5432"
    exit 1
else
    log_pass "No hardcoded IPs or ports found"
    log_pass "All services using DNS-based discovery"
    exit 0
fi
