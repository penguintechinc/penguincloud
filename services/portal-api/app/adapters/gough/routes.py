"""Gough's deny-by-default proxy allowlist.

This list governs the PROXY only — the untrusted-input path, where the
browser supplies the path string. The adapter's typed methods are not
filtered by it; see :mod:`app.adapters.base` for why that split exists and
what bounds it.

Scope convention
================
Reads require ``products:read``; every mutating verb requires
``products:manage``. Both are the portal's own scopes, defined in
``app/authz.py`` and minted into real tokens.

The brief specified ``gough:{resource}:{read|write}`` instead. That was not
adopted, and the reason is not stylistic: **nothing in the portal issues a
``gough:*`` scope.** ``_TEAM_ROLE_SCOPES`` and ``resolve_scopes`` produce
``products:read``/``products:manage``, so an allowlist demanding
``gough:nodes:read`` would be unsatisfiable by every token the portal can
mint — the entire Gough proxy surface would answer 403 to everyone, while
looking more precisely secured than the thing it replaced.

The half of the brief's intent that *is* enforceable is enforced: reads and
writes are separated, so ``POST /nodes/{id}/deploy`` (provisions hardware)
and ``DELETE /nodes/{id}`` (decommissions it) are unreachable with a
read-only token, and ``test_write_scopes_guard_every_mutating_verb`` asserts
that for every rule. Per-resource scopes remain worth having, but they need
role bundles and token minting to grow with them — a scope-model change
across all three Phase-4 products, not something the first integration
should introduce unilaterally. Flagged for the controller in
``task-4G-report.md``.

The literals below are duplicated from ``app/authz.py`` rather than imported:
``app.authz`` imports ``app.adapters.base``, so importing it here would make
``app.adapters`` and ``app.authz`` mutually dependent at import time.
``test_gough_allowlist.py`` asserts they have not drifted.

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

The cost is that a malformed id now yields "not allowlisted" rather than the
product's own 404. That is the right trade: a 403 on a bad id is a small
usability wart, and an allowlisted credential endpoint is not.
"""

from __future__ import annotations

from typing import Final

from ..base import RouteRule

__all__ = ["GOUGH_ROUTE_ALLOWLIST", "SCOPES"]

#: Numeric ids — Gough's ``<int:...>`` route converters.
_INT_ID = r"\d+"

#: UUID-shaped ids: hex digits and hyphens only. Deliberately not ``[^/]+``.
_UUID_ID = r"[0-9a-fA-F][0-9a-fA-F-]{0,63}"

#: Mirrors ``app.authz.SCOPE_PRODUCTS_READ`` / ``SCOPE_PRODUCTS_MANAGE``.
_READ: Final[str] = "products:read"
_WRITE: Final[str] = "products:manage"

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
