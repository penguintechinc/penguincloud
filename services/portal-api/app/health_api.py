"""Cached product health endpoint (Phase 6 -- go-backend replacement).

Serves what ``app.health_poller``'s background sweep already wrote to the
health cache (``app.health_cache``). This route NEVER triggers a live probe
of a connected product -- that is ``POST /products/<id>/test``
(``app/products.py``), a separate, on-demand, single-connection operation.
Requirement 3 is explicit about this: "never triggers live polls".

``include_children`` mirrors the Phase 2 subtree rule already established
by ``tenants.list_user_tenants`` and ``tenants.get_dashboard_rollup``: a
caller only sees a descendant tenant's connections when they hold
``tenants:manage`` on the tenant named by ``tenant_id`` -- holding
``products:read`` there is enough to see that tenant's OWN connections, not
its descendants'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_response

from .authz import SCOPE_PRODUCTS_READ, SCOPE_TENANTS_MANAGE, has_tenant_scope, require_tenant_scope
from .health_cache import get_health
from .middleware import auth_required, get_current_tenant_id, get_current_user
from .models import get_tenant_product_connections
from .tenancy import get_hierarchy, tenancy_aware

health_api_bp = Blueprint("health_api", __name__)


@dataclass(slots=True, frozen=True)
class ProductHealthEntry:
    """One product connection's cached health, as the endpoint reports it."""

    connection_id: int
    tenant_id: int
    product_type: str
    display_name: str
    status: str
    latency_ms: int | None
    checked_at: str | None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class ProductsHealthResponse:
    """Envelope for GET /api/v1/products/health."""

    products: list[ProductHealthEntry]
    count: int


def _resolve_tenant_id() -> int | None:
    """Active tenant from the verified JWT claim, falling back to the query param.

    Mirrors ``dashboard_api._get_tenant_id``: the claim is authoritative
    when present (re-deriving it from a request query param would be a
    second, weaker opinion about who the caller is), and the query param
    exists only for the unscoped-token bootstrap paths every other
    ``/products/*`` route already accepts it for. Either way the value is
    just a *selector* -- ``require_tenant_scope`` below is what actually
    authorises it, so a caller cannot widen what they see by editing the
    query string.

    Consequence worth stating plainly: an explicit ``?tenant_id=`` is
    SILENTLY IGNORED whenever the caller's token already carries an
    active tenant claim -- the claim always wins, the query param is only
    ever consulted for an unscoped token. A caller passing both expecting
    the query param to select a *different* tenant than the one their
    token is switched into will not get that; they get 403 (if
    unauthorised for the claimed tenant) or the claimed tenant's data
    (if authorised), never the queried one.
    """
    claim_tenant = get_current_tenant_id()
    if claim_tenant:
        try:
            return int(claim_tenant)
        except ValueError:
            pass
    return request.args.get("tenant_id", type=int)


@health_api_bp.route("/health", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(ProductsHealthResponse)
async def get_products_health() -> tuple[Any, int]:
    """Cached health for the caller's tenant, optionally + its subtree.

    Query params:
      - tenant_id: required unless the token carries an active
        tenant claim.
      - include_children=true: also include descendant tenants'
        connections, when the caller holds tenants:manage on
        tenant_id (see module docstring).
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    tenant_id = _resolve_tenant_id()
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    tenant_ids = {tenant_id}
    include_children = request.args.get("include_children", "false").lower() == "true"
    if include_children and await has_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_MANAGE):
        # Mirrors tenants.list_user_tenants' identical guard (tenants.py):
        # get_hierarchy raises ValueError for a tenant_id whose row no
        # longer exists. require_tenant_scope above already read a scope
        # for this tenant_id moments ago, so the row existed then -- a
        # ValueError here means it was deleted in the gap, not that the
        # caller did anything wrong. Falling back to the caller's own
        # tenant alone (no subtree) is the same "row read moments ago"
        # race the mirror accepts, not a new failure mode.
        try:
            hierarchy = await get_hierarchy(tenant_id)
        except ValueError:  # pragma: no cover - row read moments ago
            hierarchy = None
        if hierarchy is not None:
            tenant_ids.update(hierarchy.descendants)

    entries: list[ProductHealthEntry] = []
    for tid in sorted(tenant_ids):
        for conn in await get_tenant_product_connections(tid):
            connection_id = int(conn["id"])
            cached = await get_health(connection_id)
            entries.append(
                ProductHealthEntry(
                    connection_id=connection_id,
                    tenant_id=tid,
                    product_type=str(conn.get("product_type") or "generic"),
                    display_name=str(conn.get("display_name") or ""),
                    status=cached.status if cached else "unknown",
                    latency_ms=cached.latency_ms if cached else None,
                    checked_at=cached.checked_at if cached else None,
                    error=cached.error if cached else None,
                )
            )

    return ProductsHealthResponse(products=entries, count=len(entries)), 200
