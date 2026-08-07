"""API Proxy/Relay Engine — Forwards requests to product APIs (async Quart)."""

import asyncio
import logging
from typing import Any

from quart import Blueprint, request

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


@proxy_bp.route(
    "/<int:product_id>/<path:subpath>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
@auth_required
async def proxy_request(product_id: int, subpath: str) -> Any:
    """Forward request to a connected product's API."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    # Validate connection exists
    conn_masked = await get_product_connection_by_id(product_id)
    if not conn_masked:
        return {"error": "Product connection not found"}, 404

    # Check tenant membership
    role = await get_user_tenant_role(user["id"], conn_masked["tenant_id"])
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    # Check product is active
    if not conn_masked.get("is_active"):
        return {"error": "Product connection is inactive"}, 403

    # Get raw connection (with encrypted keys) for proxy
    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return {"error": "Product connection not found"}, 404

    adapter = get_adapter(conn_raw["product_type"], conn_raw)

    # Build proxy kwargs
    kwargs: dict[str, Any] = {}
    data = await request.get_data()
    if data:
        kwargs["data"] = data
        kwargs["headers"] = {
            "Content-Type": request.content_type or "application/json"
        }
    args = request.args
    if args:
        kwargs["params"] = dict(args)

    # Forward request (blocking adapter call)
    response = await asyncio.to_thread(
        adapter.proxy_request,
        request.method,
        subpath,
        **kwargs,
    )

    # Audit log
    await create_audit_log(
        user_id=user["id"],
        action=f"proxy.{request.method.lower()}",
        resource_type="product_connection",
        resource_id=str(product_id),
        tenant_id=conn_masked["tenant_id"],
        ip_address=request.remote_addr,
    )

    return response
