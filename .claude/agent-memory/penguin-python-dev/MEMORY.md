# Agent Memory — penguin-python-dev (penguincloud)

- [Local toolchain constraints](env_toolchain_constraints.md) — PEP 668 blocks pip installs; `penguin_*` are editable installs of shared penguin-libs, so its branch silently decides your test results.
- [Pre-push gates that actually block](feedback_gates_block_push.md) — gitleaks entropy, npm audit, checkov openapi, prettier; what each rejects and the accepted fix shape.
- [Portal scope vocabulary](project_portal_scope_vocabulary.md) — coarse `products:*` plus per-product `products:{type}:{action}`; a scope no minter issues is a dead 403.
- [Evidence over assumption](feedback_evidence_over_assumption.md) — verify a product's API from its handler source, not its spec/brief; state what was only mock-verified.
- [Adapter contract boundaries](adapter_contract_boundaries.md) — proxy-vs-typed boundary, which mutations go where, allowlist over-match traps, trailing-slash asymmetry.
- [Prove a regression test can fail](feedback_revert_verification.md) — revert the fix and watch it go red; several 4G tests were green against the bug they covered.
- [Test suite shares one SQLite file](project_test_suite_shared_db.md) — deployment-wide counts accumulate across tests; fix the count, never the wall.
- [Nest product topology](project_nest_topology.md) — Nest is 4 services; only `apps/api` is reachable under `/api`, so Servers/Cloud/Workflows can't back a portal screen.
- [Bash cwd drift](feedback_bash_cwd_drift.md) — session cwd can silently jump to a different worktree; always prefix an absolute `cd`/`git -C`, never trust a bare command.
- [`pre-commit run --all-files` blast radius](feedback_precommit_all_files_blast_radius.md) — rewrote ~80 unrelated files repo-wide; use plain `pre-commit run` instead.
- [Makefile strictness sweep](feedback_makefile_strictness_sweep.md) — dropping `|| true` everywhere detonates on 691 flutter findings, 258 ruff findings, vendored shellcheck hits, docs gitleaks hits; scope each fix, test before committing.
- [penguin-email unpublished](project_penguin_email_unpublished.md) — not on PyPI yet; use stdlib smtplib+ssl for SMTP work until it ships.
- [webui npm audit blocks every push](feedback_webui_npm_audit_blocks_every_push.md) — pre-existing puppeteer-chain high-severity vulns in package-lock.json fail osv-scanner/npm-audit-webui regardless of your changes (RESOLVED 2026-08-20: puppeteer removed, ported to Playwright — see fix/mutation-error-surfacing).
