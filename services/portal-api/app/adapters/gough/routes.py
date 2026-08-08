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
``POST /nodes/{id}/deploy`` (provisions hardware) and
``DELETE /nodes/{id}`` (decommissions it) are unreachable with a read-only
token, asserted by ``test_write_scopes_guard_every_mutating_verb``.

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

So each id is matched by what it actually is:

* :data:`_INT_ID` (``\\d+``) for nodes and biomes — Gough declares those
  routes ``<int:node_id>``/``<int:biome_id>``, so a non-numeric value was
  never going to be a valid id, and restricting to digits cannot collide
  with any word-shaped literal.
* :data:`_UUID_ID` (hex and hyphens) for agents, deployments and clusters,
  whose ids are UUIDs. This excludes ``enrollment-keys``, ``enroll``,
  ``refresh`` and ``heartbeat`` structurally — including any *future* literal
  Gough mounts there, which a hand-written exclusion list would not.

(The second case above is stated in the scopes of the time; both rules now
carry ``products:gough:*``, and the collision it describes is unchanged.)

The cost is that a malformed id now yields "not allowlisted" rather than the
product's own 404. That is the right trade: a 403 on a bad id is a small
usability wart, and an allowlisted credential endpoint is not.
"""

from __future__ import annotations

from typing import Final

from ..base import RouteRule, product_scope

__all__ = ["GOUGH_ROUTE_ALLOWLIST", "PRODUCT_TYPE", "SCOPES"]

#: The ``product_connections.product_type`` value this adapter serves. Also
#: the middle segment of every scope below, so a connection of this type is
#: exactly what makes those scopes minted for its tenant.
PRODUCT_TYPE: Final[str] = "gough"

#: Numeric ids — Gough's ``<int:...>`` route converters.
_INT_ID = r"\d+"

#: UUID-shaped ids: hex digits and hyphens only. Deliberately not ``[^/]+``.
_UUID_ID = r"[0-9a-fA-F][0-9a-fA-F-]{0,63}"

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
    RouteRule("POST", rf"^/api/v1/nodes/{_INT_ID}/deploy\Z", _WRITE),
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
    RouteRule("POST", rf"^/api/v1/biomes/{_INT_ID}/upgrade\Z", _WRITE),
    # -- operations (deployments + upgrade runs) --------------------------
    RouteRule("GET", r"^/api/v1/biomes/deployments\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/deployments/{_UUID_ID}\Z", _READ),
    RouteRule("GET", rf"^/api/v1/biomes/deployments/{_UUID_ID}/logs\Z", _READ),
    RouteRule(
        "GET",
        rf"^/api/v1/biomes/{_INT_ID}/upgrade-runs/{_UUID_ID}\Z",
        _READ,
    ),
    RouteRule(
        "POST",
        rf"^/api/v1/biomes/deployments/{_UUID_ID}/cancel\Z",
        _WRITE,
    ),
    # -- clusters ---------------------------------------------------------
    # No collection rule: Gough registers no ``GET /api/v1/clusters``. A rule
    # for it would allowlist a 404.
    RouteRule("GET", rf"^/api/v1/clusters/{_UUID_ID}/config\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_UUID_ID}/lxd/status\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_UUID_ID}/lxd/members\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_UUID_ID}/storage\Z", _READ),
    RouteRule("GET", rf"^/api/v1/clusters/{_UUID_ID}/network-pools\Z", _READ),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_UUID_ID}/config\Z", _WRITE),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_UUID_ID}/storage\Z", _WRITE),
    RouteRule("PATCH", rf"^/api/v1/clusters/{_UUID_ID}/network-pools\Z", _WRITE),
    # -- agents -----------------------------------------------------------
    RouteRule("GET", r"^/api/v1/agents/?\Z", _READ),
    RouteRule("GET", rf"^/api/v1/agents/{_UUID_ID}\Z", _READ),
    RouteRule("POST", rf"^/api/v1/agents/{_UUID_ID}/suspend\Z", _WRITE),
    RouteRule("POST", rf"^/api/v1/agents/{_UUID_ID}/resume\Z", _WRITE),
]
