---
name: feedback-gates-block-push
description: Which penguincloud pre-commit/pre-push gates silently block a commit or push, and the accepted (non-suppression) fix for each
metadata:
  type: feedback
---

The git hooks block commits and pushes on findings that are easy to mistake
for a successful run — `git commit` prints scanner output and the commit
simply does not exist afterwards. **Always re-check `git log --oneline -1`
and `git status -sb` after committing or pushing**; a push that prints
remote Dependabot chatter may still have failed.

**Why:** several gates emit a wall of PASSED output with one FAILED line
buried in it, and the hook's non-zero exit is the only real signal.

**How to apply** — gates that fired during Task 3, and the fix each accepts.
Suppression/allowlisting is never the answer; each was fixed at source:

| Gate | Rejects | Accepted fix |
|---|---|---|
| `gitleaks protect --staged` | High-entropy string literals **in test files** (e.g. `"sk-live-…"` as a fake credential) | Assemble the fake secret from low-entropy words: `"-".join(("not","a","real","credential"))`. Allowlisting the file would blind the scanner to a real key landing there later. |
| `npm audit` (pre-push) | Any advisory, including **transitive dev-only** deps | Add an `overrides` entry at an EXACT version. A range reintroduces the drift the pin prevents. |
| `checkov --framework openapi` | `CKV_OPENAPI_21` — arrays without `maxItems` | Declare a bound in the spec generator, documented against the real invariant that bounds it. |
| `yamllint` | Generated YAML's sequence indentation; unquoted `off` in `.spectral.yaml` (truthy rule) | Indenting `yaml.Dumper` subclass; quote `"off"`. |
| `prettier --check` (webui) | `openapi-typescript` output is not prettier-formatted | Chain `prettier --write` into the `generate:api` script so regeneration is byte-reproducible. |
| `mypy` on staged files | Missing third-party stubs; `list.append()` used for its return value; subclassing an `Any` base; **assigning to a module attribute in a test** (`app.proxy.get_transport = fake` → `does not explicitly export attribute`) | Declare stubs + scoped `mypy.ini` section; use a named recorder class instead of `(list.append(x), Response())[1]`; patch via `monkeypatch.setattr("app.proxy.get_transport", …)` (string form), never attribute assignment. |

Spectral is NOT run by the hooks — it is wired into `make lint` via
`make openapi-lint`. Run it explicitly before claiming the spec is clean.

## Since PR #18 the hooks are the pre-commit FRAMEWORK, and ruff replaced flake8

`.pre-commit-config.yaml` + `pyproject.toml` arrived on `v0.1.x`. The hooks
live in the SHARED git dir, so they apply to every worktree — including
branches that predate the config, where `pre-commit` then fails with
"missing config" and blocks the push. Fix by merging the release branch
(required for the green gate anyway), never by bypassing.

| Gate | Where | Notes |
|---|---|---|
| `ruff` + `ruff-format` | pre-commit, STAGED files only | pinned **v0.8.4** — a newer local ruff drops rules it still enforces (e.g. `UP038`). Check against the pin, not `$PATH` |
| `mypy` | pre-commit, staged files | passes |
| bandit, trivy fs/config, osv-scanner, checkov, k8s-security, npm audit, trufflehog | pre-push, whole repo | slow (~2 min); pip-audit is advisory |

**`flake8` is no longer the gate; ruff is, and its `select` includes `S`.**
Before the `tests/** = ["S101"]` per-file-ignore landed, ruff failed on any
commit staging any test file (373 `assert` findings suite-wide) — i.e. no
test in the repo could be changed. If you hit a rule that makes a whole
tree uncommittable, the fix is a narrow `per-file-ignores`, justified
against how the repo already scopes the same class of rule (bandit runs
`-ll -r` over the app tree, never tests).

Measure your ruff delta against `origin/v0.1.x` versions of the same files
before reformatting anything — every file in the repo is non-compliant
(an untouched test file: 51 findings), so absolute counts mean nothing.

**`black` and `isort` contradict each other in this repo** and neither is
clean at any recent baseline (at `c6db2dd2`: 19 black failures, 31 isort).
Running `isort` on a file makes `black` want to reformat it, and vice versa.
Neither is run by the hooks — **`flake8` is the gate that actually blocks**.

