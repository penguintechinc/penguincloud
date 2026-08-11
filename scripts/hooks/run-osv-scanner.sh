#!/usr/bin/env bash
# run-osv-scanner.sh — scan tracked dependency lockfiles with osv-scanner.
#
# osv-scanner's own directory walk cannot parse the .git pointer file inside
# a git worktree, so targets are enumerated explicitly via `git ls-files`
# instead of letting it walk the tree itself (see the now-superseded
# fix/osv-scanner-worktree-compat branch for the same finding).
set -euo pipefail

OSV_TARGETS=$(git ls-files | grep -E '(^|/)(requirements[^/]*\.txt|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|go\.sum|Cargo\.lock|pubspec\.lock|composer\.lock|Gemfile\.lock)$' || true)

if [ -z "$OSV_TARGETS" ]; then
  echo "osv-scanner: no tracked lockfiles found, skipping"
  exit 0
fi

# Intentional word-splitting: expands to `-L file1 -L file2 ...` as
# separate arguments, matching osv-scanner's multi-target invocation.
# shellcheck disable=SC2046,SC2086
osv-scanner $(printf -- '-L %s ' $OSV_TARGETS)
