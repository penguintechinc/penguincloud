---
name: env-toolchain-constraints
description: Local Python env is PEP 668 externally-managed (pip install fails); repo lints YAML/OpenAPI with tools beyond flake8
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

Beyond flake8/black/isort/mypy, the repo also gates on:
- `yamllint -c .yamllint.yml` — rejects PyYAML's default sequence indentation,
  so generated YAML must be emitted with an indenting Dumper
- `spectral` (via `npx @stoplight/spectral-cli`) — OpenAPI ruleset
- `checkov --framework openapi` — runs on pre-push, catches things spectral
  does not (e.g. arrays without `maxItems`)

See [[feedback-gates-block-push]].
