---
name: project-test-suite-shared-db
description: penguincloud's pytest suite shares ONE SQLite file for the whole run, so any deployment-wide count accumulates across tests — the reason quota walls looked untestable
metadata:
  type: project
---

`tests/conftest.py` resolves `TestingConfig.DB_NAME` once per pytest process,
so **one SQLite file carries every user, tenant, team and connection the whole
run creates**. The `app` fixture is function-scoped but only re-runs
`create_all` against that same file.

**Why it matters:** any check against a *deployment-wide* count is meaningless
in a test — by the fiftieth test there are fifty tenants. That is what made
Phase 5's licence quotas appear to need a suite-wide "resolve everything as
Enterprise" fixture, which in turn made every wall a no-op and let an
unmetered creation path (`/auth/register` creating a team) survive review.

**How to apply:** do not disable the wall to work around the shared DB; make
the *count* per-test. `_quota_counts_are_per_test` (autouse) wraps
`quotas.count_*` to subtract a baseline, and `_prime_quota_baselines()` freezes
that baseline inside the `app` fixture — **before** other fixtures write rows,
so a tenant/admin created during setup still counts toward the test.
Tests that genuinely build a paid shape request `enterprise_license` (tier +
entitlements + limits move together; lifting only the numbers leaves the
`multi_tenant`/`delegated_admin` capability gates refusing, which reads like an
authz bug).

Measured on 2026-08-10: turning the walls on cost 35 failures, all of them
genuine multi-tenant/multi-team/delegated-admin tests.

Same shape applies to feature flags: with no `POSTHOG_KEY` every flag resolves
OFF, so an ungated suite tests a portal with every module switched off. The
fixture supplies flag STATE via a fake client (`flags._client`), leaving all of
`app/flags.py` executing — patching `get_client` or `is_enabled_blocking`
instead would bypass the code under test, and `evaluate_all` now takes a bulk
path that never calls the single-flag function at all.

See [[feedback-revert-verification]], [[env-toolchain-constraints]].
