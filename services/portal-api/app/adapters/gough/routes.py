"""Gough's deny-by-default proxy allowlist.

This list governs the PROXY only — the untrusted-input path, where the
browser supplies the path string. The adapter's typed methods are not
filtered by it; see :mod:`app.adapters.base` for why that split exists and
what bounds it.

Scope convention
================
Reads require ``products:gough:read``; every mutating verb requires
``products:gough:manage``. Both are built with
:func:`~app.adapters.base.product_scope` and both are minted for real by
``app.tenancy.authz.resolve_scopes``, which expands a caller's coarse
``products:*`` grant across the product types their tenant is connected to.
See "Per-product scopes" in :mod:`app.adapters.base` for the model.

The brief specified ``gough:{resource}:{read|write}``. The namespace was not
adopted, and the reason is not stylistic: **nothing in the portal issues a
``gough:*`` scope**, so an allowlist demanding ``gough:nodes:read`` would be
unsatisfiable by every token the portal can mint — the entire Gough proxy
surface would answer 403 to everyone, while looking more precisely secured
than the thing it replaced. The brief's *intent* — an operator with
authority over one product and not another — is what the ``products:gough:*``
form delivers, because it is inside the namespace the portal already mints.

Per-resource granularity (``…:nodes:…`` vs ``…:biomes:…``) is still not
adopted. Nothing distinguishes those grants either, and a scope no grant
surface can express is the same dead rule in a smaller form. The enforceable
split is read vs write, and it is enforced for every rule below:
``POST /nodes/{id}/evacuate`` (drains hardware) and ``DELETE /nodes/{id}``
(decommissions it) are unreachable with a read-only token, asserted by
``test_write_scopes_guard_every_mutating_verb``.

Actions that start pollable work are NOT here
=============================================
``POST /nodes/{id}/deploy`` and ``POST /biomes/{id}/upgrade`` are deliberately
absent. Both answer ``202`` with ids the caller must poll, and the proxy
forwards a response body verbatim — so proxying either would hand the browser
Gough's raw payload with no :class:`~app.adapters.base.Operation`, no
normalised state and no poll key, leaving the UI to invalidate its queries and
hope. They are served by the typed action route
(``POST /products/{id}/resources/{kind}/{id}/actions/{action}``), which returns
an :class:`~app.adapters.base.ActionResult` carrying those ids. See "Which
mutations go through which path" in :mod:`app.adapters.base`.

Anchoring is enforced by :class:`~app.adapters.base.RouteRule` at
construction, so a mistake in this module is an ImportError in CI rather
than a rule that silently over- or never matches. ``\\Z`` is required, not
``$``.

Id patterns are typed, and that is a security property
======================================================
A permissive ``[^/]+`` for an id collides with the literal sub-collections
Gough mounts under the same prefix, and the collision silently ALLOWLISTS
them. Two real cases, both caught by the matrix in
``tests/api/test_gough_allowlist.py`` rather than by inspection:

* ``GET /api/v1/agents/enrollment-keys`` matched an "agent detail" rule and
  became a proxyable route that lists **agent enrollment credentials**.
* ``GET /api/v1/biomes/deployments`` matched a "biome detail" rule and was
  admitted under ``gough:biomes:read`` instead of ``gough:operations:read``,
  so the operations scope governed nothing.

So each id is matched by what it actually is, using the shared constants in
:mod:`app.adapters.base` rather than patterns invented here — the contract
now carries the typed-id rule, so Phase-4N and 4T inherit it instead of
rediscovering it:

* :data:`_INT_ID` (:data:`~app.adapters.base.ID_INT`, ``\\d+``) for nodes,
  biomes and biome groups — Gough declares those routes ``<int:node_id>`` /
  ``<int:biome_id>`` / ``<int:group_id>``, so a non-numeric value was never
  going to be a valid id, and digits cannot collide with a word-shaped
  literal.
* :data:`_UUID_ID` (:data:`~app.adapters.base.ID_UUID`) for agents, anchored
  to the real 8-4-4-4-12 shape because Gough mints agent ids with
  ``str(uuid.uuid4())``. This excludes ``enrollment-keys``, ``enroll``,
  ``refresh`` and ``heartbeat`` structurally — including any *future* literal
  Gough mounts there, which a hand-written exclusion list would not.
* :data:`_OPAQUE_ID` (:data:`~app.adapters.base.ID_SLUG`) for deployments,
  clusters and upgrade runs, whose ids are genuinely opaque strings
  (``deployments.id`` is ``String(64)``, ``clusters.id`` is ``String(255)``).
  These are NOT UUIDs and typing them as UUIDs would have refused valid ids.

The previous revision typed all three of the last group as a loose
``[0-9a-fA-F][0-9a-fA-F-]{0,63}``, which was simultaneously too tight (it
would reject a legitimate non-hex deployment id) and too loose (it admitted
any hyphenated hex-ish word, re-opening the collision). Splitting them is
what makes both halves true.

(The second case above is stated in the scopes of the time; both rules now
carry ``products:gough:*``, and the collision it describes is unchanged.)

The cost is that a malformed id now yields "not allowlisted" rather than the
product's own 404. That is the right trade: a 403 on a bad id is a small
usability wart, and an allowlisted credential endpoint is not.
"""

