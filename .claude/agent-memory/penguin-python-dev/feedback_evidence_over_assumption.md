---
name: feedback-evidence-over-assumption
description: On penguincloud Phase-4, verify a product's API against its source before building — committed specs and briefs have both been wrong; state what was NOT verified
metadata:
  type: feedback
---

Check the connected product's **live handler source** before implementing or
describing its API, and say plainly what you could not verify.

**Why:** Task 4G's brief and Gough's own committed
`docs/api/openapi-spec.yaml` both described routes the service does not
register (`/servers`, `/servers/{id}/power/{action}`, `/jobs`, `/stats`).
Building from either would have shipped a screen of buttons calling 404s.
The real surface was only in `~/code/gough/services/api-manager/app/api/*.py`.
The same session, a "cluster_id is available" reading collapsed once the
model was checked: the field is populated by a tolerant getter whose default
always wins because the column does not exist.

A third instance, fix wave 1: a task said to wire the dashboard card to
`metrics_summary()` instead of list-row counts. **Gough publishes no
fleet-size metric at all** — every gauge in
`services/api-manager/app/metrics.py` is operational or security (queue depths,
API error totals, latency, audit-chain failures); there is no `gough_nodes` /
`gough_agents` / `gough_biomes`. The card can source queue depth from metrics
and nothing else, so the fleet tiles stay list-derived (with the page-cap
caveat) until Gough adds a gauge. Check what a product actually exposes before
rewiring a UI onto it.

**How to apply:**
- Grep the product's route registrations and serializers, not its spec file
  or the brief. `~/code/{product}` is usually checked out locally.
- Check the product's route registrations for TRAILING SLASHES specifically —
  `route("/")` vs `route("/groups")` is a 308-vs-404 difference that no spec
  records (see [[adapter-contract-boundaries]]).
- When a decision hinges on a field being present, verify it at the **model**
  layer too — a serializer key can be a defaulting getter over a column that
  was never added.
- Distinguish "not implemented" from "cannot be implemented", and give the
  evidence for the latter. A controller can re-scope a blocked screen; it
  cannot act on "seemed hard".
- **Never let a green test suite imply a working integration.** Mock-only
  verification must be stated as such in the report ("adapter has only run
  against `httpx.MockTransport`; live smoke lands with the alpha deploy"),
  not softened or omitted.
- **You can usually get a real run without Docker.** In 4N the product's own
  Quart app was constructed in-process and served to the adapter via
  `httpx.ASGITransport`, injected as `Transport._client` — real routing,
  middleware, handlers and serializers, no compose, no build. It found a
  defect 97 green tests did not: Nest's create *reads* `type`/`class` while
  its serializer *writes* `resourceType`/`storageClass`, so a payload built
  from a resource just read is 400-rejected, and the committed spec documents
  the wrong pair. Gotchas: load the product's `app.py` under a distinct
  module name (it collides with the portal's own `app` package in
  `sys.modules`), execute it **once** per session (module-level Prometheus
  collectors raise `Duplicated timeseries` on re-exec), patch BOTH
  `app.adapters.transport.get_transport` and the adapter's own `_transport`
  (`HealthOnlyAdapter.health` reaches for the shared one, so patching only
  the helper leaves health talking to a real socket), and clear any JWKS
  cache between tests if each mints a fresh key.
- **Derive the product's route table from its source, not by hand.**
  `tests/api/{gough,nest}_route_source.py` AST-parse the real registrations;
  a test that binds every allowlist rule against a `werkzeug.routing.Map`
  built from that table is what catches a rule aimed at a route the product
  does not have — the `/servers`-and-`/jobs` class of defect. Verify it by
  injecting a phantom rule and watching it go red.

Related: writing the test first surfaces gate bugs the code reads as correct
— 4G's feature flag gated *rendering* while the component's hooks had already
fetched, which only a "the fetch never happens" assertion catches.

See [[project-portal-scope-vocabulary]], [[adapter-contract-boundaries]].
