"""Shared authorisation and context building for product-backed routes.

Extracted from :mod:`app.operations_api`, which owned these privately until a
second module — :mod:`app.resources_api` — needed exactly the same ordering.
Two copies of an authorisation sequence is how one of them ends up missing the
deactivation check, so there is one.

The ordering below is the contract, and it is deliberate: membership, then
scope, then credential decryption. A non-member learns nothing about the
connection (404, not 403 — see :func:`resolve_product_context`), and an
unauthorised request never causes a stored secret to be decrypted at all.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Final

from quart import jsonify, request

from . import flags
from .adapters.base import (
    UPSTREAM_RESPONSE_HEADER,
    AdapterContext,
    AdapterError,
    adapter_error_status,
    product_scope,
)
from .authz import require_tenant_scope
from .encryption import decrypt_value
from .middleware import get_current_user
from .models import (
    get_product_connection_by_id,
    get_product_connection_raw,
    get_product_tenant_map,
)
from .tenancy.authz import resolve_effective_role

__all__ = [
    "ACTION_MANAGE",
    "ACTION_READ",
    "NOT_FOUND",
    "adapter_failure",
    "iso",
    "resolve_product_context",
]

logger = logging.getLogger(__name__)

#: The single "you get nothing" answer. Shared so that "no such connection"
#: and "not your tenant" are byte-identical — see the oracle note in
#: :func:`resolve_product_context`.
NOT_FOUND: Final[tuple[dict[str, Any], int]] = (
    {"error": "Product connection not found"},
    404,
)

#: Scope actions these routes require. Reads list and poll; anything that
#: changes product state is a mutation.
ACTION_READ: Final[str] = "read"
ACTION_MANAGE: Final[str] = "manage"


def iso(value: datetime | None) -> str | None:
    """Render a timestamp for the wire, or None."""
    return value.isoformat() if value is not None else None


async def resolve_product_context(
    product_id: int, action: str
) -> tuple[AdapterContext, str, None] | tuple[None, None, tuple[dict[str, Any], int]]:
    """Authorise the caller and build the adapter context.

    ``action`` is ``read`` or ``manage``; the required scope is derived from
    it and the connection's product type, so these routes participate in the
    per-product scope model rather than stopping at the coarse grant. See
    "Per-product scopes" in :mod:`app.adapters.base`.

    Returns ``(ctx, product_type, None)`` on success or
    ``(None, None, error_response)``. Ordering is deliberate and matches the
    proxy: membership first, then scope, so a non-member learns nothing about
    the connection, and credential decryption last, so an unauthorised request
    never causes a secret to be decrypted at all.
    """
    user = get_current_user()
    if not user:
        return None, None, ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return None, None, NOT_FOUND

    # Membership before anything that distinguishes this connection from a
    # non-existent one, and a 404 rather than a 403 when it fails.
    #
    # A 403 here would answer "this id exists, in a tenant that is not yours"
    # while a 404 answers "no such id" — so a caller in any tenant could walk
    # product_ids and map every connection in the deployment, including how
    # many other tenants exist and roughly when each was created. The scope
    # check below still answers 403, which is correct and not an oracle: it
    # is only reachable by someone already established as a member of that
    # tenant, so it discloses nothing they did not already have.
    portal_tenant_id = conn["tenant_id"]
    if await resolve_effective_role(user["id"], portal_tenant_id) is None:
        return None, None, NOT_FOUND

    product_type_for_scope = str(conn.get("product_type", ""))
    denied = await require_tenant_scope(
        user["id"],
        portal_tenant_id,
        product_scope(product_type_for_scope, action),
    )
    if denied:
        return None, None, denied

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return None, None, NOT_FOUND

    if not conn_raw.get("is_active", True):
        # Same kill switch the proxy honours: a deactivated connection must
        # not have its credential decrypted, let alone used.
        return None, None, ({"error": "Product connection is deactivated"}, 403)

    # The OTHER kill switch, and it belongs here for the same reason the
    # deactivation check does: this is the shared path every typed product
    # route takes, so gating it once gates all of them.
    #
    # `penguincloud.{product}` was enforced only at connection create and in
    # the proxy, which left the whole typed surface — operations, logs,
    # cancel, resource create/delete, resource actions, metrics — running
    # against a module the operator had switched off. "Disable a module
    # without a redeploy" was not true of the routes that do the work.
    #
    # Before decryption, deliberately: a disabled module's stored credential
    # is never decrypted at all, so "off" means the secret stays at rest
    # rather than merely not being sent.
    gate = await flags.product_gate_refusal(str(conn_raw["product_type"]), str(user["id"]))
    if gate is not None:
        return None, None, gate

    mapping = await get_product_tenant_map(product_id, conn["tenant_id"])
    ctx = AdapterContext(
        connection_id=product_id,
        portal_tenant_id=conn["tenant_id"],
        external_id=(mapping or {}).get("external_id", ""),
        external_kind=(mapping or {}).get("external_kind", ""),
        base_url=conn_raw.get("base_url", ""),
        auth_type=conn_raw.get("auth_type", "bearer"),
        api_key=(decrypt_value(conn_raw.get("api_key", "")) if conn_raw.get("api_key") else ""),
        api_secret=(
            decrypt_value(conn_raw.get("api_secret", "")) if conn_raw.get("api_secret") else ""
        ),
        correlation_id=request.headers.get("X-Correlation-ID", ""),
    )
    return ctx, str(conn_raw["product_type"]), None


def adapter_failure(exc: AdapterError, product_id: int, operation: str) -> tuple[Any, int]:
    """Render an adapter error using the taxonomy's shared status mapping.

    The product's URL and headers never reach the response — only the
    adapter's own message. That message is NOT portal-neutral, despite the
    taxonomy's intent: every product's ``raise_for_status`` (e.g.
    ``adapters/nest/responses.py``) builds it as ``f"{context}: {detail}"``,
    where ``detail`` is read straight out of the product's own response body.
    A Nest 502 becomes ``"create_resource:database: connection refused to
    10.0.4.17"`` here — the product's own text, unredacted, embedded in a
    portal-generated envelope.

    So the response is marked with ``UPSTREAM_RESPONSE_HEADER``, same as
    ``app.proxy`` marks a forwarded body — this is the OTHER path
    upstream-derived text reaches an API response by, and the webui client
    only trusts an UNMARKED body, so leaving this one unmarked was the
    regression a content-shape denylist used to (imperfectly) cover. See
    that constant's doc comment in ``adapters/base.py`` for the full
    rationale, including why every ``AdapterError`` subclass is marked
    uniformly rather than trying to except the ones that happen not to
    carry upstream text today.

    LATENT TRAP for whoever adds the first ``@validate_response`` for a
    non-2xx status on a route that calls this function: returning a
    pre-built ``Response`` (this function's return value) into a route
    whose status happens to match a status THAT route declares via
    ``@validate_response(Model, status_code=...)`` hits quart_schema's own
    ``isinstance(value, Response) and status == status_code`` branch, which
    raises ``ResponseHeadersValidationError`` — visible to a caller as a
    500, not the intended 404/409/422/429/502. Harmless today: every
    current caller (``resources_api.py``, ``operations_api.py``) only
    declares ``@validate_response`` for the SUCCESS status, never for one
    of :data:`_ERROR_STATUS`'s codes. If that changes, this function needs
    the same 3-tuple ``(model, status, headers)`` return
    ``health_api.get_products_health`` uses instead of a ``Response``
    object — see that function's comment for why.
    """
    logger.info(
        "product_request_failed",
        extra={
            "product_id": product_id,
            "operation": operation,
            "error_type": type(exc).__name__,
        },
    )
    response = jsonify({"error": str(exc)})
    response.headers[UPSTREAM_RESPONSE_HEADER] = "true"
    return response, adapter_error_status(exc)
