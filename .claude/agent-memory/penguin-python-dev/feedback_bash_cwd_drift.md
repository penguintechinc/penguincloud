---
name: feedback-bash-cwd-drift
description: The Bash tool's working directory can silently drift to a different worktree mid-session; always prefix commands with an absolute cd, never trust a bare relative command
metadata:
  type: feedback
---

Mid-Task-6 fix wave 1, a `cd /path/to/feature-health-poller && make test-api`
command was dispatched correctly, but the tool's own follow-up note reported
the session's cwd as `/home/penguin/code/penguincloud/.worktrees/feature-flags-licensing/services/portal-api`
— a DIFFERENT worktree, one being used by a different parallel agent, that I
never `cd`'d into myself. A subsequent bare `pwd` confirmed it: the shell
really was sitting in the other worktree.

**Why it matters:** any bash command in that window that did NOT itself
prefix an absolute `cd` (a bare `pytest`, `git status`, `ls`, etc.) would
have silently operated on the WRONG repo checkout — different code, possibly
a different agent's in-flight uncommitted work — with no error, just a
confusing/wrong result that looks like a mystery regression.

**How to apply:**
- Never rely on a `cd` issued in an earlier tool call still being in effect.
  Every bash command that touches the filesystem gets its own
  `cd /absolute/path && <command>` prefix, every time — cheap insurance
  against a shared/pooled shell session drifting between agents.
- For git specifically, prefer `git -C /absolute/path <command>` over `cd`
  entirely — it can't drift because there's no persistent state to drift.
- After ANY unexplained result (wrong file count, missing venv, command
  "succeeds" against nothing), the first move is `pwd` — not re-running the
  command, not assuming your own code broke.
- The Read/Edit/Write tools take an explicit absolute `file_path` and are
  NOT subject to this — they stayed correct throughout. Only bare Bash
  commands without their own path prefix are at risk.

No actual damage occurred this time (verified via `git status --porcelain`
on the other worktree — clean, untouched), but it was pure luck that no
bare command ran during the drift window.
