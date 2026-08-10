#!/usr/bin/env bash
# run-eslint-webui.sh — eslint for services/webui, matching the old
# hand-written hook's exact scope (services/webui only, not top-level web/).
#
# pre-commit's `files:` filter already restricts invocations of this hook to
# paths under services/webui/, so every argument is guaranteed to carry that
# prefix; it's stripped before invoking since eslint resolves paths relative
# to its own config root (services/webui), not the repo root.
set -euo pipefail

cd services/webui
args=("$@")
npx --no-install eslint --max-warnings=0 --no-warn-ignored "${args[@]/#services\/webui\//}"
