# Agent Memory — penguin-python-dev (penguincloud)

- [Local toolchain constraints](env_toolchain_constraints.md) — PEP 668 blocks pip installs; spectral/checkov/yamllint gate the repo beyond flake8.
- [Pre-push gates that actually block](feedback_gates_block_push.md) — gitleaks entropy, npm audit, checkov openapi, prettier; what each rejects and the accepted fix shape.
- [Portal scope vocabulary](project_portal_scope_vocabulary.md) — coarse `products:*` plus per-product `products:{type}:{action}`; a scope no minter issues is a dead 403.
- [Evidence over assumption](feedback_evidence_over_assumption.md) — verify a product's API from its handler source, not its spec/brief; state what was only mock-verified.
- [Adapter contract boundaries](adapter_contract_boundaries.md) — proxy-vs-typed boundary, which mutations go where, allowlist over-match traps, trailing-slash asymmetry.
- [Prove a regression test can fail](feedback_revert_verification.md) — revert the fix and watch it go red; several 4G tests were green against the bug they covered.
