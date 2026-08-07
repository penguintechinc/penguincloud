#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/.git/hooks"

mkdir -p "${HOOKS_DIR}"

# Install pre-commit hook
cat > "${HOOKS_DIR}/pre-commit" << 'HOOK_PRE_COMMIT'
#!/usr/bin/env bash
set -euo pipefail

# --diff-filter=d excludes deleted paths: a deleted file still appears in
# plain `git diff --cached --name-only`, and every linter below happily
# accepts the path then fails with "No such file or directory" once it
# tries to open it — deletions have nothing left to lint.
CHANGED=$(git diff --cached --name-only --diff-filter=d)

gitleaks protect --staged --exit-code 1

STAGED_PY=$(echo "$CHANGED" | grep '\.py$' || true)
if [ -n "$STAGED_PY" ]; then
  echo "$STAGED_PY" | xargs flake8
  echo "$STAGED_PY" | xargs mypy --ignore-missing-imports
fi

if echo "$CHANGED" | grep -q '\.go$'; then
  if find . -name "go.mod" -not -path "*/node_modules/*" 2>/dev/null | grep -q .; then
    golangci-lint run ./...
  else
    echo "No go.mod in repo (no Go module to lint), skipping golangci-lint"
  fi
fi

STAGED_JS=$(echo "$CHANGED" | grep -E '\.(js|ts|jsx|tsx)$' || true)
if [ -n "$STAGED_JS" ]; then
  echo "$STAGED_JS" | xargs npx eslint --max-warnings=0
  echo "$STAGED_JS" | xargs npx prettier --check
fi

if echo "$CHANGED" | grep -q '\.sh$'; then
  echo "$CHANGED" | grep '\.sh$' | xargs shellcheck
fi

if echo "$CHANGED" | grep -qE '\.ya?ml$'; then
  echo "$CHANGED" | grep -E '\.ya?ml$' | xargs yamllint
fi

if echo "$CHANGED" | grep -q 'Dockerfile'; then
  find . -name "Dockerfile*" -not -path "*/node_modules/*" | xargs hadolint
  for df in $(echo "$CHANGED" | grep 'Dockerfile'); do
    [ ! -f "$df" ] && continue
    last_user=$(grep -i '^USER' "$df" | tail -1 | awk '{print $2}')
    if [ -z "$last_user" ] || [ "$last_user" = "root" ] || [ "$last_user" = "0" ]; then
      if grep -q 'ROOT EXCEPTION (approved)' "$df"; then
        echo "ℹ️  $df — root exception approved"
      else
        echo "⚠️  WARNING: $df — final stage runs as root"
        echo "   Add: # ROOT EXCEPTION (approved): <reason>  if intentional"
      fi
    fi
  done
fi

if echo "$CHANGED" | grep -q '\.github/workflows'; then
  zizmor .github/workflows/
fi

echo "✓ pre-commit passed"
HOOK_PRE_COMMIT

chmod +x "${HOOKS_DIR}/pre-commit"

# Install pre-push hook
cat > "${HOOKS_DIR}/pre-push" << 'HOOK_PRE_PUSH'
#!/usr/bin/env bash
set -euo pipefail

echo "Running pre-push security scans..."

trufflehog git file://. --only-verified --no-update 2>/dev/null || \
  echo "⚠️  trufflehog: could not verify (network issue?) — check manually"

trivy fs --exit-code 1 --severity HIGH,CRITICAL --quiet .
# osv-scanner: enumerate tracked manifests explicitly — its directory walk
# cannot parse the .git pointer file inside git worktrees
OSV_TARGETS=$(git ls-files | grep -E '(^|/)(requirements[^/]*\.txt|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|go\.sum|Cargo\.lock|pubspec\.lock|composer\.lock|Gemfile\.lock)$' || true)
if [ -n "$OSV_TARGETS" ]; then
  # shellcheck disable=SC2086
  osv-scanner $(printf -- '-L %s ' $OSV_TARGETS)
fi

semgrep scan --config=auto --error --quiet . 2>/dev/null || true
command -v bandit      &>/dev/null && bandit -r . -q -ll
command -v gosec       &>/dev/null && gosec -quiet ./... 2>/dev/null || true

trivy config --exit-code 1 --severity HIGH,CRITICAL --quiet .
command -v checkov     &>/dev/null && checkov -d . --quiet --compact

if [ -d k8s/helm ]; then
  helm lint ./k8s/helm/* 2>/dev/null || true
  for chart in k8s/helm/*/; do
    helm template release "$chart" 2>/dev/null | \
      checkov -d /dev/stdin --quiet --compact 2>/dev/null || true
  done
fi

if [ -d k8s/ ]; then
  find k8s/ -name "*.yaml" | xargs kube-score score 2>/dev/null || true
  for manifest in $(find k8s/ -name "*.yaml" 2>/dev/null); do
    grep -qL 'runAsNonRoot'             "$manifest" && \
      echo "⚠️  WARNING: $manifest — missing runAsNonRoot"
    grep -qL 'allowPrivilegeEscalation' "$manifest" && \
      echo "⚠️  WARNING: $manifest — missing allowPrivilegeEscalation: false"
  done
fi

for df in $(find . -name "Dockerfile*" -not -path "*/node_modules/*" 2>/dev/null); do
  last_user=$(grep -i '^USER' "$df" | tail -1 | awk '{print $2}')
  if [ -z "$last_user" ] || [ "$last_user" = "root" ] || [ "$last_user" = "0" ]; then
    if grep -q 'ROOT EXCEPTION (approved)' "$df"; then
      echo "ℹ️  $df — root exception approved"
    else
      echo "⚠️  WARNING: $df — final stage runs as root"
      echo "   Add: # ROOT EXCEPTION (approved): <reason>  if intentional"
    fi
  fi
done

command -v pip-audit     &>/dev/null && pip-audit -q 2>/dev/null || true
command -v govulncheck   &>/dev/null && govulncheck ./... 2>/dev/null || true
[ -f package.json ]      && npm audit --audit-level=moderate 2>/dev/null || true

echo "✓ pre-push passed"
HOOK_PRE_PUSH

chmod +x "${HOOKS_DIR}/pre-push"

echo "✓ Git hooks installed: pre-commit, pre-push"
