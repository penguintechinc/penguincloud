# PenguinCloud Application Standards

## Product Overview

**PenguinCloud** is the unified management and WebUI layer for the PenguinTech product portfolio. It serves MSPs, Enterprises, and hosting providers with a single portal and unified art scheme (gold #fbbf24 on slate dark), rendering full management screens via direct calls to product APIs. No SSO-handoff UI patchwork — one coherent experience across all integrated products.

## Integrated Products & Phasing

**Phase 0 (now):** Core 3 products
- **Gough** — Hypervisor solutions (VMs, containers, resource orchestration)
- **Nest** — Data, storage, and DBaaS (relational/NoSQL, backups, replication)
- **Tobogganing** — Networking and SASE (firewalls, VPNs, routing, threat prevention)

**Phase 1:** WaddleAI (generative AI capabilities, licensing-gated Enterprise tier)

**Later phases:** Elder (relationship/knowledge management), Waddles/WaddleBot (community management), Current (URL shortening/link management)

## Architecture

### Current Status
Phase 0 repository hygiene in progress on `chore/phase0-repo-hygiene`. Current state: legacy template lineage deleted; go-backend retired (unused, permanent osv-scanner advisory GO-2026-5932); git hooks live (gitleaks/flake8/mypy pre-commit, full security scans pre-push); test suite runs clean (73 passed, 12 skipped-as-not-implemented, 19 xfailed, exit 0). Backend currently Flask (`services/portal-api`) — migration to Quart 0.19+ scheduled Phase 1a.

### Services

**Portal API** (`services/portal-api`): Backend orchestration layer
- Framework: Quart 0.19+ with hypercorn ASGI server
- Auth: penguin-aaa (OIDC, scope-based, tenant-scoped)
- Database: penguin-dal (runtime) + SQLAlchemy/Alembic (schema-only)
- API docs: quart-schema generates OpenAPI v1 at `openapi/v1.yaml` (authenticated)
- Health endpoint: `/health` (TCP + HTTP GET)

**WebUI** (`services/webui`): React management dashboard
- React **19.2.8**, TypeScript strict — deviates from org standard React 18 to resolve GHSA-qwww-vcr4-c8h2 (RSC-mode CSRF advisory affecting react-router 7.12.0–8.2.x, fixed in 8.3.0; no React-18-compatible fix available)
- Routing: react-router **8.3.0** (exact pin) — org standard is react-router v6; upgraded to 8.3.0 for security advisory remediation (user-approved, Phase 1F)
- Styling: TailwindCSS v4 with @theme tokens (slate dark + gold)
- Data fetching: TanStack Query 5
- Components: @penguintechinc/react-libs (shared components, auth, forms) — tested compatible with React 19.2.8
- Deployment: Node.js/Express serving static files + `/api` proxy to portal-api

### Product Adapters
Each integrated product exposes a typed async contract (health checks, capabilities discovery, resource CRUD operations, metrics, user mapping). PenguinCloud calls these via deny-by-default scoped proxy with per-route allowlists (no blanket product-to-portal-api trust; every endpoint explicitly allowed).

Product tenant identity mapping via `product_tenant_map` table: portal tenant ↔ product tenant_id/organization_id/namespace.

## Tenancy Model

Hierarchical — provider org → customer tenants → teams/users. Delegated MSP admin via ancestor-tenant membership resolved at token issue. JWT claims carry `tenant`, `teams`, `roles`, and `scope` fields. Tenant isolation enforced at middleware layer (runs first, blocks 403 on mismatch).

## License Tiers

**The paywall gates scale and structure, not features.** Every tier gets every module with full features — a single free user experiences the whole product. There is never a locked or crippled module; if a change would make a *capability* unavailable rather than a *count* unavailable, it belongs in `FEATURE_MIN_TIER`, not in the quota table.

| Dimension | Free | Professional | Enterprise |
|---|---|---|---|
| Modules (all, full features) | ✅ | ✅ | ✅ |
| Non-admin members | unlimited | unlimited | unlimited |
| Global admins | 1 | 1 | unlimited |
| Tenant admins (delegated) | 0 | 10 | unlimited |
| Tenants | 1 | 1 | unlimited |
| Teams | 1 | unlimited | unlimited |
| Object quota | 1,000 | unlimited | unlimited |
| Backend nodes per service type | 1 each | 1 each | multiple/HA |
| Google OAuth2 SSO | — | ✅ | ✅ |
| SAML 2.0 / OIDC SSO | — | — | ✅ |
| WaddleAI | — | ✅ hosted API only | ✅ |
| BYOK AI (Anthropic/OpenAI/Ollama) | — | — | ✅ |
| Whitelabel | — | — | ✅ |
| External KMS | — | — | ✅ |
| Audit logs, advanced analytics | — | — | ✅ |

"Free" is the commercial name; the licence server's wire value is `community` (`licensing.TIER_COMMUNITY`).

### Enforcement is a hard block

The over-limit action — 2nd team on Free, 11th tenant admin on Professional, 2nd tenant below Enterprise, 1001st object on Free — is **refused with 402 + an upgrade prompt**. Never a soft warning, never a silent cap that drops the write. 402 rather than 403 so a scale wall is distinguishable from an authorization denial: opposite problems, opposite remedies.

Metered at both the creation **and** the promotion path — "add as member, then promote" must not be an unmetered route to the same structure.

**One refusal shape for every scale wall.** `quotas.scale_refusal_body()` builds it, and `devmode.user_creation_refusal()` uses the same one: status 402 and keys `error`, `message`, `dimension`, `limit`, `current`, `current_tier`, `required_tier` (null when no tier lifts it). `error` names the specific cause. One class of problem must not reach a client in several unrelated shapes.

**`tenant_admins` is counted deployment-wide**, like every other dimension. Counted per-tenant it read the same only because tenants are themselves capped at 1 below Enterprise — but the limits are licence-configurable, so raising `max_tenants` alone would have sold 10×N delegated admins under a limit published as 10.

**Routes meter; the model layer backstops.** `models.create_team`, `create_tenant` and `add_tenant_member` call `quotas.assert_within()` and raise `QuotaExceeded`. A limit enforced at only some call sites is not a limit, and this is not hypothetical: `POST /api/v1/auth/register` created a personal team through the model layer with nothing metering it. The register path now meters the **team** and still creates the **user** — non-admin members are unlimited at every tier, so refusing the signup would turn a team wall into a user cap the model deliberately does not have. The refusal is reported in the response as `personal_team_refused`, never swallowed.

**A personal team counts toward the team limit, and the refusal says so.** On Free (Teams: 1) the first registration consumes the only team; not counting it would quietly give Free two. Because the team that consumed the limit was created *by this endpoint*, possibly for another account, a bare "1 of 1 teams" reads as a bug to someone who never created one — so `auth.register` prefixes the standard quota message with the explanation. Keys are unchanged; a test pins the wording so it cannot regress into a bare quota error.

**Validation precedes metering.** An invalid body is a 400 even when the deployment is over quota; answering 402 to a typo sends the operator to sales.

**Capability and count are two halves of one gate.** Because every limit is licence-configurable, a numeric override could otherwise sell a capability the tier does not include. Creating a second tenant additionally requires `multi_tenant`; enrolling or promoting a delegated tenant admin additionally requires `delegated_admin`. Those refuse 403 (`feature_not_entitled`) — a missing capability is not a number you have outgrown.

### Numeric limits are licence-server-configurable

`quotas.DEFAULT_TIER_LIMITS` is a **fallback table**, not a set of constants. Every limit is read from the licence payload (`max_global_admins`, `max_tenant_admins`, `max_tenants`, `max_teams`, `max_objects`) so a negotiated contract needs no redeploy. A malformed override falls back to the tier default — neither 0 (locks the customer out) nor unlimited (gives away the paywall) is a safe reading.

### Object quota — an object is one product connection

Confirmed. Enforced at connection create (`products.py`), 402 alongside the existing per-tenant `max_products` 403 — two different ceilings (what the licence sells vs. what the operator set on one tenant), and neither substitutes for the other.

Reasoning: a connection is the portal's unit of managed inventory and the only operator-created resource that grows unboundedly with use. Tenants/teams/admins are excluded (each already has its own wall). Users are excluded (non-admin members are unlimited by design; counting them would reintroduce the user cap the model removes).

**This wall is unlikely ever to bind on this product — do not build on it as protection.** A Free deployment is capped at 1 tenant and 1 team, and one tenant realistically registers a handful of connections, not a thousand. The walls that actually bite here are `tenants`, `teams`, `tenant_admins` and `global_admins`. The object quota is enforced because the commercial table names it and because a deployment *can* in principle register connections without limit inside its one tenant. A gate that exists but never fires is fine when documented as such; it is dangerous when mistaken for a control.

### Backend nodes per service type — NOT a portal-runtime concern

Helm replica counts, set at deploy time. Deferred to Phase 7 rather than inventing a runtime check the portal has no authority over.

### Two layers, both required

A feature ships only when the **flag is on** *and* the **licence entitles it**. `app/flags.py::is_feature_available` is the single place that conjunction lives — checking one and believing you checked both is the failure this split exists to prevent.

| Layer | Module | Source of truth |
|---|---|---|
| Flag (general enablement, rollout, kill switch) | `app/flags.py` | PostHog inside `license.penguintech.io` |
| Licence tier (entitlement) | `app/licensing.py` | `penguin_licensing.LicenseClient` |

- Declaration sides are `flags.KNOWN_FLAGS` and `licensing.FEATURE_MIN_TIER`. A name a gate spells that is absent from them is refused, and CI asserts every gated name is grantable — a gate nothing mints is a permanent 403.
- **CI asserts the converse too**, which is where the real gap was: every `FEATURE_MIN_TIER` entry is either enforced at a call site or listed in `licensing.NOT_YET_IMPLEMENTED`. Declaring a feature is selling it; a declared feature nothing checks is a paid capability given away. Removing a name from `NOT_YET_IMPLEMENTED` is the last step of building it.
- Same discipline for products: every `PRODUCT_TYPES` value is either in `PRODUCT_FLAGS` or in `flags.UNFLAGGED_PRODUCT_TYPES` (retired products, products with no portal module of their own, and the `generic` escape hatch).
- **The conjunction is enforced server-side.** `flags.product_gate_refusal()` runs at connection create (`products.py`) and in the proxy (`proxy.py`), so a disabled module refuses the API call rather than merely not rendering. `featureGates.ts` decides what the browser draws; it is not a control.
- **A product flag is a kill switch, not an enablement gate.** `flags.default_for()` resolves product flags ON (`PRODUCT_FLAG_DEFAULT`) and feature flags OFF. Only an explicit `false` from a configured flag server disables a module; no flag backend, or a backend that has never heard of the flag, leaves it available. This is deliberate divergence from "new/unseen flags default OFF", which governs the rollout of something *new* — a shipped module is not that, and the tier model forbids a locked or crippled module at any tier. Defaulting products OFF made every self-hosted deployment without PostHog an inert portal with no products at all. `GET /api/v1/features` reports the same defaults it enforces, so the UI cannot hide a product the API allows.
- `PRODUCT_FLAGS` and `FEATURE_FLAGS` must stay disjoint. `waddleai` is a connectable product on any tier; the Enterprise entitlement is `waddleai_assist`.

### Bypass is domain-based, and only domain-based

`licensing.host_is_license_exempt()` matching `*.penguincloud.io`, `*.penguintech.cloud`, `*.localhost.local` is the **only** way gating is skipped. There is no environment variable, CLI flag or config key that disables it, and adding one is forbidden (general.md).

**The host comes from configuration — `BASE_URL`, then `SERVER_NAME` — never from the request's `Host` header** (`licensing.configured_host()`). In a licensing threat model the adversary is the operator: they control their own ingress and can reach the pod directly, so a header is a claim the party being charged makes about themselves. Reading `request.host` meant any self-hosted deployment could send `Host: x.penguincloud.io` and entitle every licensed feature, pass every tier gate and resolve the Enterprise limits table. An unconfigured deployment resolves to no host and is therefore not exempt.

`RELEASE_MODE` survives in exactly two places, neither of which decides entitlement: whether a failed licence validation is fatal at startup, and whether keepalive phones home. It previously short-circuited `is_feature_enabled` to `True`, unlocking every paid feature on any deployment that had not set it.

### Frontend

`GET /api/v1/features` (authenticated) publishes flags, tier, tier ordering, the licensed-feature→tier map, and the dev-mode signal. `hooks/useFeatures` fetches it once from `Layout` and mirrors it into `lib/featureGates`; every gate reads that store. Everything defaults OFF until it resolves, including on fetch failure.

### `--dev` (single-user evaluation)

Undocumented flag on the portal entrypoint. Active only when **all** hold, **re-evaluated per request** (never latched at boot): PenguinTech-controlled domain, ≤1 user counted server-side from the identity table, and the flag was passed. While active it caps user creation at 1, logs a WARN carrying the resolved domain and the **observed** user count, prints the verbatim general.md notice to stderr, and raises a persistent non-dismissible UI banner. It unlocks **features only** — authentication, authorization and tenant isolation are untouched.

**It widens entitlement itself.** `licensing.dev_mode_entitles()` is consulted by `is_feature_entitled()` and by `quotas.resolve_limits()`, so an active `--dev` unlocks *because it is active*. Previously nothing consulted it: the mode appeared to work only because its domain condition called the same `host_is_license_exempt()` as the licence bypass, so on every domain where it could activate everything was already unlocked — without the cap, the WARN or the banner.

**Its domain set is deliberately wider than the licence bypass**, by exactly the product `.app` domains general.md names (`devmode.DEV_MODE_APP_DOMAINS`). The licence bypass is left exactly as `penguin_licensing` defines it. The divergence is what makes `--dev` observable on its own, and dev mode is far narrower in every other respect: it also needs the flag and at most one user, and it announces itself.

The cap refuses with the shared 402 scale-refusal shape at every user-creation path — `auth.register`, `users.create_new_user` and the OAuth callback — with `models.create_user` as the raising backstop beneath them. The OAuth path previously had no check, so the second SSO signup hit the backstop and escaped the view as a 500.

## Non-Goals

- No per-product art schemes — unified gold-on-slate only
- No Kustomize/raw manifests — Helm v4 only for all K8s deployments
- No direct product-DB access — all interactions via product APIs
- Desktop clients live in the `penguin` repo, not here

## Security Exceptions

### CKV_GHA_7 (GitHub Actions workflow_dispatch inputs)
`.github/workflows/gitstream.yml` is generated by the gitStream GitHub App and its `workflow_dispatch` inputs are the app's dispatch contract. This workflow is not subject to the org-wide workflow_dispatch ban. All other workflows must NOT use workflow_dispatch inputs.

Scoped via an inline `# checkov:skip=CKV_GHA_7: ...` comment on the `workflow_dispatch:` line in `gitstream.yml` itself — not a repo-wide `skip-check` in a `.checkov.yaml` config, which would silently exempt every *future* workflow's `workflow_dispatch` too. If the gitStream app regenerates the file and drops the comment, `checkov` fails loudly on the next scan and the comment is re-added; that's the intended failure mode.

### Services/go-backend Retirement
The `services/go-backend` was retired in Phase 0 (unused, never called by portal-api, no replacement scheduled). It carried a permanent osv-scanner advisory (GO-2026-5932) with no available fix. Its health-polling duty will migrate to an asyncio task in portal-api during Phase 6.

## Development Setup

**Prerequisites:**
- Python 3.13+ (portal-api)
- Node.js 26+ (webui)
- PostgreSQL 17+ or MySQL 12.3+ (run locally or via docker-compose)
- Docker + docker-compose for local services

**Local environment:**
```bash
make setup        # Install dependencies
make dev          # Start all services (portal-api, webui, postgres, redis)
make seed-mock-data  # Populate 3-4 test items per core-3 product
make test         # Run full test suite
```

**Mock data includes:** Sample VMs/containers (Gough), databases/storage (Nest), network policies (Tobogganing), test users across Community/Professional/Enterprise license tiers, hierarchical tenant structures for MSP admin testing.

## Testing Requirements

**Smoke tests:** Build, run, API health, page loads, core workflows (login, resource list/create/delete, tenant navigation)

**Coverage:** 90%+ minimum (lines, branches, functions, statements)

**Integration tests:** Real postgres (rollback after each test), product adapter mocking

**E2E:** Login → tenant switch → core-3 resource CRUD → permission checks

## Deployment

All environments (alpha/beta/gamma/prod) via Helm v4 only. Values files per environment: `alpha.yml`, `beta.yml`, `gamma.yml`, `production.yml`.

Alpha: local K8s (MicroK8s or Docker Desktop), `localhost:32000` registry
Beta/Gamma: `dal2.penguintech.cloud`, `ghcr.io/penguintechinc/penguincloud/{service}:{tag}`
Prod: Custom domain or `penguincloud.penguintech.cloud`, SHA256 image digests required

## Login contract adapter (documented exception)

The portal login page is `LoginPageBuilder` from `@penguintechinc/react-libs` —
no bespoke login UI exists. The component issues its own `fetch`, and its
request/response dialect differs from `POST /api/v1/auth/login` in three ways
that cannot be reconciled from the client:

| Component expects | Portal API sends |
|---|---|
| `data.success === true` on the response, else the attempt is rendered as failed | no `success` field at all |
| `mfaCode` (camelCase) in the request body | reads `mfa_code` |
| MFA challenge as **2xx** + `mfaRequired` (the MFA prompt is unreachable from a non-2xx response) | **401** + `mfa_required: true` |

Rather than fork the public API contract (mobile client + OpenAPI spec consume
it) or reimplement the login UI, the webui Express server exposes a BFF
translation endpoint, `POST /api/ui/login`
(`services/webui/src/server/authAdapter.ts`). It is registered ahead of the
`/api` proxy, forwards to the API unchanged, and maps only the response shape.
`src/server/__tests__/authAdapter.test.ts` pins each of the three mappings.

Consequence: `LOGIN_ENDPOINT` in `src/client/pages/Login.tsx` points at
`/api/ui/login`, not `/api/v1/auth/login`. If the shared library ever accepts a
response transform (or the API adopts the `success` envelope), delete the
adapter and repoint the constant.

## Known Limitations

- Single auth provider fallback (local accounts) during OIDC outage
- Product API timeouts (default 10s) — increase per-product via environment
- No multi-region replication (Phase 3 roadmap)
- Audit export (Enterprise) supports CSV only (JSON/Parquet Phase 2)

---

**Last Updated:** 2026-08-07  
**Maintained By:** PenguinTech Platform Team  
**Related Documentation:** CLAUDE.md, docs/DEVELOPMENT.md, docs/TESTING.md, docs/PRE_COMMIT.md