from __future__ import annotations

from typing import Final

from ..base import ID_INT, ID_SLUG, ID_UUID, RouteRule, product_scope

__all__ = [
    "GOUGH_ROUTE_ALLOWLIST",
    "GOUGH_UNEXPOSED_ROUTES",
    "PRODUCT_TYPE",
    "SCOPES",
]

#: The ``product_connections.product_type`` value this adapter serves. Also
#: the middle segment of every scope below, so a connection of this type is
#: exactly what makes those scopes minted for its tenant.
PRODUCT_TYPE: Final[str] = "gough"

#: Numeric ids — Gough's ``<int:...>`` route converters.
#: Aliases the shared :data:`~app.adapters.base.ID_INT` so the typed-id
#: contract lives in one place and every Phase-4 adapter inherits it.
_INT_ID = ID_INT

#: Agent ids. Gough mints these with ``str(uuid.uuid4())``
#: (``api/agents.py:245``), so the full 8-4-4-4-12 shape is exact, not
#: defensive. This replaces a looser ``[0-9a-fA-F][0-9a-fA-F-]{0,63}`` run,
#: which admitted any hyphenated hex-ish word and so re-opened the literal
#: collision that typing ids exists to close.
_UUID_ID = ID_UUID

#: Opaque product-generated ids that are genuinely not int or UUID:
#: ``deployments.id`` is ``String(64)`` and ``clusters.id`` is ``String(255)``
#: (``models_m1.py``), and upgrade-run ids come straight from an insert.
#:
#: Word-shaped, so this is the one family that COULD collide with a literal
#: sub-collection. It does not today — no rule below mounts a literal at the
#: same depth beneath the same prefix — and
#: ``test_adapter_registry.test_no_id_pattern_matches_a_sibling_literal``
#: enforces that for every adapter, so a future literal added beside one of
#: these is a red test rather than a silent widening.
_OPAQUE_ID = ID_SLUG

#: Per-product scopes for this adapter. The coarse ``products:read`` /
#: ``products:manage`` still satisfy these (RBACEnforcer implication), so
#: naming the narrow form costs nothing today and is what lets a narrower
#: grant restrict to Gough alone tomorrow.
_READ: Final[str] = product_scope(PRODUCT_TYPE, "read")
_WRITE: Final[str] = product_scope(PRODUCT_TYPE, "manage")

#: Every scope this adapter's allowlist can require. Exported so a scope
#: audit does not have to re-derive the set by reading regexes.
SCOPES: Final[tuple[str, ...]] = (_READ, _WRITE)

