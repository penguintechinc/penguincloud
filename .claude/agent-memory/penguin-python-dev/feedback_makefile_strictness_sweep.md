---
name: feedback-makefile-strictness-sweep
description: Converting a Makefile's `command -v TOOL || true` guard to fail loud is not safe by default — test each tool against the real repo first, because pre-existing debt (691 flutter findings, 258 ruff findings, shellcheck scanning .venv) will make the target permanently red if you don't scope it
metadata:
  type: feedback
---

A coordinator fix-round asked to stop `make lint`/`make test-security` from
silently reporting success when a linter binary was missing (the guard was
`if command -v TOOL; then check || true; fi` — missing binary AND real
findings both get swallowed). The naive fix — just drop `|| true`
everywhere the shape appears — detonates on contact with this repo:

- `cd services/mobile && flutter analyze` has **691 pre-existing errors**
  (real Flutter/Dart code, not scaffold). Making `make lint` require this to
  pass would make it permanently red for reasons with zero relation to the
  task.
- `ruff check .` (whole-repo, unscoped) surfaces **258 pre-existing
  findings**, concentrated in `tests/api/` (136) and
  `services/portal-api/app/killkrill_client/` (47) — genuinely first-party
  code, not vendored, confirmed via
  `ruff check . | grep -oE ... | sort -u | grep venv`.
- `find . -name "*.sh" | xargs shellcheck` (no `.venv` exclusion) scans
  **vendored third-party scripts inside `.venv/lib/.../site-packages/`**
  (e.g. `tqdm/completion.sh`) and reports their findings as if they were
  this repo's own.
- `gitleaks detect --source . --no-git` (unscoped working-tree scan, not
  `--staged`) flags **8 hits, all in `docs/standards/*.md` and
  `docs/API.md`** — illustrative API-key/curl-auth-header examples in files
  this repo is not allowed to edit (see repo `CLAUDE.md`). Making this
  strict would make `test-security` permanently unfixable without either a
  forbidden edit or a `.gitleaksignore`.

**How to apply:**
- Before removing `|| true` from ANY existing Makefile check, run the exact
  underlying command against the real repo tree first and read the output.
  "This guard is buggy" does not imply "the thing it's guarding is clean."
- Distinguish two separate bugs that look identical in the diff: (a) tool
  MISSING → converted to false success (the actual reported bug — fix
  everywhere, it's unambiguous), vs (b) tool PRESENT and reports real
  findings → currently swallowed by `|| true` on the check itself (a
  separate, much bigger judgment call — only flip this if you've verified
  the check is currently clean or the debt is genuinely in scope to
  surface).
- Fix pattern that separates the two cleanly: find the relevant files
  first (`find . -name "Dockerfile*" ...`); only if non-empty, require the
  tool (`command -v TOOL || { echo ...; exit 1; }`) and run it. A machine
  with no Go code doesn't need golangci-lint installed; one with
  Dockerfiles does need hadolint.
- Match the ACTUAL gate's flags exactly when you do make something strict
  — `shellcheck --severity=warning` (not default `style`) and excluding
  `.venv`/`node_modules`, because that's what the pre-commit hook already
  enforces; a Makefile target that disagrees with the real gate is worse
  than one that does nothing.
- `[ -f/-d PATH ]`-guarded blocks (eslint on `web/package.json`, flutter on
  `services/mobile/`) are a DIFFERENT pattern from `command -v TOOL` —
  don't conflate "missing directory means nothing to check" with "missing
  binary means the check never ran." Only the latter is the reported bug.
- If a tool you're about to point a Makefile target at (e.g. `ruff`) isn't
  actually installed anywhere reachable — check with
  `ls .venv/bin/ | grep TOOL` or just try running it — before writing the
  target. `ruff` was never in `services/portal-api/requirements.in`; it
  only existed in the pre-commit hook's own isolated mirror env. Declaring
  it pinned to the exact same version as `.pre-commit-config.yaml`'s
  `ruff-pre-commit` rev (not just "latest") keeps the Makefile target and
  the real gate from ever disagreeing — same principle as the mypy-hook
  venv fix, applied to a second tool.

See [[env-toolchain-constraints]], [[feedback-gates-block-push]],
[[feedback-precommit-all-files-blast-radius]].
