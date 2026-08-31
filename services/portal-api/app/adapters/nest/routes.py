"""Nest route shapes, proxy allowlist, and the routes that must stay closed.

Every path Nest is addressed by — by the proxy allowlist, by the typed
adapter methods, and (via the generated OpenAPI spec) by the web UI — is
built here. That is deliberate: Task 4G shipped a defect in which the
adapter and the UI each spelled a collection path for themselves and
disagreed by one trailing slash, which surfaced as an empty table rather
than an error. One source of path text is the only structural fix.

Trailing slashes
================
Nest's API (``~/code/nest/apps/api/app.py``) registers **every** route
WITHOUT a trailing slash — ``@app.route("/api/v1/tenants/<tenant_id>/
data-resources")`` and so on for all **27 route registrations across 21
distinct paths** (six paths are declared twice, once per method). Under
Werkzeug's default ``strict_slashes`` that means a trailing-slash request
gets a flat 404 with no redirect back, and the portal's transport does not
follow redirects. So the builders below never emit one. This is the
opposite of Gough, which registers some collections as ``route("/")`` — the
asymmetry is why the shape is asserted against a real route map in
``tests/api/test_nest_allowlist.py`` rather than described in prose.

Which mutations are absent from the allowlist, and why
=====================================================
The allowlist here is **GET-only**, which is stricter than the contract
requires and is a consequence of how Nest answers writes rather than a
stylistic preference.

Every create in Nest is a long-running operation: ``POST`` of a
data-resource, snapshot, protection policy and search pool each answer
``202`` with an ``operationId`` and a ``Location`` header
(``apps/api/handlers/dataresource.py:295-309``,
``handlers/protection.py:92``, ``:274``, ``handlers/searchpool.py:87``).
:mod:`app.adapters.base` states that a mutation whose result the portal must
interpret — anything returning an :class:`~app.adapters.base.Operation` to
poll — belongs on a typed adapter method rather than the proxy, because the
proxy is a byte pipe and ``ActionResult.operations`` is unreachable through
it. That covers every write Nest has, so none of them is proxied.

Deletes answer ``204`` and would be safe to proxy by that rule, but they are
typed here too: ``delete_resource`` maps Nest's ``409`` onto
:class:`~app.adapter_errors.ResourceConflictError` so a confirm dialog can
tell "still referenced" from "gone", which a proxied 409 body cannot.

The practical effect is that Nest proxies no mutating verb at all, so the
registry-wide guard in ``test_adapter_registry`` keeps holding for it
unchanged.
"""

from __future__ import annotations

from typing import Final

from ..base import (
    ID_SLUG,
    ID_UUID,
    TENANT_PLACEHOLDER_PATTERN,
    RouteRule,
    product_scope,
)

__all__ = [
    "PRODUCT_TYPE",
    "SCOPE_READ",
    "SCOPE_MANAGE",
    "SCOPES",
    "API_PREFIX",
    "HEALTH_ENDPOINT",
    "READY_ENDPOINT",
    "CATALOG_PATH",
    "COLLECTION_DATA_RESOURCES",
    "COLLECTION_SNAPSHOTS",
    "COLLECTION_PROTECTION_POLICIES",
    "COLLECTION_SEARCH_POOLS",
    "COLLECTION_OPERATIONS",
    "COLLECTION_COST_REPORT",
    "COLLECTION_ANOMALIES",
    "COST_SUMMARY_SEGMENT",
    "tenant_path",
    "NEST_ROUTE_ALLOWLIST",
    "NEST_UNEXPOSED_ROUTES",
]

#: Registry key. Must match ``ADAPTER_REGISTRY``.
PRODUCT_TYPE: Final[str] = "nest"

#: Per-product scopes, built with the shared helper so the spelling is
#: defined once. ``resolve_scopes`` really mints these — see the model in
#: :mod:`app.adapters.base`. A product-local namespace (``nest:snapshot:read``,
#: which is what Nest's OWN middleware requires of the credential the operator
#: stores) is deliberately NOT used here: nothing in the portal mints it, so
#: every rule requiring one would answer 403 to every token the portal can
#: issue while looking more precisely secured.
SCOPE_READ: Final[str] = product_scope(PRODUCT_TYPE, "read")
SCOPE_MANAGE: Final[str] = product_scope(PRODUCT_TYPE, "manage")
SCOPES: Final[tuple[str, str]] = (SCOPE_READ, SCOPE_MANAGE)

#: Nest mounts its whole API under this prefix.
API_PREFIX: Final[str] = "/api/v1"

#: Liveness. Nest registers ``/health`` and ``/ready`` and does NOT register
#: ``/healthz`` anywhere (verified across ``apps/api`` and ``apps/manager``),
#: so the contract's default health path would 404 against a real Nest.
HEALTH_ENDPOINT: Final[str] = "/health"
READY_ENDPOINT: Final[str] = "/ready"

#: Resource-type catalogue — not tenant-scoped.
CATALOG_PATH: Final[str] = f"{API_PREFIX}/catalog"

COLLECTION_DATA_RESOURCES: Final[str] = "data-resources"
COLLECTION_SNAPSHOTS: Final[str] = "snapshots"
COLLECTION_PROTECTION_POLICIES: Final[str] = "protection-policies"
COLLECTION_SEARCH_POOLS: Final[str] = "search-pools"
COLLECTION_OPERATIONS: Final[str] = "operations"
COLLECTION_COST_REPORT: Final[str] = "cost-report"
COLLECTION_ANOMALIES: Final[str] = "anomalies"

#: ``/cost-report/summary`` — a literal sub-collection, not an id.
COST_SUMMARY_SEGMENT: Final[str] = "summary"


