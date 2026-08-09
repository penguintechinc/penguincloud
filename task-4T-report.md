# Task 4T — Tobogganing integration

## Session 1

### Spec capture — the brief has the two specs backwards

The brief says: *"Tobogganing's public spec (~/code/tobogganing/openapi/v1.yaml) documents
only 5 paths; the full spec is auth-gated at the live `/openapi.json`. … capture the full
spec from a local/alpha instance … The adapter pins against this fixture."*

Both halves are inverted. Measured, not read:

| Artefact | Brief's claim | Measured | Evidence |
|---|---|---|---|
| `~/code/tobogganing/openapi/v1.yaml` | "only 5 paths" | **107 paths / 137 operations** | `grep -cE '^  /' openapi/v1.yaml` → 107 |
| live `GET /openapi.json` | "the full spec" | **5 hardcoded placeholder paths** | `hub_api/app.py:381-554`; handler body is a literal dict, commented `"For now, return a placeholder full spec."` (`app.py:398-399`). Paths: `/api/v1/auth/{login,refresh,logout}`, `/health`, `/ready` |

The committed `openapi/v1.yaml` is **generated from the live app**, not hand-maintained:
`scripts/generate_openapi.py:63-107` boots `create_app()` inside `async with app.test_app()`
specifically so `before_serving` fires and `registry.apply_to` mounts every module blueprint
before the spec is read (its own comment at `:72-78` says the spec would otherwise "contain
only the core routes and miss every module").

**Consequence:** following the brief literally — capture live `/openapi.json`, pin the adapter
to it — would have pinned the adapter to a 5-path placeholder and dropped 102 real paths. That
is the phase's own three-strikes defect class (binding to the wrong side of a boundary).

**What I did instead:** captured the **live `url_map`** — the route registrations themselves,
which are the single source both the spec generator and the adapter must agree with. Booted
Tobogganing locally (`create_app()` + `test_app()`, all 9 modules registered) and dumped every
rule with its methods, `strict_slashes`, and the auth decorator guarding it. **139 rules.**

### Live run — Tobogganing boots

`create_app()` + `async with app.test_app()` completes: all 9 modules register
(`ping, sase, sdwan, threatintel, perftest_cluster, perftest_client, perftest_c2c, ziti, netsvcs`),
`InAppKeyProvider` configured, services initialised. So the route table below is observed, not
inferred. (Full HTTP round-trips against a seeded DB are not part of this — stated as a limit.)

### The brief's resource map does not match the product

Brief: *"`sase` (clients/clusters/status), `sdwan` (links/policies), `firewall` (rules),
`wireguard` (peers/configs), `headend` (config)"*. Against the real `url_map`:

| Brief resource | Reality |
|---|---|
| `sase` = clients/clusters/status | **No.** SASE is **blockpages + SWG** (`/api/v1/sase/blockpages/*`, `/api/v1/sase/swg/*`, 12 rules). `clients`/`clusters`/`status` are **SD-WAN** routes. |
| `sdwan` = links/policies | **No such routes.** SD-WAN (15 rules) is clients / clusters / status / wireguard. Nothing named `links` or `policies` exists anywhere in the url_map. |
| `firewall` = rules | 1 rule, `GET /api/v1/firewall/rules` — **machine-JWT only** (see below). |
| `wireguard` = peers/configs | `GET /api/v1/wireguard/peers` — **machine-JWT only**. `GET /api/v1/sdwan/wireguard/peers` *is* user-reachable. **No `configs` route exists.** |
| `headend` = config | `GET /api/v1/headend/<headend_id>/ports` — **machine-JWT only**. No `config` route. (`/api/v1/sdwan/clusters/<id>/headend-config` exists but is node-credential auth.) |

### Three of the five brief resources are unreachable with a portal credential

This is the load-bearing finding, and it is an audience mismatch, not a scope one.

```
portal connection credential
    └─ POST /api/v1/auth/login          (hub_api/api/auth_routes.py:23)
         └─ AuthService._generate_access_token
              claims["aud"] = config.product_name        service.py:341
                            = "tobogganing"              config/__init__.py:36
                                    │
                                    ▼
        @require_machine_jwt(...)  ──► _extract_machine_identity
                                        if claims["aud"] != "headend": reject
                                                          middleware.py:516-517
```

A user token carries `aud="tobogganing"`; the machine path demands `aud="headend"`. The
scopes are *not* the blocker — `ROLE_SCOPES` (`service.py:24-28`) grants wildcards
(`*:read`, `*:write`) and `_scope_satisfied` (`middleware.py:44-50`) expands `*:read` to
satisfy `firewall:read`. The audience check fails first and cannot be satisfied by any token
`/api/v1/auth/login` issues.

The 8 machine-JWT routes (`aud=headend`, issued by `POST /api/v1/auth/token` to a node
presenting `node_id`/`node_type`/`api_key`, `headend_routes.py:291`):

| Route | Scope |
|---|---|
| `GET /api/v1/firewall/rules` | `firewall:read` |
| `GET /api/v1/wireguard/peers` | `wireguard:read` |
| `GET /api/v1/headend/<headend_id>/ports` | `ports:read` |
| `POST /api/v1/certs/certificates` | `certs:issue` |
| `GET /api/v1/sase/swg/radix` | `swg:read` |
| `GET /api/v1/netsvcs/dns-servers/<id>/config` | `dns:config:read` |
| `POST /api/v1/netsvcs/dns-servers/<id>/heartbeat` | `metrics:write` |
| `POST /api/v1/sdwan/clients/headends/<id>/metrics` | `metrics:write` |

`headend_routes.py:1-8` states the intent outright: *"These endpoints are called by the Go
hub-router headend service."* They are a machine-to-machine control plane, not a portal surface.

**The one way to reach them would be to store Tobogganing's `HEADEND_API_TOKEN` as the portal
connection credential** — the legacy dual-accept branch at `middleware.py:587-626` accepts it
while `tobogganing.core.machine_jwt_required` is OFF. That is rejected here: it is a
fleet-wide shared secret granting `firewall:read wireguard:read ports:read metrics:write
certs:issue swg:read` (`machine_claims.py:9`), and the legacy branch hardcodes
`g.machine_tenant = "default"` (`middleware.py:619`), so it bypasses tenant scoping entirely.
Storing it per-connection would put a cross-tenant credential behind a per-tenant UI.

**Therefore Firewall, WireGuard-peers and Headend-ports cannot back a portal screen** on the
user-credential model every other adapter uses. This is "cannot be implemented", with the
evidence, not "not implemented".

### What IS reachable — the real adapter surface

User-JWT (`require_tenant` [+ `require_scope`]), so reachable with a stored login credential:

| Portal resource | Routes | Scope required by Tobogganing |
|---|---|---|
| **SASE** | `GET/POST /sase/blockpages/pages`, `PUT /sase/blockpages/pages/<id>`, `POST …/preview`, `POST …/publish`, `GET/PUT /sase/blockpages/routes`, `GET /sase/swg/policy`, `PUT /sase/swg/policy`, `POST /sase/swg/categories`, `GET /sase/swg/lookup` | `sase:read` / `sase:write` |
| **SD-WAN** | `GET /sdwan/clients`, `GET /sdwan/clusters`, `GET /sdwan/wireguard/peers` | `clients:read`, `clusters:read`, (peers: `require_tenant` only) |
| **Clusters (flat)** | `GET /api/v1/clusters/` — **trailing slash, strict** | `clusters:read` |
| **DNS (netsvcs)** | zones, records, dns-servers, analytics/* | `dns:read` / `dns:write` |
| **Perf** | `perftest_cluster` / `perftest_client` / `perftest_c2c` | per-resource read/write |

### Trailing-slash asymmetry (the Gough class, present here)

Tobogganing mixes both shapes in one API, so a uniform rule is wrong in one direction or the
other. All rules are `strict_slashes=True`:

- `GET /api/v1/clusters/` — **registered WITH** the slash (`headend_routes.py:614`). A request
  to `/api/v1/clusters` gets a 308 the portal transport does not follow.
- `GET /api/v1/sdwan/clusters` — **registered WITHOUT** (`sdwan/api/…`). A request to
  `/api/v1/sdwan/clusters/` gets a flat 404.

Two paths that both read "clusters", opposite slash requirements. Pinned per-route in the
fixture rather than described.

### Product-side defects observed (in Tobogganing, not fixed here — read-only)

1. `GET /api/v1/ziti/api/v1/ziti/health` — doubled prefix. The ziti blueprint declares its own
   `/api/v1/ziti` prefix and the registry prepends `/api/v1/{module}` again
   (`registry/registry.py:58-62`). Same defect class as Phase 3's doubled proxy mount.
2. `POST /api/v1/auth/refresh` is registered **twice** (`auth_routes.py:79` and
   `headend_routes.py:502`); the app-level `headend_bp` and `auth_bp` collide on the path.
   Whichever registers first wins — silently different token-rotation semantics.
3. Live `GET /openapi.json` serves a hardcoded 5-path placeholder while claiming in its
   docstring to expose "the complete API surface" (`app.py:381-397`).

---

*(session continues — adapter implementation below as it lands)*
