"""Dashboard API — Aggregated stats and health overview."""

from dataclasses import dataclass
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_response

from .audit_view import AuditRecord, to_audit_records
from .authz import SCOPE_TENANTS_READ, require_tenant_scope
from .middleware import auth_required, get_current_user
from .models import (
    get_db,
    get_tenant_by_id,
    get_tenant_member_count,
    get_tenant_product_connections,
    get_tenant_product_count,
)
from .product_view import ProductConnection, to_product_connections

dashboard_bp = Blueprint("dashboard", __name__)


def _isoformat(value: Any) -> str | None:
    """Render a datetime column as ISO-8601, tolerating NULL or a string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


@dataclass(slots=True, frozen=True)
class TenantSummary:
    """The active tenant, as the dashboard overview names it.

    Attributes:
        id: Identifier of the tenant.
        name: Display name.
        plan: Licensed plan tier for this tenant.
    """

    id: int
    name: str
    plan: str


@dataclass(slots=True, frozen=True)
class HealthCounts:
    """Count of connections in each cached health state.

    Attributes:
        healthy: Connections last observed healthy.
        degraded: Connections last observed degraded.
        unhealthy: Connections last observed unhealthy.
        unknown: Connections never yet probed, or with no cached result.
    """

    healthy: int
    degraded: int
    unhealthy: int
    unknown: int


@dataclass(slots=True, frozen=True)
class DashboardStats:
    """Aggregate counters for the overview's stats block.

    Attributes:
        total_products: Number of product connections in this tenant.
        total_members: Number of members in this tenant.
        health: Connections grouped by cached health state.
        categories: Connection count by product category, e.g. networking.
    """

    total_products: int
    total_members: int
    health: HealthCounts
    categories: dict[str, int]


@dataclass(slots=True, frozen=True)
class DashboardOverviewResponse:
    """Envelope for GET /api/v1/dashboard/overview.

    Attributes:
        tenant: The active tenant this overview describes.
        stats: Aggregate counters across the tenant's connections.
        products: The tenant's product connections, credentials masked —
            the same projection GET /api/v1/products publishes.
    """

    tenant: TenantSummary
    stats: DashboardStats
    products: list[ProductConnection]


@dataclass(slots=True, frozen=True)
class HealthMatrixEntry:
    """One connection's row in the dashboard health matrix.

    Attributes:
        id: Identifier of the connection.
        product_type: Which product this connects to.
        display_name: Operator-assigned label for this connection.
        health_status: Cached health result: healthy, degraded, unhealthy
            or unknown.
        last_health_check: When the health status was last refreshed,
            ISO-8601.
        base_url: The connected product's base URL.
    """

    id: int
    product_type: str | None
    display_name: str | None
    health_status: str
    last_health_check: str | None
    base_url: str | None


@dataclass(slots=True, frozen=True)
class HealthMatrixResponse:
    """Envelope for GET /api/v1/dashboard/health.

    Attributes:
        health: One entry per product connection in the tenant.
        count: Number of entries returned.
    """

    health: list[HealthMatrixEntry]
    count: int


def _get_tenant_id() -> int | None:
    """Resolve the active tenant ID from verified claims, else query param.

    Reads the tenant that auth_required already verified and stashed on the
    request context — re-decoding the bearer token here would duplicate
    (and risk weakening) signature verification.
    """
    from .middleware import get_current_tenant_id

    claim_tenant = get_current_tenant_id()
    if claim_tenant:
        try:
            return int(claim_tenant)
        except ValueError:
            # A non-numeric tenant claim cannot address this schema's
            # integer tenants.id; fall through to the explicit param.
            pass
    return request.args.get("tenant_id", type=int)


@dashboard_bp.route("/overview", methods=["GET"])
@auth_required
@validate_response(DashboardOverviewResponse)
async def dashboard_overview() -> tuple[Any, int]:
    """Aggregated stats for all products in the current tenant."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # Scope, not direct membership: get_user_tenant_role answers "has a
    # tenant_members row", which a delegated MSP admin never does, so the
    # dashboard used to be blank for exactly the operator it exists for.
    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_READ)
    if denied:
        return denied

    tenant = await get_tenant_by_id(tenant_id)
    connections = await get_tenant_product_connections(tenant_id)
    member_count = await get_tenant_member_count(tenant_id)
    product_count = await get_tenant_product_count(tenant_id)

    # Aggregate health stats
    health_counts: dict[str, int] = {
        "healthy": 0,
        "degraded": 0,
        "unhealthy": 0,
        "unknown": 0,
    }
    for conn in connections:
        status = conn.get("health_status", "unknown")
        health_counts[status] = health_counts.get(status, 0) + 1

    # Group by category
    from .models import PRODUCT_CATEGORIES

    category_counts: dict[str, int] = {}
    for conn in connections:
        ptype = conn.get("product_type", "generic")
        for cat, types in PRODUCT_CATEGORIES.items():
            if ptype in types:
                category_counts[cat] = category_counts.get(cat, 0) + 1
                break

    return (
        DashboardOverviewResponse(
            tenant=TenantSummary(
                id=tenant_id,
                name=str(tenant.get("name")) if tenant else "",
                plan=str(tenant.get("plan_tier")) if tenant else "free",
            ),
            stats=DashboardStats(
                total_products=product_count,
                total_members=member_count,
                health=HealthCounts(
                    healthy=health_counts.get("healthy", 0),
                    degraded=health_counts.get("degraded", 0),
                    unhealthy=health_counts.get("unhealthy", 0),
                    unknown=health_counts.get("unknown", 0),
                ),
                categories=category_counts,
            ),
            products=to_product_connections(connections),
        ),
        200,
    )


