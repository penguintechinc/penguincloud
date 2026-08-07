"""Dashboard API — Aggregated stats and health overview."""

from flask import Blueprint, jsonify, request

from .middleware import auth_required, get_current_user
from .models import (
    get_db,
    get_tenant_by_id,
    get_tenant_member_count,
    get_tenant_product_connections,
    get_tenant_product_count,
    get_user_tenant_role,
)

dashboard_bp = Blueprint("dashboard", __name__)


def _get_tenant_id():
    """Extract current tenant ID from JWT or query param."""
    from .middleware import decode_token, get_token_from_header

    token = get_token_from_header()
    if token:
        payload = decode_token(token)
        if payload and payload.get("current_tenant_id"):
            return payload["current_tenant_id"]
    return request.args.get("tenant_id", type=int)


@dashboard_bp.route("/overview", methods=["GET"])
@auth_required
def dashboard_overview():
    """Aggregated stats for all products in the current tenant."""
    user = get_current_user()
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    tenant = get_tenant_by_id(tenant_id)
    connections = get_tenant_product_connections(tenant_id)
    member_count = get_tenant_member_count(tenant_id)
    product_count = get_tenant_product_count(tenant_id)

    # Aggregate health stats
    health_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
    for conn in connections:
        status = conn.get("health_status", "unknown")
        health_counts[status] = health_counts.get(status, 0) + 1

    # Group by category
    from .models import PRODUCT_CATEGORIES

    category_counts = {}
    for conn in connections:
        ptype = conn.get("product_type", "generic")
        for cat, types in PRODUCT_CATEGORIES.items():
            if ptype in types:
                category_counts[cat] = category_counts.get(cat, 0) + 1
                break

    return jsonify({
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
    }), 200


@dashboard_bp.route("/health", methods=["GET"])
@auth_required
def dashboard_health():
    """Health matrix for all products."""
    user = get_current_user()
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    connections = get_tenant_product_connections(tenant_id)

    health_matrix = []
    for conn in connections:
        health_matrix.append({
            "id": conn["id"],
            "product_type": conn.get("product_type"),
            "display_name": conn.get("display_name"),
            "health_status": conn.get("health_status", "unknown"),
            "last_health_check": conn.get("last_health_check"),
            "base_url": conn.get("base_url"),
        })

    return jsonify({"health": health_matrix, "count": len(health_matrix)}), 200


@dashboard_bp.route("/activity", methods=["GET"])
@auth_required
def dashboard_activity():
    """Recent audit events for the tenant."""
    user = get_current_user()
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)

    db = get_db()
    logs = db(db.audit_logs.tenant_id == tenant_id).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )

    return jsonify({
        "activity": [log.as_dict() for log in logs],
        "count": len(logs),
    }), 200


@dashboard_bp.route("/alerts", methods=["GET"])
@auth_required
def dashboard_alerts():
    """Aggregated alerts — products with non-healthy status."""
    user = get_current_user()
    tenant_id = _get_tenant_id()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    connections = get_tenant_product_connections(tenant_id)

    alerts = []
    for conn in connections:
        status = conn.get("health_status", "unknown")
        if status in ["degraded", "unhealthy", "unknown"]:
            alerts.append({
                "product_id": conn["id"],
                "product_type": conn.get("product_type"),
                "display_name": conn.get("display_name"),
                "health_status": status,
                "last_health_check": conn.get("last_health_check"),
                "severity": "critical" if status == "unhealthy" else "warning",
            })

    return jsonify({"alerts": alerts, "count": len(alerts)}), 200
