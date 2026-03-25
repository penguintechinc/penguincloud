"""Audit Log APIs — Query, filter, and export audit logs."""

import csv
import io
import json
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from .middleware import auth_required, get_current_user, role_required
from .models import get_db, get_user_tenant_role

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/logs", methods=["GET"])
@auth_required
def get_audit_logs():
    """Get audit logs with filtering and pagination."""
    user = get_current_user()
    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    offset = (page - 1) * per_page

    # Filters
    db = get_db()
    query = db.audit_logs.tenant_id == tenant_id

    action_filter = request.args.get("action")
    if action_filter:
        query &= db.audit_logs.action.contains(action_filter)

    resource_type_filter = request.args.get("resource_type")
    if resource_type_filter:
        query &= db.audit_logs.resource_type == resource_type_filter

    user_id_filter = request.args.get("user_id", type=int)
    if user_id_filter:
        query &= db.audit_logs.user_id == user_id_filter

    logs = db(query).select(
        orderby=~db.audit_logs.created_at,
        limitby=(offset, offset + per_page),
    )
    total = db(query).count()

    return jsonify({
        "logs": [log.as_dict() for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }), 200


@audit_bp.route("/export", methods=["GET"])
@auth_required
def export_audit_logs():
    """Export audit logs as CSV or JSON."""
    user = get_current_user()
    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    fmt = request.args.get("format", "json")
    limit = min(request.args.get("limit", 1000, type=int), 10000)

    db = get_db()
    logs = db(db.audit_logs.tenant_id == tenant_id).select(
        orderby=~db.audit_logs.created_at,
        limitby=(0, limit),
    )
    records = [log.as_dict() for log in logs]

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
                clean_row[k] = v.isoformat() if isinstance(v, datetime) else str(v) if v is not None else ""
            writer.writerow(clean_row)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    return jsonify({"logs": records, "count": len(records)}), 200