GOUGH_ROUTE_ALLOWLIST: Final[list[RouteRule]] = [
    # -- liveness ---------------------------------------------------------
    RouteRule("GET", r"^/healthz\Z", _READ),
    RouteRule("GET", r"^/readyz\Z", _READ),
    RouteRule("GET", r"^/api/v1/status\Z", _READ),
    # -- nodes ------------------------------------------------------------
    RouteRule("GET", r"^/api/v1/nodes/?\Z", _READ),
    RouteRule("GET", rf"^/api/v1/nodes/{_INT_ID}\Z", _READ),
    RouteRule("GET", rf"^/api/v1/nodes/{_INT_ID}/tags\Z", _READ),
    RouteRule("GET", rf"^/api/v1/nodes/{_INT_ID}/biomes\Z", _READ),
    RouteRule("PATCH", rf"^/api/v1/nodes/{_INT_ID}\Z", _WRITE),
    RouteRule("PATCH", rf"^/api/v1/nodes/{_INT_ID}/tags\Z", _WRITE),
    # Destructive and provisioning verbs. Deploy commissions hardware,
    # evacuate drains it, reject and delete remove it from the fleet — all
    # write, none reachable with a read scope.
    # NOT allowlisted: POST /nodes/{id}/deploy. It answers 202 with the
    # assignment ids the caller must poll, and the proxy forwards a body
    # verbatim — so a proxied deploy hands the browser Gough's raw payload
    # with no Operation, no normalised state and no poll key. It is served by
    # the typed action route instead (`perform_action`), which returns an
    # ActionResult carrying those ids. See "Which mutations go through which
    # path" in :mod:`app.adapters.base`.
    RouteRule("POST", rf"^/api/v1/nodes/{_INT_ID}/evacuate\Z", _WRITE),
    RouteRule("POST", rf"^/api/v1/nodes/{_INT_ID}/reject\Z", _WRITE),
    RouteRule("POST", rf"^/api/v1/nodes/{_INT_ID}/biomes\Z", _WRITE),
    RouteRule("DELETE", rf"^/api/v1/nodes/{_INT_ID}\Z", _WRITE),
    RouteRule("DELETE", rf"^/api/v1/nodes/{_INT_ID}/biomes/{_INT_ID}\Z", _WRITE),
    # -- biomes -----------------------------------------------------------
    # Declared before the generic /biomes/{id} rules would matter; ordering
    # is irrelevant to matching (every rule is fully anchored and tried
    # independently) but keeps the literal sub-collections legible.
    RouteRule("GET", r"^/api/v1/biomes/groups\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/groups/{_INT_ID}\Z", _READ),
    RouteRule("POST", r"^/api/v1/biomes/groups\Z", _WRITE),
    RouteRule("PUT", rf"^/api/v1/biomes/groups/{_INT_ID}\Z", _WRITE),
    RouteRule("DELETE", rf"^/api/v1/biomes/groups/{_INT_ID}\Z", _WRITE),
    RouteRule("GET", r"^/api/v1/biomes/?\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/{_INT_ID}\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/{_INT_ID}/eligibility\Z", _READ),
    RouteRule("POST", r"^/api/v1/biomes/?\Z", _WRITE),
    RouteRule("PUT", rf"^/api/v1/biomes/{_INT_ID}\Z", _WRITE),
    RouteRule("DELETE", rf"^/api/v1/biomes/{_INT_ID}\Z", _WRITE),
    # NOT allowlisted for the same reason as node deploy: upgrade answers
    # 202 with an upgrade_run_id to poll. Typed action route only.
    # -- operations (deployments + upgrade runs) --------------------------
    RouteRule("GET", r"^/api/v1/biomes/deployments\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/deployments/{_OPAQUE_ID}\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/deployments/{_OPAQUE_ID}/logs\Z", _READ),
    RouteRule(
        "GET",
        rf"^/api/v1/biomes/{_INT_ID}/upgrade-runs/{_OPAQUE_ID}\Z",
        _READ,
    ),
    RouteRule(
        "POST",
        rf"^/api/v1/biomes/deployments/{_OPAQUE_ID}/cancel\Z",
        _WRITE,
    ),
    # -- clusters ---------------------------------------------------------
    # No collection rule: Gough registers no ``GET /api/v1/clusters``. A rule
    # for it would allowlist a 404.
    RouteRule("GET", rf"^/api/v1/clusters/{_OPAQUE_ID}/config\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_OPAQUE_ID}/lxd/status\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_OPAQUE_ID}/lxd/members\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_OPAQUE_ID}/storage\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_OPAQUE_ID}/network-pools\Z", _READ),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_OPAQUE_ID}/config\Z", _WRITE),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_OPAQUE_ID}/storage\Z", _WRITE),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_OPAQUE_ID}/network-pools\Z", _WRITE),
    # -- agents -----------------------------------------------------------
    RouteRule("GET", r"^/api/v1/agents/?\Z", _READ),
    RouteRule("GET", rf"^/api/v1/agents/{_UUID_ID}\Z", _READ),
    RouteRule("POST", rf"^/api/v1/agents/{_UUID_ID}/suspend\Z", _WRITE),
    RouteRule("POST", rf"^/api/v1/agents/{_UUID_ID}/resume\Z", _WRITE),
]

