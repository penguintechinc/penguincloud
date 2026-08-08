"""Dashboard API — Aggregated stats and health overview."""

from typing import Any

from quart import Blueprint, request

from .middleware import auth_required, get_current_user
from .authz import SCOPE_TENANTS_READ, require_tenant_scope
from .models import (
    get_db,
    get_tenant_by_id,
    get_tenant_member_count,
    get_tenant_product_connections,
    get_tenant_product_count,
)

dashboard_bp = Blueprint("dashboard", __name__)


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
async def dashboard_overview() -> tuple[dict[str, Any], int]:
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

    return {
        "tenant": {
            "id": tenant_id,
            "name": tenant.get("name") if tenant else "",
            "plan": tenant.get("plan_tier") if tenant else "free",
        },
        "stats": {
            "total_products": product_count,
            "total_members": member_count,
            "health": health_counts,
            "categories": category_counts,
        },
        "products": connections,
    }, 200


@dashboard_bp.route("/health", methods=["GET"])
@auth_required
async def dashboard_health() -> tuple[dict[str, Any], int]:
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

    health_matrix: list[dict[str, Any]] = []
    for conn in connections:
        health_matrix.append(
            {
                "id": conn["id"],
                "product_type": conn.get("product_type"),
                "display_name": conn.get("display_name"),
                "health_status": conn.get("health_status", "unknown"),
                "last_health_check": conn.get("last_health_check"),
                "base_url": conn.get("base_url"),
            }
        )

    return {"health": health_matrix, "count": len(health_matrix)}, 200


@dashboard_bp.route("/activity", methods=["GET"])
@auth_required
async def dashboard_activity() -> tuple[dict[str, Any], int]:
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

    return {
        "activity": [dict(log) for log in logs],
        "count": len(logs),
    }, 200


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
