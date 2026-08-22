---
name: env-toolchain-constraints
description: Local Python env is PEP 668 externally-managed (pip install fails); penguin-dal editable checkout drifts and breaks 37 tests; repo lints YAML/OpenAPI beyond flake8
metadata:
  type: project
---

The dev machine's Python is an **externally-managed (PEP 668) interpreter**:
`pip install`, `pip install --user`, and `mypy --install-types` all fail. A
new type-stub dependency can be *declared* (requirements.in + `uv pip compile
--generate-hashes`) but cannot be installed locally, so the pre-commit mypy
hook will keep failing on it.

**Why:** `mypy.ini` runs `strict = True` globally, and a missing stub is an
`import-untyped` error, not a warning.

**How to apply:** when adding a dependency whose stubs live in a separate
distribution, declare the stub package AND add a narrow `[mypy-<lib>]
ignore_missing_imports = True` section — `mypy.ini` documents this exact
carve-out and requires it be scoped to the third-party library only, never to
first-party code. If a single line needs it, use a coded `# type: ignore[code]`
with a comment, which the file also sanctions.

`uv` IS available (`~/.local/bin/uv`) and is the required way to recompile
`requirements.txt`.

## penguin-dal is an EDITABLE install of a shared checkout that drifts

`penguin_dal` resolves to `~/code/penguin-libs/packages/python-dal/src`, not
to the hash-pinned PyPI `penguin-dal==0.4.1`. Whatever branch that shared
checkout happens to be on is what penguincloud's tests run against, and other
people/agents switch it.

Seen 2026-08-10: the checkout sat on `fix/aaa-quart-safe-import`, which
predates `AsyncDB.executesql`, giving **37 failures** in
tenancy/resolver/hierarchy/rollup paths (`TableNotFoundError: Table
'executesql' not found`, from `app/tenancy/resolver.py:395`) on a clean
worktree. It looks exactly like a regression from your own work.

**How to apply:** before trusting a baseline, check
`python3 -c "import penguin_dal.db as d; print(hasattr(d.AsyncDB,'executesql'))"`.
If False, restore the released behaviour **without touching the shared
checkout or the system env** — no branch switch, no `--break-system-packages`,
no venv build needed:

```bash
git -C ~/code/penguin-libs archive origin/main packages/python-dal/src \
  | tar -x -C "$SCRATCH/dalmain"
PYTHONPATH=$SCRATCH/dalmain/packages/python-dal/src python3 -m pytest tests -q
```

PYTHONPATH wins over the editable install. This restored the documented
baseline exactly (1190 passed / 12 skipped / 18 xfailed). Run **every** gate
under that PYTHONPATH — pytest, mypy, `make openapi-check` — or they disagree.

**SUPERSEDED 2026-08-11 — prefer `make test-api`.** The archive+PYTHONPATH
dance above is now the fallback, not the first move. `make venv-portal-api`
builds a project-local venv from `services/portal-api/requirements.txt
--require-hashes` (idempotent: ~33s cold, instant warm), and `make test-api`
runs the suite through it, so results no longer depend on the shared
penguin-libs checkout at all — leave that checkout alone entirely. Expected:
**985 passed / 22 skipped / 19 xfailed**. The count differs from the 1190
baseline above because building the venv honestly exposed three deps the suite
had been borrowing from the ambient environment (`quart-schema`, pinned `==0.19.0`
because `app/openapi.py` uses a private API removed later; `greenlet` for
SQLAlchemy's AsyncEngine; `aiosqlite` for penguin-dal's async sqlite dialect),
and 10 tests now `importorskip` on `opentelemetry`/`redis` because they execute
Nest's and Tobogganing's own app code and need *their* deps, not this service's.
See `docs/DEVELOPMENT.md`.

## The isolated venv does NOT fix mypy's drift exposure — only pytest's

`make venv-portal-api`/`make test-api` insulate **pytest** from the ambient
`~/code/penguin-libs` checkout (see above), but the pre-commit **mypy hook is
`language: system`** (`.pre-commit-config.yaml`: `entry: mypy
--ignore-missing-imports`, no venv). It runs whatever `mypy` is on `$PATH`
(`~/.local/bin/mypy`), which resolves `import penguin_dal` via the SAME
drifting editable install as before — `.venv/`'s pinned `penguin-dal==0.4.1`
is invisible to it entirely.

Consequence, hit for real on Task 6: `app/background.py` and `run.py` each
carry a `# type: ignore[operator]` on `db.executesql(...)`, documented as
needed because mypy infers `db.executesql` as pydal's dynamic `TableProxy`
rather than a typed method. `.venv`'s pinned `penguin-dal==0.4.1` DOES type
`executesql` properly, so `.venv/bin/python3 -m mypy --strict` flags the
suppression as `unused-ignore` — genuinely, reproducibly, confirmed via
`git stash` that it's true even with zero code changes. **Removing the
suppression on that evidence is wrong**: the ambient checkout mypy's hook
actually resolves through (confirmed 2026-08-11: `fix/pypi-publish-action-bump`,
`grep -c executesql db.py` → 0) predates `executesql` entirely, so without
the suppression `mypy --ignore-missing-imports app/background.py` (the exact
hook invocation) fails with `"TableProxy" not callable [operator]`.

**How to apply:** for any `# type: ignore` whose stated reason is "penguin-dal
stub gap", verify against BOTH mypy invocations before touching it —
`.venv/bin/python3 -m mypy --strict --ignore-missing-imports <file>` (the
pinned/released truth) AND plain `mypy --ignore-missing-imports <file>` (what
`git commit` actually runs) — and keep the suppression if EITHER wants it.
They can legitimately disagree, and the system one is what gates the commit
regardless of which one is "more correct" for a shipped release.

**SUPERSEDED 2026-08-20 — the hook no longer runs the ambient/system mypy.**
`.pre-commit-config.yaml`'s mypy hook is now `language: script`, entry
`scripts/hooks/run-mypy.sh`, which resolves `git rev-parse --show-toplevel`
and execs `$REPO_ROOT/.venv/bin/mypy` — never `mypy` off `$PATH`. It fails
loudly with an instruction to run `make venv-portal-api` if `.venv/` doesn't
exist, rather than silently falling back to the ambient environment. This
closes the drift class documented above at its root: a developer's shell,
the hook, and CI now all resolve `penguin_dal` from the same pinned
`.venv`. The `# type: ignore[operator]` suppressions on `db.executesql(...)`
in `run.py`/`background.py` were genuinely `unused-ignore` under this fixed
hook and were removed — do not re-add them on ambient-checkout evidence;
the ambient checkout no longer has a vote.

Beyond flake8/black/isort/mypy, the repo also gates on:
- `yamllint -c .yamllint.yml` — rejects PyYAML's default sequence indentation,
  so generated YAML must be emitted with an indenting Dumper
- `spectral` (via `npx @stoplight/spectral-cli`) — OpenAPI ruleset
- `checkov --framework openapi` — runs on pre-push, catches things spectral
  does not (e.g. arrays without `maxItems`)

`make lint`/`make typecheck` invoke `mypy . --ignore-missing-imports`, which
is clean; a bare `mypy --strict services/portal-api` reports a pre-existing
`grpc` stub error. Quote the repo's own invocation, not yours.

See [[feedback-gates-block-push]].
