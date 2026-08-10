#!/usr/bin/env bash
# run-pip-audit.sh — audit tracked requirements files (advisory).
#
# The old hand-written hook ran bare `pip-audit -q` with no `-r` flag,
# which audits whatever happens to be installed in the *machine's* Python
# environment rather than this repo's actual dependencies — on a dev
# workstation that silently reports unrelated system-package CVEs instead
# of this repo's. Scoped here to the repo's own requirements files instead.
#
# Non-blocking, matching the old hook's `|| true` — kept advisory rather
# than newly gating pushes on a finding class nobody has triaged yet, and
# because pip-audit's --require-hashes resolution has a known false-failure
# here: sqlalchemy's optional `greenlet != 0.4.17` extra constraint isn't
# itself hash-pinned, which trips pip's --require-hashes dependency
# resolution on requirements.txt regardless of --no-deps.
set -uo pipefail

for req in requirements.txt services/portal-api/requirements.txt; do
  [ -f "$req" ] || continue
  echo "pip-audit: $req"
  pip-audit -r "$req" || echo "  (pip-audit reported an issue for $req — see output above)"
done

exit 0
