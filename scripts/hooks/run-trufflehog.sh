#!/usr/bin/env bash
# run-trufflehog.sh — verified-secret scan of git history (advisory).
#
# `trufflehog git file://.` cannot read the .git pointer file inside a git
# worktree ("failed to read index file: open .git: not a directory"), the
# same class of worktree incompatibility already documented for
# osv-scanner. Non-blocking, matching the old hand-written hook exactly —
# it already treated a trufflehog failure as advisory
# (`|| echo "could not verify"`), not a push blocker.
set -uo pipefail

trufflehog git file://. --only-verified --no-update 2>/dev/null || \
  echo "trufflehog: could not verify (network issue, or running inside a git worktree — see script header) — check manually"

exit 0
