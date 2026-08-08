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