#: Routes Gough really registers that this adapter must NEVER admit.
#:
#: Transcribed from Gough's own blueprints (``~/code/gough/services/
#: api-manager/app/``), not from its committed OpenAPI spec, which documents
#: routes the service does not register.
#:
#: This exists because the registry-wide id checks are structurally blind to
#: it: they compare an id pattern only against the literals THIS module
#: declares, so a route Gough mounts and this allowlist deliberately omits
#: cannot be seen by them. ``/api/v1/agents/enrollment-keys`` is exactly that
#: — a real Gough route, never allowlisted here, and silently admitted by a
#: loose ``[^/]+`` agent-id pattern until it was typed. Declaring these turns
#: "the id patterns look tight" into an assertion that names the endpoint it
#: is protecting.
#:
#: Concrete paths with REAL id values, not patterns: each is a request the
#: proxy must refuse, and ``test_adapter_registry`` asserts no rule matches
#: any of them.
GOUGH_UNEXPOSED_ROUTES: Final[tuple[tuple[str, str], ...]] = (
    # -- credential and auth surfaces -------------------------------------
    # Proxying any of these would let a caller holding a portal scope drive
    # Gough's own auth: mint an enrollment key, enrol an agent, or trade the
    # service account's session for a fresh token.
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/token"),
    ("POST", "/api/v1/auth/device"),
    ("GET", "/api/v1/agents/enrollment-keys"),
    ("POST", "/api/v1/agents/enrollment-keys"),
    ("DELETE", "/api/v1/agents/enrollment-keys/7"),
    ("POST", "/api/v1/agents/enroll"),
    ("POST", "/api/v1/agents/refresh"),
    ("POST", "/api/v1/agents/heartbeat"),
    ("GET", "/api/v1/secrets"),
    ("GET", "/api/v1/vault/status"),
    ("GET", "/api/v1/ssh-ca/ca"),
    ("POST", "/api/v1/shell/exec"),
    ("GET", "/api/v1/joiner-secrets"),
    # -- remote execution and cluster surgery -----------------------------
    ("POST", "/api/v1/clusters/cl-1/adopt"),
    ("POST", "/api/v1/clusters/cl-1/lxd/join"),
    ("POST", "/api/v1/clusters/cl-1/storage/switch-primary"),
    ("POST", "/api/v1/nodes/12/lxd/join"),
    ("GET", "/api/v1/nodes/12/cloud-init"),
    ("POST", "/api/v1/nodes/12/events"),
    ("POST", "/api/v1/nodes/discover"),
    ("POST", "/api/v1/primary/replace"),
    # -- identity the portal models itself --------------------------------
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/teams"),
    # -- operation-starting actions: typed route only (see above) ---------
    ("POST", "/api/v1/nodes/12/deploy"),
    ("POST", "/api/v1/biomes/5/upgrade"),
    # -- biome surfaces outside the reviewed set --------------------------
    ("POST", "/api/v1/biomes/5/upload"),
    ("POST", "/api/v1/biomes/5/sign"),
    ("POST", "/api/v1/biomes/render-cloud-init"),
    # -- scraped by the adapter, never proxied verbatim -------------------
    ("GET", "/metrics"),
)
