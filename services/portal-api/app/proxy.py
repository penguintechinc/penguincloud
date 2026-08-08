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

import base64
import json
import logging
import uuid
from typing import Any
from urllib.parse import quote

from quart import Blueprint, make_response, request

from .adapters import get_adapter
from .adapters.base import AdapterContext, RBACEnforcer
from .adapters.transport import ResponseTooLargeError, get_transport
from .encryption import decrypt_value
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    get_product_connection_raw,
    get_product_tenant_map,
)
from .tenancy.authz import resolve_effective_role, resolve_scopes

logger = logging.getLogger(__name__)

proxy_bp = Blueprint("proxy", __name__)

#: Correlaton ID header name
CORRELATION_ID_HEADER = "X-Correlation-ID"

#: Maximum allowed response body size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024

#: Maximum accepted request body size (10 MB). Enforced before the outbound
#: call so an oversized upload is rejected by the portal rather than
#: forwarded to the product and rejected there.
MAX_REQUEST_SIZE = 10 * 1024 * 1024

#: What replaces a product credential found in a response.
REDACTION_MARKER = "[REDACTED]"

#: A credential shorter than this cannot be redacted from a response body
#: without also mangling unrelated content that happens to contain the same
#: few bytes. Rather than choose between leaking it and corrupting the
#: response, refuse to proxy at all: a 3-character API key is a
#: misconfiguration, and failing closed is the only safe reading of it.
MIN_REDACTABLE_CREDENTIAL_LEN = 4

#: Response headers never passed back to the caller. hop-by-hop headers
#: belong to this connection, and Set-Cookie would let a product plant a
#: cookie on the portal's origin.
_STRIPPED_RESPONSE_HEADERS = frozenset(
    {
        "transfer-encoding",
        "connection",
        "keep-alive",
        "set-cookie",
        "set-cookie2",
        "proxy-authenticate",
        "www-authenticate",
        "content-length",
        "content-encoding",
    }
)

#: Request headers never forwarded to the product. `authorization` is the
#: important one: the caller's portal JWT must not reach a third-party
#: product, and the slot is about to be filled with the product's own
#: credential anyway.
_STRIPPED_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "host",
        "connection",
        "content-length",
        "x-api-key",
    }
)


#: Placeholder an adapter's route_allowlist uses to mark where the product's
#: own tenant identifier belongs. The caller never supplies it — they address
#: their portal tenant, and this is where the mapped external id is spliced in.
TENANT_PLACEHOLDER = "{tenant}"


def _substitute_tenant(fragment: str, ctx: AdapterContext) -> str:
    """Replace the tenant placeholder with the mapped external identifier.

    The portal's tenant ids are its own; a product knows its customers by
    whatever ``product_tenant_map`` recorded (``external_id``). Substituting
    server-side means the outbound identity is derived from the mapping row
    rather than from anything the caller sent, so a caller cannot address
    another customer's data inside the product by editing the path.
    """
    if TENANT_PLACEHOLDER not in fragment:
        return fragment
    return fragment.replace(TENANT_PLACEHOLDER, quote(ctx.external_id, safe=""))


def _credential_material(ctx: AdapterContext) -> list[str]:
    """Every literal string form of the credential injected outbound.

    Includes the base64 blob for basic auth, because a product that echoes
    the raw ``Authorization`` header back leaks the encoded form, and an
    encoded credential is exactly as usable as a decoded one.
    """
    material = [value for value in (ctx.api_key, ctx.api_secret) if value]
    if ctx.auth_type == "basic" and ctx.api_key:
        encoded = base64.b64encode(f"{ctx.api_key}:{ctx.api_secret}".encode()).decode()
        material.append(encoded)
    return material


def _redact(payload: bytes, material: list[str]) -> bytes:
    """Strip every occurrence of the injected credential from a body.

    The proxy hands back whatever the product returned, and some products
    echo request headers on error ("unauthorized: Bearer sk-live-..."),
    render them into debug pages, or reflect query parameters. Any of those
    turns a proxied response into a credential disclosure to a caller who
    is authorized to *use* the connection but never to *read* its secret —
    which is the whole reason credentials are decrypted here and not handed
    to the browser.

    Applied unconditionally to every response on every path, including
    errors. An allowlist of "endpoints that might echo" would have to be
    right about a third party's behaviour forever.
    """
    for secret in material:
        payload = payload.replace(secret.encode(), REDACTION_MARKER.encode())
    return payload


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

        # A credential too short to redact safely means this connection
        # cannot be proxied without risking disclosure — refuse it here,
        # before any outbound call is made.
        credential_material = _credential_material(ctx)
        if any(
            len(secret) < MIN_REDACTABLE_CREDENTIAL_LEN
            for secret in credential_material
        ):
            logger.error(
                "proxy_request",
                extra={
                    "event": "credential_too_short_to_redact",
                    "connection_id": connection_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Product connection is misconfigured"}, 502

        # Build outbound URL. The portal tenant is substituted for the
        # product's own identifier from product_tenant_map: the caller
        # addresses their portal tenant, the product only ever sees its own.
        substituted_path = _substitute_tenant(proxy_path, ctx)
        outbound_url = f"{base_url}{substituted_path}"
        if request.query_string:
            query = _substitute_tenant(request.query_string.decode(), ctx)
            outbound_url += f"?{query}"

        # Collect request body and headers (stripping auth)
        body = await request.get_data()
        if len(body) > MAX_REQUEST_SIZE:
            logger.warning(
                "proxy_request",
                extra={
                    "event": "request_too_large",
                    "size": len(body),
                    "max_size": MAX_REQUEST_SIZE,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Request body too large"}, 413

        headers: dict[str, str] = {}
        for key, value in request.headers:
            if key.lower() not in _STRIPPED_REQUEST_HEADERS:
                headers[key] = value

        # Make the proxied request
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

            # Redact before anything is written to the response object, so
            # there is no ordering in which the raw body reaches the caller.
            response = await make_response(
                _redact(outbound_response.content, credential_material),
                outbound_response.status_code,
            )
            for key, value in outbound_response.headers.items():
                if key.lower() in _STRIPPED_RESPONSE_HEADERS:
                    continue
                # Header values get the same treatment as the body: a
                # product that reflects its auth header into a response
                # header leaks exactly as much as one that reflects it into
                # the body.
                response.headers[key] = _redact(
                    value.encode(), credential_material
                ).decode("utf-8", "replace")

            response.headers[CORRELATION_ID_HEADER] = corr_id

            # Audit log success
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

        except ResponseTooLargeError:
            # Raised by the transport when the body blew the cap before
            # the proxy's own check could see it.
            logger.warning(
                "proxy_request",
                extra={
                    "event": "response_too_large",
                    "connection_id": connection_id,
                    "correlation_id": corr_id,
                },
            )
            return {"error": "Response too large"}, 502

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
