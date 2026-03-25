"""API Proxy/Relay Engine — Forwards requests to connected product APIs."""

import json
import logging

from flask import Blueprint, Response, jsonify, request

from .adapters import get_adapter
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    get_product_connection_by_id,
    get_product_connection_raw,
    get_user_tenant_role,
)

logger = logging.getLogger(__name__)

proxy_bp = Blueprint("proxy", __name__)


@proxy_bp.route("/<int:product_id>/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@auth_required
def proxy_request(product_id: int, subpath: str):
    """Forward request to a connected product's API."""
    user = get_current_user()

    # Validate connection exists
    conn_masked = get_product_connection_by_id(product_id)
    if not conn_masked:
        return jsonify({"error": "Product connection not found"}), 404

    # Check tenant membership
    role = get_user_tenant_role(user["id"], conn_masked["tenant_id"])
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    # Check product is active
    if not conn_masked.get("is_active"):
        return jsonify({"error": "Product connection is inactive"}), 403

    # Get raw connection (with encrypted keys) for proxy
    conn_raw = get_product_connection_raw(product_id)
    if not conn_raw:
        return jsonify({"error": "Product connection not found"}), 404

    adapter = get_adapter(conn_raw["product_type"], conn_raw)

    # Build proxy kwargs
    kwargs = {}
    if request.data:
        kwargs["data"] = request.data
        kwargs["headers"] = {"Content-Type": request.content_type or "application/json"}
    if request.args:
        kwargs["params"] = dict(request.args)

    # Forward request
    response = adapter.proxy_request(
        method=request.method,
        path=subpath,
        **kwargs,
    )

    # Audit log
    create_audit_log(
        user_id=user["id"],
        action=f"proxy.{request.method.lower()}",
        resource_type="product_connection",
        resource_id=str(product_id),
        tenant_id=conn_masked["tenant_id"],
        product_connection_id=product_id,
        request_body=subpath,
        response_status=response.status_code if hasattr(response, "status_code") else 0,
        ip_address=request.remote_addr,
    )

    return response
