#!/usr/bin/env bash
# run-mypy.sh — run mypy from the repo's own pinned venv, never $PATH.
#
# The hook used to be `entry: mypy --ignore-missing-imports` with
# `language: system`, which resolves `mypy` (and everything it imports,
# including `penguin_dal`) off whatever happens to be on the developer's
# PATH/PYTHONPATH. On this machine that's an EDITABLE checkout of
# ~/code/penguin-libs, not the hash-pinned `penguin-dal` this repo actually
# ships — and that checkout drifts branch-to-branch independently of this
# repo. `db.executesql(...)` genuinely type-checks differently depending on
# which one answers the import: the pinned release types it properly, an
# older editable checkout infers pydal's dynamic `TableProxy` and needs a
# suppression. A developer, this hook, and CI must not be able to disagree
# about whether a `# type: ignore` is needed — the fix is making every one
# of them resolve `penguin_dal` the same way: this repo's own `.venv`
# (`make venv-portal-api`), never the ambient environment.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
VENV_MYPY="$REPO_ROOT/.venv/bin/mypy"

if [ ! -x "$VENV_MYPY" ]; then
  echo "mypy hook: $VENV_MYPY not found. Run 'make venv-portal-api' first." >&2
  exit 1
fi

exec "$VENV_MYPY" --ignore-missing-imports "$@"
