---
name: feedback-precommit-all-files-blast-radius
description: pre-commit run --all-files runs --fix/formatters against every tracked file in the repo, not just your changeset — it silently rewrote ~80 unrelated files across three other agents' domains
metadata:
  type: feedback
---

`pre-commit run --all-files` does exactly what it says: every hook with
`--fix`/format semantics (ruff, ruff-format, trailing-whitespace,
end-of-file-fixer) runs against **every tracked file in the repo**, not just
the files you're working on. Running it mid-task on penguincloud (which has
a large pre-existing lint/format debt outside any one task's scope — see
[[feedback-gates-block-push]] "every file in the repo is non-compliant")
modified ~80 files across `services/portal-api/app/`,
`services/portal-api/alembic/`, `tests/api/`, `web/`, `.gitignore`,
`LICENSE.md`, and more — none of them touched by the actual task, several
inside OTHER parallel agents' assigned worktree domains.

**Why it matters:** in a multi-agent session, running `--all-files` doesn't
just create unwanted diff noise in your own PR — if it happens to touch a
file another concurrently-running agent is editing, it's a direct collision
(see [[feedback-bash-cwd-drift]]'s "shared pre-commit cache" incident for
the same class of cross-agent damage, different mechanism).

**How to apply:**
- Never run `pre-commit run --all-files` as a "does everything still pass"
  check on this repo. Use plain `pre-commit run` (defaults to files that
  differ from HEAD / are staged) — it's what a real `git commit` actually
  invokes, and it's what "verify the gate passes" should mean in practice.
- If a task explicitly asks for `--all-files` specifically, treat that as a
  red flag to confirm with the user first rather than running it blind —
  the literal instruction and "verify my changes pass the gate" are not the
  same thing on a repo with this much pre-existing debt.
- If you already ran it: `git status -sb` immediately, diff the unexpected
  files against HEAD, and `git checkout -- <path>` everything outside your
  intended file set BEFORE staging/committing anything. Do this file-by-file
  against an explicit allowlist of what you meant to touch — don't trust
  "looks unrelated" from memory, actually check each path.
- A file that IS legitimately part of your changeset (you added real code to
  it) will still get whole-file reformatted by ruff/ruff-format the moment
  it's staged for a real commit — that part is correct and expected, not
  something to fight (see [[feedback-gates-block-push]] "measure your ruff
  delta" — that guidance is about NOT touching files outside your changeset,
  not about resisting the formatter on files you did touch).

See [[env-toolchain-constraints]], [[feedback-gates-block-push]].
