"""Audit Log APIs — Query, filter, and export audit logs (async Quart).

Both routes are Enterprise-licensed. The commercial table sells
"Auditability & compliance (audit logs), advanced analytics" at Enterprise,
and *reading* the trail is the product being sold — the platform WRITES
audit rows on every tier regardless, because that is a security property,
not a feature. Gating the write would be a locked module; gating access to
it is the paywall the table describes.

``audit_export`` sat in ``licensing.NOT_YET_IMPLEMENTED`` while
``GET /export`` was fully built (CSV + JSON) and reachable behind nothing
but a tenant scope. A name parked in the "not built yet" set is exempt from
the mint-vs-enforce guard by construction, so the one thing that set must
never contain is something that is, in fact, built.

``audit_logs`` is a separate entry rather than reusing ``audit_export``:
one name meaning two capabilities is how half the call sites end up
checking a gate that does not mean what the reader thinks (see
``unlimited_hierarchy``, deleted for exactly this).
"""

import csv
import io
from datetime import datetime
from typing import Any

from quart import Blueprint, Response, request

from .authz import SCOPE_TENANTS_MANAGE, require_tenant_scope
from .license import require_feature
from .middleware import auth_required, get_current_user
from .models import get_db

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/logs", methods=["GET"])
@auth_required
@require_feature("audit_logs")
async def get_audit_logs() -> tuple[dict[str, Any], int]:
    """Get audit logs with filtering and pagination."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # The tenant audit trail is admin-only. Asked as a scope so a
    # delegated admin (authority from an ancestor, no membership row
    # here) is answered the same way the rest of the API answers them.
    denied = await require_tenant_scope(
        user["id"], tenant_id, SCOPE_TENANTS_MANAGE
    )
    if denied:
        return denied

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    offset = (page - 1) * per_page

    # Filters
    db = get_db()
    query = db.audit_logs.tenant_id == tenant_id

    action_filter = request.args.get("action")
    if action_filter:
        query &= db.audit_logs.action_type.contains(action_filter)

    resource_type_filter = request.args.get("resource_type")
    if resource_type_filter:
        query &= db.audit_logs.resource_type == resource_type_filter

    user_id_filter = request.args.get("user_id", type=int)
    if user_id_filter:
        query &= db.audit_logs.user_id == user_id_filter

    logs = await db(query).select(
        orderby=~db.audit_logs.created_at,
        limitby=(offset, offset + per_page),
    )
    total_rows = await db(query).select()
    total = len(total_rows)

    return {
        "logs": [dict(log) for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }, 200


@audit_bp.route("/export", methods=["GET"])
@auth_required
@require_feature("audit_export")
async def export_audit_logs() -> tuple[dict[str, Any], int] | dict[str, Any] | Response:
    """Export audit logs as CSV or JSON."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # The tenant audit trail is admin-only. Asked as a scope so a
    # delegated admin (authority from an ancestor, no membership row
    # here) is answered the same way the rest of the API answers them.
    denied = await require_tenant_scope(
        user["id"], tenant_id, SCOPE_TENANTS_MANAGE
    )
    if denied:
        return denied

    fmt = request.args.get("format", "json")
    limit = min(request.args.get("limit", 1000, type=int), 10000)

    db = get_db()
    logs = await db(db.audit_logs.tenant_id == tenant_id).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )
    records = [dict(log) for log in logs]

    if fmt == "csv":
        if not records:
            return Response("No data", mimetype="text/csv")

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        for row in records:
            # Convert datetime objects to strings
            clean_row = {}
            for k, v in row.items():
                clean_row[k] = (
                    v.isoformat()
                    if isinstance(v, datetime)
                    else str(v)
                    if v is not None
                    else ""
                )
            writer.writerow(clean_row)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    return {"logs": records, "count": len(records)}, 200