@dashboard_bp.route("/health", methods=["GET"])
@auth_required
@validate_response(HealthMatrixResponse)
async def dashboard_health() -> tuple[Any, int]:
    """Health matrix for all products."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # Scope, not direct membership: get_user_tenant_role answers "has a
    # tenant_members row", which a delegated MSP admin never does, so the
    # dashboard used to be blank for exactly the operator it exists for.
    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_READ)
    if denied:
        return denied

    connections = await get_tenant_product_connections(tenant_id)

    health_matrix: list[HealthMatrixEntry] = []
    for conn in connections:
        health_matrix.append(
            HealthMatrixEntry(
                id=int(conn["id"]),
                product_type=conn.get("product_type"),
                display_name=conn.get("display_name"),
                health_status=str(conn.get("health_status", "unknown")),
                last_health_check=_isoformat(conn.get("last_health_check")),
                base_url=conn.get("base_url"),
            )
        )

    return HealthMatrixResponse(health=health_matrix, count=len(health_matrix)), 200


# Docstring below is exported as the ActivityResponse schema description;
# the rationale (this route returned raw audit rows on every tier) lives in
# app/audit_view.py, which is not published.
@dataclass(slots=True, frozen=True)
class ActivityResponse:
    """Recent audit events for one tenant, newest first.

    Attributes:
        activity: The audit entries.
        count: Number of entries returned.
    """

    activity: list[AuditRecord]
    count: int


@dashboard_bp.route("/activity", methods=["GET"])
@auth_required
@validate_response(ActivityResponse)
async def dashboard_activity() -> tuple[Any, int]:
    """Recent audit events for the tenant."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # Scope, not direct membership: get_user_tenant_role answers "has a
    # tenant_members row", which a delegated MSP admin never does, so the
    # dashboard used to be blank for exactly the operator it exists for.
    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_READ)
    if denied:
        return denied

    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)

    db = get_db()
    logs = await db(db.audit_logs.tenant_id == tenant_id).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )

    # Projected, not passed through. This route is reachable on EVERY tier
    # (see AUDIT_ROUTES_INTENTIONALLY_UNLICENSED) and was returning the raw
    # audit row — request_body, user_agent, metadata and all — making the
    # least-gated audit surface in the portal also the most revealing one.
    records = to_audit_records(logs)
    return ActivityResponse(activity=records, count=len(records)), 200


@dashboard_bp.route("/alerts", methods=["GET"])
@auth_required
async def dashboard_alerts() -> tuple[dict[str, Any], int]:
    """Aggregated alerts — products with non-healthy status."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # Scope, not direct membership: get_user_tenant_role answers "has a
    # tenant_members row", which a delegated MSP admin never does, so the
    # dashboard used to be blank for exactly the operator it exists for.
    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_READ)
    if denied:
        return denied

    connections = await get_tenant_product_connections(tenant_id)

    alerts: list[dict[str, Any]] = []
    for conn in connections:
        status = conn.get("health_status", "unknown")
        if status in ["degraded", "unhealthy", "unknown"]:
            alerts.append(
                {
                    "product_id": conn["id"],
                    "product_type": conn.get("product_type"),
                    "display_name": conn.get("display_name"),
                    "health_status": status,
                    "last_health_check": conn.get("last_health_check"),
                    "severity": "critical" if status == "unhealthy" else "warning",
                }
            )

    return {"alerts": alerts, "count": len(alerts)}, 200