**How to apply:** keep touched files **black-clean** (the convention every
Phase-3 file follows) and accept the isort finding. Measure your delta
rather than the absolute count — stash your work, record the failing-file
list at HEAD, restore, diff — then format only the files YOU added to the
list. Reformatting the pre-existing 19 buries the review diff of a
security-fix branch in unrelated churn.

See [[env-toolchain-constraints]].

## `git commit` with unstaged sibling changes can silently lose them

When you `git add` a subset of files and commit (deliberately splitting one
logical change across several commits), pre-commit's "Stashing unstaged
files" step hid the REST of the working tree during the hook run, then
printed `[INFO] Restored changes from <patch>` — but on Task 6 the restore
left every unstaged file (`models.py`, `requirements.in/.txt`,
`conftest.py`, `app/__init__.py`, `background.py`, `pyproject.toml`,
`docs/APP_STANDARDS.md`, `Dockerfile`, `openapi/v1.yaml`, `portalPaths.ts`,
`schema.d.ts`) reverted to HEAD with **no error printed** — the commit
itself succeeded and looked completely normal. Only `git diff`/`git status`
immediately after revealed the loss.

**The patch survives even when the restore doesn't**: pre-commit writes it
to `~/.cache/pre-commit/patch<epoch>-<pid>` before attempting the stash pop,
and does NOT delete it on a botched restore. `git apply --check <patch>`
then `git apply <patch>` recovered everything byte-for-byte.

**Third incident, confirmed by another agent's own diagnosis: this cache
directory is SHARED across worktrees and sessions, not scoped to one.**
During a later Task 6 fix wave, my uncommitted edit vanished again — this
time with `git status --porcelain` and `git diff` both coming back fully
EMPTY (not "reverted to a stale patch", just gone), traced via `git reflog`
to a `reset: moving to HEAD` I never issued. Root cause per the other
agent working in a DIFFERENT worktree of the same repo at the same time:
their own pre-commit run picked up a stray patch of MINE out of the shared
`~/.cache/pre-commit/`, correctly recognised it wasn't theirs, and
preserved it as `git stash@{0}` (stashes are also NOT worktree-scoped —
`refs/stash` is one stack shared by every worktree of a repo) rather than
discarding it. Recovered via `git stash show -p stash@{0}` (inspect before
applying — it was captured mid-edit and can contain a deliberately-broken
state, e.g. a line disabled specifically to prove a regression test goes
red) and redoing the edits by hand from that inspection, not a blind
`stash pop`.

**How to apply, given the cache is shared:**
- Expect this class of failure to recur in ANY multi-agent/multi-worktree
  session on this machine — it is not a one-off fluke, it is a property of
  where the tool puts its temp files.
- `git status --porcelain` fully empty after an edit you know you made is
  the signature of THIS variant (vs. the single-worktree case above, which
  reverts to a stale-but-present patch). Check `git reflog` for an
  unexplained `reset` before assuming your own tooling is broken.
- Check `git stash list` for an entry labelled around "leaked" / "not
  mine" / "precommit" before assuming work is actually lost — another
  agent may have already rescued it for you.
- Commit and push MORE frequently when working in a shared worktree,
  specifically to shrink the window where uncommitted work can be caught
  in someone else's pre-commit run.

**How to apply:**
- After ANY commit that leaves other files unstaged, immediately
  `git status --porcelain` and diff a couple of the files you know you'd
  edited — don't trust the hook's own "Restored changes" message.
- If something is missing, look at the hook's own stdout for the stash
  patch path (`[INFO] Stashing unstaged files to <path>`) before it scrolls
  away, or `ls -t ~/.cache/pre-commit/patch* | head -1` for the most recent
  one — then `git apply` it.
- Cheapest prevention: `git add -A` everything you intend across the whole
  multi-commit sequence into the index first (or just commit the untouched
  files' state is irrelevant to), then use `git restore --staged` to peel
  files back out per commit, rather than incrementally `git add`ing more
  while earlier commits still leave siblings unstaged — untested here, but
  removes the stash step's opportunity to run at all mid-sequence.
