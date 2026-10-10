---
name: project-nest-topology
description: Nest is four services behind one hostname; only apps/api is reachable under /api, so manager/saga-engine/gateway routes cannot back a portal screen
metadata:
  type: project
---

**Nest is not one API.** A portal connection has one `base_url` and the
transport pins to it, so what a Nest adapter can serve is decided by Nest's
own routing, not by its repo layout.

`~/code/nest/k8s/kustomize/base/httproute.yaml` (host `nest.penguintech.cloud`):
`/api` → `nest-api:8080`, `/` → `nest-gateway:8082`. **Everything under
`/api` therefore lands on `apps/api` (Quart) and nothing else.**

| Service | Surface | Reachable under `/api`? |
|---|---|---|
| `apps/api` | data-resources, snapshots, protection-policies, search-pools, operations, catalog, cost-report, anomalies | yes |
| `apps/manager` | `/api/v1/servers`, `/cloud/*`, `/scaling/*`, `/sql-files/*`, `/auth/*`, `/license` | **no** |
| `services/saga-engine` | `/api/v1/workflows` | **no** |
| `services/gateway` | its own `/api/v1/tenants/{tid}/billing`, `/dataresources` (no hyphen) | **no** — shadowed by the HTTPRoute |

**Why it matters:** the 4N brief specified Servers, Cloud and Workflows
screens. All three are manager/saga routes. Building them against a Nest
connection ships buttons that 404. Billing survives only because `apps/api`
has `cost-report` — which its committed spec does not document.

**How to apply:** before scoping a Nest screen, check which service owns the
route AND whether the HTTPRoute reaches it. `apps/manager` routes share the
`/api/v1` prefix with `apps/api`, so they look sibling-adjacent in a grep and
are a different origin in production — that is also why they belong in
`unexposed_routes` (see [[adapter-contract-boundaries]]).

Other Nest facts that cost time:
- Nest registers `/health` + `/ready` and **no `/healthz`** anywhere. The
  contract's inherited default would report every healthy Nest as unhealthy.
  Nest's own compose healthchecks curl `/healthz` and are broken.
- **All 21 routes register without a trailing slash** — the opposite of
  Gough. Emit none.
- Every write answers `202` + `operationId`, including creates. One poll
  route for all of them: `/tenants/{tid}/operations/{op_id}`. No cancel and
  no log stream on `apps/api`.
- DataResource create **reads `type`/`class`** but **writes
  `resourceType`/`storageClass`**, and the spec documents the write names.
- `cost-report` proxies to `nest-cost-calculator` and answers 503 when it is
  absent — Billing needs a degraded state, not an empty table.
- `infrastructure/docker/nginx/` does not exist, so `docker compose up nginx`
  cannot start; bring up `api` alone, or run it in-process.

See [[feedback-evidence-over-assumption]], [[project-portal-scope-vocabulary]].
