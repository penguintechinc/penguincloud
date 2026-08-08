"""API Proxy/Relay Engine — v2 Deny-by-Default Forwarding.

Routes: /api/v1/products/<connection_id>/proxy/<path>

Security model:
- Request must match adapter's route_allowlist (deny-by-default)
- Scope check via RBACEnforcer against rule's required_scope
- Inbound Authorization header stripped
- Product credentials injected from connection (decrypted)
- Portal tenant substituted with external product tenant ID
- Audit log records every call (rule matched, scope result, status)
- Response size capped at 10MB
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from quart import Blueprint, make_response, request

from .adapters import get_adapter
from .adapters.base import AdapterContext, RBACEnforcer
from .encryption import decrypt_value
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    get_product_connection_raw,
    get_product_tenant_map,
)
from .tenancy.authz import resolve_effective_role

logger = logging.getLogger(__name__)

proxy_bp = Blueprint("proxy", __name__)

#: Correlaton ID header name
CORRELATION_ID_HEADER = "X-Correlation-ID"

#: Maximum allowed response body size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024


@proxy_bp.route(
    "/api/v1/products/<int:connection_id>/proxy/<path:proxy_path>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
@auth_required
async def proxy_request(connection_id: int, proxy_path: str) -> Any:
    """Forward request to a connected product's API.

    Deny-by-default: request must match adapter's route_allowlist.
    """
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    # Generate correlation ID for request tracking
    corr_id = request.headers.get(CORRELATION_ID_HEADER, str(uuid.uuid4()))

    try:
        # Get raw connection (with encrypted keys)
        conn_raw = await get_product_connection_raw(connection_id)
        if not conn_raw:
            logger.warning(
                "proxy_request",
                extra={
                    "event": "connection_not_found",
                    "connection_id": connection_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Product connection not found"}, 404

        product_type: str = str(conn_raw.get("product_type", "unknown"))
        portal_tenant_id_maybe = conn_raw.get("tenant_id")
        if not isinstance(portal_tenant_id_maybe, int):
            logger.error(
                "proxy_request",
                extra={
                    "event": "invalid_tenant_id",
                    "connection_id": connection_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Invalid connection configuration"}, 500
        portal_tenant_id: int = portal_tenant_id_maybe
        base_url: str = str(conn_raw.get("base_url", "")).rstrip("/")

        # Resolve effective role in the tenant
        effective_role = await resolve_effective_role(user["id"], portal_tenant_id)
        if effective_role is None:
            logger.warning(
                "proxy_request",
                extra={
                    "event": "unauthorized_tenant",
                    "connection_id": connection_id,
                    "user_id": user["id"],
                    "tenant_id": portal_tenant_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Not a member of this tenant"}, 403

        # Resolve scopes from effective role
        from .tenancy.authz import resolve_scopes

        scopes = await resolve_scopes(user["id"], portal_tenant_id)

        # Get product tenant mapping (external ID)
        mapping = await get_product_tenant_map(connection_id, portal_tenant_id)
        if not mapping:
            logger.warning(
                "proxy_request",
                extra={
                    "event": "tenant_mapping_not_found",
                    "connection_id": connection_id,
                    "portal_tenant_id": portal_tenant_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Product tenant mapping not found"}, 404

        external_id = mapping.get("external_id", "")
        external_kind = mapping.get("external_kind", "")

        # Decrypt credentials
        api_key = (
            decrypt_value(conn_raw.get("api_key", ""))
            if conn_raw.get("api_key")
            else ""
        )
        api_secret = (
            decrypt_value(conn_raw.get("api_secret", ""))
            if conn_raw.get("api_secret")
            else ""
        )

        # Build adapter context
        ctx = AdapterContext(
            connection_id=connection_id,
            portal_tenant_id=portal_tenant_id,
            external_id=external_id,
            external_kind=external_kind,
            base_url=base_url,
            auth_type=conn_raw.get("auth_type", "bearer"),
            api_key=api_key,
            api_secret=api_secret,
            correlation_id=corr_id,
            scopes=scopes,
        )

        # Get adapter instance
        adapter = get_adapter(product_type, ctx)

        # Normalize proxy path: ensure it starts with /
        if not proxy_path.startswith("/"):
            proxy_path = "/" + proxy_path

        # Check route allowlist (deny-by-default)
        matched_rule = None
        for rule in adapter.route_allowlist:
            if rule.matches(request.method, proxy_path):
                matched_rule = rule
                break

        if matched_rule is None:
            logger.warning(
                "proxy_request",
                extra={
                    "event": "route_not_allowed",
                    "method": request.method,
                    "path": proxy_path,
                    "connection_id": connection_id,
                    "product_type": product_type,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Route not allowed"}, 404

        # Check scope requirement
        enforcer = RBACEnforcer(matched_rule.required_scope)
        if not enforcer.enforce(scopes):
            logger.warning(
                "proxy_request",
                extra={
                    "event": "insufficient_scope",
                    "required_scope": matched_rule.required_scope,
                    "granted_scopes": scopes,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Insufficient permissions"}, 403

        # Build outbound URL
        outbound_url = f"{base_url}{proxy_path}"
        if request.query_string:
            outbound_url += f"?{request.query_string.decode()}"

        # Collect request body and headers (stripping auth)
        body = await request.get_data()
        headers: dict[str, str] = {}
        for key, value in request.headers:
            if key.lower() not in ("authorization", "cookie", "host", "connection"):
                headers[key] = value

        # Make the proxied request
        from .adapters.transport import get_transport

        transport = await get_transport()
        try:
            outbound_response = await transport.request(
                request.method,
                outbound_url,
                ctx,
                headers=headers,
                content=body if body else None,
                timeout=30.0,
            )

            # Check response size
            if len(outbound_response.content) > MAX_RESPONSE_SIZE:
                logger.warning(
                    "proxy_request",
                    extra={
                        "event": "response_too_large",
                        "size": len(outbound_response.content),
                        "max_size": MAX_RESPONSE_SIZE,
                        "correlation_id": corr_id,
                    },
                )
                return {"error": "Response too large"}, 502

            # Build response, stripping sensitive headers
            response = await make_response(
                outbound_response.content, outbound_response.status_code
            )
            for key, value in outbound_response.headers.items():
                if key.lower() not in ("transfer-encoding", "connection", "set-cookie"):
                    response.headers[key] = value

            response.headers[CORRELATION_ID_HEADER] = corr_id

            # Audit log success
            import json

            changes = json.dumps(
                {
                    "product_type": product_type,
                    "path": proxy_path,
                    "status_code": outbound_response.status_code,
                    "route_matched": f"{matched_rule.method} {matched_rule.path_regex}",
                    "scope_required": matched_rule.required_scope,
                }
            )
            await create_audit_log(
                user_id=user["id"],
                action=f"proxy.{request.method.lower()}",
                resource_type="product_connection",
                resource_id=str(connection_id),
                tenant_id=portal_tenant_id,
                ip_address=request.remote_addr,
                changes=changes,
            )

            return response

        except Exception as e:
            logger.error(
                "proxy_request",
                extra={
                    "event": "proxy_error",
                    "error": str(e),
                    "connection_id": connection_id,
                    "product_type": product_type,
                    "path": proxy_path,
                    "correlation_id": corr_id,
                },
            )
            import json

            changes = json.dumps({"error": str(e)})
            await create_audit_log(
                user_id=user["id"],
                action=f"proxy.{request.method.lower()}.error",
                resource_type="product_connection",
                resource_id=str(connection_id),
                tenant_id=portal_tenant_id,
                ip_address=request.remote_addr,
                changes=changes,
            )
            return {"error": "Proxy request failed"}, 502

    except Exception as e:
        logger.exception(
            "proxy_request",
            extra={
                "event": "unhandled_error",
                "error": str(e),
                "correlation_id": corr_id,
            },
        )
        return {"error": "Internal server error"}, 500
