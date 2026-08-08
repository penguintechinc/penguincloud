"""API Proxy/Relay Engine — v2 Deny-by-Default Forwarding.

Routes: /api/v1/products/<connection_id>/proxy/<path>

This is the UNTRUSTED-INPUT path into a connected product: the caller
supplies the path, method, query string and body. See
:mod:`app.adapters.base` for the full statement of which path is the
security boundary and why adapter methods are treated differently.

Security model:
- Request path is normalized and refused outright on traversal/control chars
- Request must match adapter's route_allowlist (deny-by-default, anchored)
- Scope check via RBACEnforcer against rule's required_scope
- A deactivated connection is refused before its credential is decrypted
- Request headers are ALLOW-listed; anything not named is dropped
- Product credentials injected from connection (decrypted)
- Portal tenant substituted with external product tenant ID
- Every call is audited — allowed AND refused, with rule/scope/tenant/status
- Request and response size capped at 10MB
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from typing import Any
from urllib.parse import quote

from quart import Blueprint, make_response, request

from .adapters import get_adapter
from .adapters.base import (
    AdapterContext,
    PathTraversalError,
    RBACEnforcer,
    RouteRule,
    normalize_proxy_path,
)
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

#: A caller may supply the correlation id so their own trace stitches to
#: ours, but the value is echoed into structured logs, into an outbound
#: header and back into a response header. Constrain it to a token charset
#: and a sane length: CR/LF here is log injection and header splitting, and
#: an unbounded value is a cheap way to bloat every log line it touches.
CORRELATION_ID_MAX_LEN = 128
_CORRELATION_ID_RE = re.compile(r"\A[A-Za-z0-9_.:-]{1,%d}\Z" % CORRELATION_ID_MAX_LEN)

#: Response headers never passed back to the caller. hop-by-hop headers
#: belong to this connection; Set-Cookie would let a product plant a cookie
#: on the portal's origin; and Location/Content-Location/Refresh would let a
#: product turn the portal into an open redirect, borrowing the portal's
#: origin to send an authenticated user anywhere it chooses.
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
        "location",
        "content-location",
        "refresh",
    }
)

#: Request headers forwarded to the product — an ALLOW-list, because this is
#: the one channel on a deny-by-default boundary where "everything not named
#: is permitted" would otherwise apply. A deny-list has to enumerate every
#: credential-bearing header name any product might honour, forever:
#: X-Auth-Token, Api-Key, Authentication, X-Forwarded-*, X-Original-URL and
#: whatever the next framework invents. Naming what is safe instead bounds
#: the problem to content negotiation and conditional requests.
#:
#: Deliberately absent:
#: - authorization / cookie: the caller's portal credentials must not reach
#:   a third party, and the slot is filled with the product's own credential
#: - user-agent / x-forwarded-*: caller-controlled identity claims the
#:   product may trust for its own access decisions
#: - host / content-length: recomputed by the transport for the real target
_FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "accept-charset",
        "accept-language",
        "content-type",
        "if-match",
        "if-modified-since",
        "if-none-match",
        "if-unmodified-since",
        "range",
    }
)


def _resolve_correlation_id() -> str:
    """Return a safe correlation id for this request.

    A caller-supplied value is honoured only if it matches the token charset
    and length bound; anything else is replaced with a server-generated
    uuid4 rather than rejected outright. Refusing the whole request over a
    malformed diagnostic header would fail a call for a reason unrelated to
    what it was asking for; substituting keeps the request working while
    guaranteeing nothing unvalidated reaches a log line, an outbound header
    or a response header.
    """
    supplied = request.headers.get(CORRELATION_ID_HEADER, "")
    if supplied and _CORRELATION_ID_RE.match(supplied):
        return supplied
    return str(uuid.uuid4())


def _substitute(fragment: str, adapter: Any, ctx: AdapterContext) -> str:
    """Apply the adapter's declared placeholder substitutions to a fragment.

    Which placeholders exist, and what fills each, is declared by the adapter
    (``path_substitutions``) rather than hard-coded here — see
    :class:`app.adapters.base.PathSubstitution`. Values are read from the
    :class:`AdapterContext`, every field of which is server-derived, so a
    caller cannot interpolate anything of their own by editing the path.
    """
    for substitution in getattr(adapter, "path_substitutions", ()):
        if substitution.placeholder not in fragment:
            continue
        value = str(getattr(ctx, substitution.context_attr, "") or "")
        fragment = fragment.replace(substitution.placeholder, quote(value, safe=""))
    return fragment


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


async def _audit_proxy_call(
    *,
    user_id: int,
    tenant_id: int,
    connection_id: int,
    outcome: str,
    status_code: int,
    correlation_id: str,
    method: str,
    path: str,
    product_type: str | None = None,
    rule: RouteRule | None = None,
    required_scope: str | None = None,
    detail: str | None = None,
) -> None:
    """Record one proxy decision — allowed or refused — in the audit trail.

    Refusals are audited as deliberately as successes. A deny-by-default
    boundary's denials ARE its signal: repeated ``route_not_allowed`` against
    one connection is somebody mapping the allowlist, repeated
    ``insufficient_scope`` is somebody probing for authority they lack, and
    ``connection_inactive`` says an operator's kill-switch is being tested.
    Warn-logging those (which is all the previous implementation did) keeps
    them out of the tenant-visible trail an admin actually reviews, so the
    only recorded evidence of an attack would be the calls that succeeded.

    ``action`` distinguishes the two families so either can be queried alone:
    ``proxy.get`` for a forwarded call, ``proxy.get.denied`` for a refusal.
    """
    changes: dict[str, Any] = {
        "outcome": outcome,
        "method": method,
        "path": path,
        "status_code": status_code,
        "correlation_id": correlation_id,
    }
    if product_type is not None:
        changes["product_type"] = product_type
    if rule is not None:
        changes["route_matched"] = f"{rule.method} {rule.path_regex}"
    if required_scope is not None:
        changes["scope_required"] = required_scope
    if detail is not None:
        changes["detail"] = detail

    suffix = "" if outcome == "allowed" else ".denied"
    try:
        await create_audit_log(
            user_id=user_id,
            action=f"proxy.{method.lower()}{suffix}",
            resource_type="product_connection",
            resource_id=str(connection_id),
            tenant_id=tenant_id,
            ip_address=request.remote_addr,
            changes=json.dumps(changes),
        )
    except Exception:  # pragma: no cover - trail must not break the decision
        # An audit write that fails must not convert a correct refusal into
        # a 500 (or, worse, into a forwarded request). Log loudly instead.
        logger.exception(
            "proxy_audit_write_failed",
            extra={"outcome": outcome, "correlation_id": correlation_id},
        )


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

    corr_id = _resolve_correlation_id()
    method = request.method

    try:
        # Get raw connection (with encrypted keys)
        conn_raw = await get_product_connection_raw(connection_id)
        if not conn_raw:
            # Not audited: there is no tenant to attribute the row to, and
            # inventing one would file a stranger's probe in some other
            # tenant's trail. The log line carries the caller.
            logger.warning(
                "proxy_request",
                extra={
                    "event": "connection_not_found",
                    "connection_id": connection_id,
                    "user_id": user["id"],
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

        async def _deny(
            outcome: str,
            body: dict[str, Any],
            status: int,
            *,
            rule: RouteRule | None = None,
            required_scope: str | None = None,
            detail: str | None = None,
        ) -> tuple[dict[str, Any], int]:
            """Audit a refusal, then return it."""
            logger.warning(
                "proxy_request",
                extra={
                    "event": outcome,
                    "connection_id": connection_id,
                    "user_id": user["id"],
                    "tenant_id": portal_tenant_id,
                    "method": method,
                    "path": proxy_path,
                    "correlation_id": corr_id,
                },
            )
            await _audit_proxy_call(
                user_id=user["id"],
                tenant_id=portal_tenant_id,
                connection_id=connection_id,
                outcome=outcome,
                status_code=status,
                correlation_id=corr_id,
                method=method,
                path=proxy_path,
                product_type=product_type,
                rule=rule,
                required_scope=required_scope,
                detail=detail,
            )
            return body, status

        # Resolve effective role in the tenant. Checked before anything that
        # would reveal connection state, so an outsider learns only that they
        # are not a member.
        effective_role = await resolve_effective_role(user["id"], portal_tenant_id)
        if effective_role is None:
            return await _deny(
                "unauthorized_tenant", {"error": "Not a member of this tenant"}, 403
            )

        # The operator's kill-switch. Enforced HERE, in the traffic path,
        # rather than in get_product_connection_raw: that accessor also feeds
        # the product's own management and schema endpoints, and a row that
        # vanishes when deactivated would make the connection invisible to
        # the very UI an operator uses to re-activate it — the kill-switch
        # would break the un-kill switch. Enforcement belongs where the
        # decision is, and this is the only path that carries traffic.
        #
        # Placed before decryption on purpose: a deactivated connection's
        # credential is never decrypted at all, so "deactivated" means the
        # secret stays at rest rather than merely not being sent.
        if not conn_raw.get("is_active"):
            return await _deny(
                "connection_inactive",
                {"error": "Product connection is inactive"},
                403,
            )

        # Refuse a malformed path before it is matched against anything.
        # `re.match(r"^/users", "/users/../admin")` is a match, so an
        # allowlist alone does not stop traversal; and the product, not the
        # portal, would be the one resolving the dot-segments.
        try:
            proxy_path = normalize_proxy_path(proxy_path)
        except PathTraversalError as exc:
            return await _deny(
                "malformed_path",
                {"error": "Invalid request path"},
                400,
                detail=str(exc),
            )

        # Resolve scopes from effective role
        scopes = await resolve_scopes(user["id"], portal_tenant_id)

        # Get product tenant mapping (external ID)
        mapping = await get_product_tenant_map(connection_id, portal_tenant_id)
        if not mapping:
            return await _deny(
                "tenant_mapping_not_found",
                {"error": "Product tenant mapping not found"},
                404,
            )

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

        # Check route allowlist (deny-by-default)
        matched_rule = None
        for rule in adapter.route_allowlist:
            if rule.matches(method, proxy_path):
                matched_rule = rule
                break

        if matched_rule is None:
            return await _deny("route_not_allowed", {"error": "Route not allowed"}, 404)

        # Check scope requirement
        enforcer = RBACEnforcer(matched_rule.required_scope)
        if not enforcer.enforce(scopes):
            return await _deny(
                "insufficient_scope",
                {"error": "Insufficient permissions"},
                403,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
            )

        # A credential too short to redact safely means this connection
        # cannot be proxied without risking disclosure — refuse it here,
        # before any outbound call is made.
        credential_material = _credential_material(ctx)
        if any(
            len(secret) < MIN_REDACTABLE_CREDENTIAL_LEN
            for secret in credential_material
        ):
            return await _deny(
                "credential_too_short_to_redact",
                {"error": "Product connection is misconfigured"},
                502,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
            )

        # Build outbound URL. The portal tenant is substituted for the
        # product's own identifier from product_tenant_map: the caller
        # addresses their portal tenant, the product only ever sees its own.
        substituted_path = _substitute(proxy_path, adapter, ctx)
        outbound_url = f"{base_url}{substituted_path}"
        if request.query_string:
            query = _substitute(request.query_string.decode(), adapter, ctx)
            outbound_url += f"?{query}"

        # Collect request body and headers (allow-list)
        body = await request.get_data()
        if len(body) > MAX_REQUEST_SIZE:
            return await _deny(
                "request_too_large",
                {"error": "Request body too large"},
                413,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
                detail=f"{len(body)} bytes",
            )

        headers: dict[str, str] = {}
        for key, value in request.headers:
            if key.lower() in _FORWARDED_REQUEST_HEADERS:
                headers[key] = value

        # Make the proxied request
        transport = await get_transport()
        try:
            outbound_response = await transport.request(
                method,
                outbound_url,
                ctx,
                headers=headers,
                content=body if body else None,
                timeout=30.0,
            )

            # Check response size
            if len(outbound_response.content) > MAX_RESPONSE_SIZE:
                return await _deny(
                    "response_too_large",
                    {"error": "Response too large"},
                    502,
                    rule=matched_rule,
                    required_scope=matched_rule.required_scope,
                    detail=f"{len(outbound_response.content)} bytes",
                )

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

            await _audit_proxy_call(
                user_id=user["id"],
                tenant_id=portal_tenant_id,
                connection_id=connection_id,
                outcome="allowed",
                status_code=outbound_response.status_code,
                correlation_id=corr_id,
                method=method,
                path=proxy_path,
                product_type=product_type,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
            )

            return response

        except ResponseTooLargeError:
            # Raised by the transport when the body blew the cap before
            # the proxy's own check could see it.
            return await _deny(
                "response_too_large",
                {"error": "Response too large"},
                502,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
            )

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
            await _audit_proxy_call(
                user_id=user["id"],
                tenant_id=portal_tenant_id,
                connection_id=connection_id,
                outcome="transport_error",
                status_code=502,
                correlation_id=corr_id,
                method=method,
                path=proxy_path,
                product_type=product_type,
                rule=matched_rule,
                required_scope=matched_rule.required_scope,
                detail=str(e),
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
