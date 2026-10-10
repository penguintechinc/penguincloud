#!/usr/bin/env bash
# run-pip-audit.sh — audit tracked requirements files (advisory).
#
# The old hand-written hook ran bare `pip-audit -q` with no `-r` flag,
# which audits whatever happens to be installed in the *machine's* Python
# environment rather than this repo's actual dependencies — on a dev
# workstation that silently reports unrelated system-package CVEs instead
# of this repo's. Scoped here to the repo's own requirements files instead.
#
# services/portal-api/requirements.txt is the ONLY set this repo ships —
# the stale pre-portal-api root requirements.{in,txt} (py4web/pydal, never
# imported by any service) was removed rather than fixed: it pinned
# `gunicorn` (forbidden — backend-python.md requires hypercorn) and pulled
# in `greenlet` unpinned via sqlalchemy, which made `--require-hashes`
# unresolvable and this scan fail every run with nothing to actually act on.
#
# Non-blocking, matching the old hook's `|| true` — kept advisory rather
# than newly gating pushes on a finding class nobody has triaged yet, and
# because pip-audit's --require-hashes resolution has a known false-failure
# here: sqlalchemy's optional `greenlet != 0.4.17` extra constraint isn't
# itself hash-pinned, which trips pip's --require-hashes dependency
# resolution on requirements.txt regardless of --no-deps.
#
# The path is anchored to the repo root (not relative to cwd) so this
# behaves identically regardless of where it's invoked from. It used to be
# a bare relative path that only worked because pre-commit happens to set
# cwd to the repo root — anywhere else, `[ -f "$req" ]` silently resolved
# false and the hook exited 0 having audited nothing. Fail loud instead,
# matching run-mypy.sh: an unresolvable path is a hook bug, not a "nothing
# to audit" case.
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel)"
req="$repo_root/services/portal-api/requirements.txt"
if [ ! -f "$req" ]; then
  echo "pip-audit hook: $req not found." >&2
  exit 1
fi

echo "pip-audit: $req"
pip-audit -r "$req" || echo "  (pip-audit reported an issue for $req — see output above)"

exit 0
