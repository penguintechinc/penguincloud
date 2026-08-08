# Agent Memory — penguin-python-dev (penguincloud)

- [Local toolchain constraints](env_toolchain_constraints.md) — PEP 668 blocks pip installs; spectral/checkov/yamllint gate the repo beyond flake8.
- [Pre-push gates that actually block](feedback_gates_block_push.md) — gitleaks entropy, npm audit, checkov openapi, prettier; what each rejects and the accepted fix shape.