def tenant_path(tenant: str, *segments: str) -> str:
    """Build a tenant-scoped Nest path with no trailing slash.

    ``tenant`` is either a real external id (typed adapter methods) or the
    :data:`~app.adapters.base.TENANT_PLACEHOLDER` literal (allowlist rules,
    which are matched before substitution). Segments are joined verbatim and
    are always module literals — never caller input.
    """
    joined = "/".join(str(segment) for segment in segments if segment != "")
    base = f"{API_PREFIX}/tenants/{tenant}"
    return f"{base}/{joined}" if joined else base


#: The tenant placeholder as it appears inside a ``path_regex``. Braces are
#: regex repetition syntax, so the escaped form is required; the contract
#: publishes it pre-escaped precisely so no adapter hand-rolls it. It is a
#: constant token, not a variable slot — the caller writes ``{tenant}``
#: literally and the proxy substitutes the mapped external id AFTER matching.
_TENANT_RE: Final[str] = TENANT_PLACEHOLDER_PATTERN


def _rule(method: str, *segments: str, scope: str = SCOPE_READ) -> RouteRule:
    """Build one anchored tenant-scoped allowlist rule."""
    return RouteRule(method, rf"^{tenant_path(_TENANT_RE, *segments)}\Z", scope)


#: Deny-by-default proxy allowlist — GET only, see the module docstring.
#:
#: Ids are typed to the shape Nest really uses. Nest names its resources by a
#: DNS-style ``name`` (``<name>`` string converter, no ``<int:>``), so
#: :data:`ID_SLUG` is the honest shape; operations are UUIDs
#: (``str(uuid.uuid4())`` at ``handlers/dataresource.py:294``) and take the
#: tighter :data:`ID_UUID`.
NEST_ROUTE_ALLOWLIST: list[RouteRule] = [
    # -- liveness (no tenant) ------------------------------------------
    RouteRule("GET", rf"^{HEALTH_ENDPOINT}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{READY_ENDPOINT}\Z", SCOPE_READ),
    RouteRule("GET", rf"^{CATALOG_PATH}\Z", SCOPE_READ),
    # -- data resources -------------------------------------------------
    _rule("GET", COLLECTION_DATA_RESOURCES),
    _rule("GET", COLLECTION_DATA_RESOURCES, ID_SLUG),
    # -- operations (poll pass-through) ---------------------------------
    _rule("GET", COLLECTION_OPERATIONS, ID_UUID),
    # -- snapshots -------------------------------------------------------
    _rule("GET", COLLECTION_SNAPSHOTS),
    # -- protection policies --------------------------------------------
    _rule("GET", COLLECTION_PROTECTION_POLICIES),
    # -- search pools ----------------------------------------------------
    _rule("GET", COLLECTION_SEARCH_POOLS),
    _rule("GET", COLLECTION_SEARCH_POOLS, ID_SLUG),
    # -- billing / cost --------------------------------------------------
    _rule("GET", COLLECTION_COST_REPORT),
    _rule("GET", COLLECTION_COST_REPORT, COST_SUMMARY_SEGMENT),
    # -- anomalies -------------------------------------------------------
    _rule("GET", COLLECTION_ANOMALIES),
]


#: Concrete requests the proxy must refuse, with a real id in place of any
#: pattern. See :attr:`app.adapters.base.Adapter.unexposed_routes` — the
#: registry's structural id checks compare a pattern only against literals
#: THIS adapter declares, so a route Nest mounts and this adapter omits is
#: invisible to them and has to be named.
#:
#: The first group is the genuine hazard class: Nest's manager service
#: (``~/code/nest/apps/manager``) mounts credential, licence and
#: remote-execution routes under the SAME ``/api/v1`` prefix this adapter
#: uses. They are not reachable at the deployed Nest origin today — the
#: HTTPRoute at ``k8s/kustomize/base/httproute.yaml`` sends all of ``/api``
#: to ``nest-api`` and never to ``nest-manager`` — but "not currently routed"
#: is a deployment fact that can change without this file being reviewed,
#: whereas an allowlist that would admit them if they were is a defect now.
NEST_UNEXPOSED_ROUTES: tuple[tuple[str, str], ...] = (
    # Credential and session surface (nest-manager, routes/auth.py).
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/me"),
    # Remote SQL execution (nest-manager, routes/sql_files.py) — the single
    # most dangerous route either Nest service exposes.
    ("POST", "/api/v1/sql-files/1/execute"),
    ("POST", "/api/v1/sql-files/1/validate"),
    ("GET", "/api/v1/sql-files"),
    # Licence management (nest-manager, routes/license.py).
    ("GET", "/api/v1/license"),
    ("POST", "/api/v1/license"),
    ("DELETE", "/api/v1/license"),
    # Access control and stored connection secrets (nest-manager).
    ("GET", "/api/v1/permissions"),
    ("GET", "/api/v1/security-rules"),
    ("GET", "/api/v1/temporary-access"),
    ("GET", "/api/v1/servers"),
    ("GET", "/api/v1/servers/1"),
    ("GET", "/api/v1/cloud/providers"),
    ("GET", "/api/v1/cloud/providers/1"),
    # Internal operation control plane (nest-manager, app.py) — never a
    # portal-facing route under any deployment.
    ("POST", "/internal/v1/operations"),
    ("POST", "/internal/v1/operations/11111111-1111-4111-8111-111111111111/cancel"),
    # Prometheus scrape surface: operational data for every tenant on the
    # instance, not scoped to the caller's tenant.
    ("GET", "/metrics"),
)
