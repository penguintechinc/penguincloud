"""Long-running operation APIs — the endpoints the UI polls.

Companion to the :class:`~app.adapters.base.Operation` contract added in
Phase 4G. A product action that returns ``202`` is only half an integration;
without a poll route the browser has no way to learn that a deploy finished,
and the portal would have to either block a request until the product was
done or lie about the outcome.

Routes (all under ``/api/v1/products/<product_id>``):

===================================================  ======================
``GET    /operations``                               list, newest first
``GET    /operations/<kind>/<operation_id>``         poll one
``POST   /operations/<kind>/<operation_id>/cancel``  request cancellation
``GET    /operations/<kind>/<operation_id>/logs``    log lines
===================================================  ======================

``kind`` is in the path rather than a query parameter because it is part of
the operation's identity, not a filter: :attr:`Operation.kind` selects which
of a product's poll routes answers, so ``kind`` + ``id`` together are the
key. That also makes the URL reconstructible from an ``Operation`` alone,
which is what lets the UI poll an object it was handed without tracking
where it came from.

Security
========
Every route resolves the connection, enforces a tenant-scoped portal scope,
then decrypts the credential — in that order, matching the ordering
established for the proxy in Phase 3 (A1). Reads require ``products:read``;
cancel is a mutation and requires ``products:manage``. Nothing here accepts a
caller-supplied path: ``kind`` is validated by the adapter against a literal
set, and ``operation_id`` is validated before it can reach a URL segment.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from quart import Blueprint, request

from .adapters import get_adapter
from .adapters.base import (
    AdapterContext,
    AdapterError,
    Operation,
    OperationState,
    adapter_error_status,
)
from .authz import SCOPE_PRODUCTS_MANAGE, SCOPE_PRODUCTS_READ, require_tenant_scope
from .encryption import decrypt_value
from .middleware import auth_required, get_current_user
from .models import (
    get_product_connection_by_id,
    get_product_connection_raw,
    get_product_tenant_map,
)
from .tenancy import tenancy_aware

logger = logging.getLogger(__name__)

operations_bp = Blueprint("operations", __name__)

#: Upper bound on a page of operations. A poll loop that asks for thousands
#: of rows every few seconds is a self-inflicted load problem.
_MAX_PER_PAGE = 100

#: Upper bound on log lines per request, matching Gough's own cap.
_MAX_TAIL = 1000


@dataclass(slots=True, frozen=True)
class OperationView:
    """Wire shape for one operation.

    An explicit DTO rather than serialising the dataclass directly: the
    response schema is enforced field by field, so a future field added to
    :class:`Operation` for internal use cannot silently start being published
    (see the output-validation rule — an unvalidated response is as dangerous
    as an unvalidated request, just harder to notice).
    """

    id: str
    kind: str
    state: str
    status: str
    is_terminal: bool
    resource_id: str | None
    resource_kind: str | None
    progress: float | None
    detail: str | None
    error: str | None
    created_at: str | None
    updated_at: str | None
    completed_at: str | None

    @classmethod
    def of(cls, operation: Operation) -> OperationView:
        """Project an adapter Operation onto the wire shape.

        ``is_terminal`` is published even though it is derivable from
        ``state``: it is the flag the UI's refetch loop branches on, and
        deriving it client-side means every consumer re-implements the
        terminal-state set and one of them gets it wrong.
        """
        return cls(
            id=operation.id,
            kind=operation.kind,
            state=operation.state.value,
            status=operation.status,
            is_terminal=operation.state.is_terminal,
            resource_id=operation.resource_id,
            resource_kind=operation.resource_kind,
            progress=operation.progress,
            detail=operation.detail,
            error=operation.error,
            created_at=_iso(operation.created_at),
            updated_at=_iso(operation.updated_at),
            completed_at=_iso(operation.completed_at),
        )


def _iso(value: datetime | None) -> str | None:
    """Render a timestamp for the wire, or None."""
    return value.isoformat() if value is not None else None


async def _resolve(
    product_id: int, scope: str
) -> tuple[AdapterContext, str, None] | tuple[None, None, tuple[dict[str, Any], int]]:
    """Authorise the caller and build the adapter context.

    Returns ``(ctx, product_type, None)`` on success or
    ``(None, None, error_response)``. Ordering is deliberate and matches the
    proxy: membership/scope first, so a non-member learns nothing about the
    connection, and credential decryption last, so an unauthorised request
    never causes a secret to be decrypted at all.
    """
    user = get_current_user()
    if not user:
        return None, None, ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return None, None, ({"error": "Product connection not found"}, 404)

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], scope)
    if denied:
        return None, None, denied

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return None, None, ({"error": "Product connection not found"}, 404)

    if not conn_raw.get("is_active", True):
        # Same kill switch the proxy honours: a deactivated connection must
        # not have its credential decrypted, let alone used.
        return None, None, ({"error": "Product connection is deactivated"}, 403)

    mapping = await get_product_tenant_map(product_id, conn["tenant_id"])
    ctx = AdapterContext(
        connection_id=product_id,
        portal_tenant_id=conn["tenant_id"],
        external_id=(mapping or {}).get("external_id", ""),
        external_kind=(mapping or {}).get("external_kind", ""),
        base_url=conn_raw.get("base_url", ""),
        auth_type=conn_raw.get("auth_type", "bearer"),
        api_key=(
            decrypt_value(conn_raw.get("api_key", ""))
            if conn_raw.get("api_key")
            else ""
        ),
        api_secret=(
            decrypt_value(conn_raw.get("api_secret", ""))
            if conn_raw.get("api_secret")
            else ""
        ),
        correlation_id=request.headers.get("X-Correlation-ID", ""),
    )
    return ctx, str(conn_raw["product_type"]), None


def _failure(
    exc: AdapterError, product_id: int, operation: str
) -> tuple[dict[str, Any], int]:
    """Render an adapter error using the taxonomy's shared status mapping.

    The product's URL and headers never reach the response — only the
    adapter's own message, which the taxonomy exists to keep product-neutral.
    """
    logger.info(
        "operation_request_failed",
        extra={
            "product_id": product_id,
            "operation": operation,
            "error_type": type(exc).__name__,
        },
    )
    return {"error": str(exc)}, adapter_error_status(exc)


@operations_bp.route("/<int:product_id>/operations", methods=["GET"])
@auth_required
@tenancy_aware
async def list_operations(product_id: int) -> tuple[dict[str, Any], int]:
    """List a product's long-running operations, newest first."""
    ctx, product_type, error = await _resolve(product_id, SCOPE_PRODUCTS_READ)
    if error is not None or ctx is None or product_type is None:
        return error or ({"error": "Product connection not found"}, 404)

    args = request.args
    try:
        page = max(1, int(args.get("page", 1)))
        per_page = max(1, min(int(args.get("per_page", 20)), _MAX_PER_PAGE))
    except ValueError:
        return {"error": "page and per_page must be integers"}, 400

    state: OperationState | None = None
    raw_state = args.get("state")
    if raw_state:
        try:
            state = OperationState(raw_state)
        except ValueError:
            return {
                "error": f"unknown state {raw_state!r}",
                "allowed": [member.value for member in OperationState],
            }, 400

    adapter = get_adapter(product_type, ctx)
    try:
        result = await adapter.list_operations(
            ctx,
            kind=args.get("kind"),
            resource_id=args.get("resource_id"),
            state=state,
            page=page,
            per_page=per_page,
        )
    except AdapterError as exc:
        return _failure(exc, product_id, "list_operations")

    return {
        "operations": [asdict(OperationView.of(item)) for item in result.items],
        "page": result.page,
        "per_page": result.per_page,
        "total": result.total,
        "has_more": result.has_more,
    }, 200


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>", methods=["GET"]
)
@auth_required
@tenancy_aware
async def get_operation(
    product_id: int, kind: str, operation_id: str
) -> tuple[dict[str, Any], int]:
    """Poll one operation. This is the route the UI's refetch loop calls."""
    ctx, product_type, error = await _resolve(product_id, SCOPE_PRODUCTS_READ)
    if error is not None or ctx is None or product_type is None:
        return error or ({"error": "Product connection not found"}, 404)

    adapter = get_adapter(product_type, ctx)
    try:
        operation = await adapter.get_operation(kind, operation_id, ctx)
    except AdapterError as exc:
        return _failure(exc, product_id, "get_operation")

    return asdict(OperationView.of(operation)), 200


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>/cancel", methods=["POST"]
)
@auth_required
@tenancy_aware
async def cancel_operation(
    product_id: int, kind: str, operation_id: str
) -> tuple[dict[str, Any], int]:
    """Request cancellation and return the operation's resulting state.

    Requires ``products:manage``: cancelling a deploy mid-flight changes what
    the product does with real hardware, which is not a read.
    """
    ctx, product_type, error = await _resolve(product_id, SCOPE_PRODUCTS_MANAGE)
    if error is not None or ctx is None or product_type is None:
        return error or ({"error": "Product connection not found"}, 404)

    adapter = get_adapter(product_type, ctx)
    try:
        operation = await adapter.cancel_operation(kind, operation_id, ctx)
    except AdapterError as exc:
        return _failure(exc, product_id, "cancel_operation")

    return asdict(OperationView.of(operation)), 200


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>/logs", methods=["GET"]
)
@auth_required
@tenancy_aware
async def operation_logs(
    product_id: int, kind: str, operation_id: str
) -> tuple[dict[str, Any], int]:
    """Return an operation's log lines, oldest first.

    ``since`` lets the DetailDrawer's log tab fetch only what is new on each
    poll instead of re-reading the whole stream every interval.
    """
    ctx, product_type, error = await _resolve(product_id, SCOPE_PRODUCTS_READ)
    if error is not None or ctx is None or product_type is None:
        return error or ({"error": "Product connection not found"}, 404)

    args = request.args
    try:
        tail = max(1, min(int(args.get("tail", 100)), _MAX_TAIL))
    except ValueError:
        return {"error": "tail must be an integer"}, 400

    since: datetime | None = None
    raw_since = args.get("since")
    if raw_since:
        try:
            since = datetime.fromisoformat(raw_since)
        except ValueError:
            return {"error": "since must be an ISO-8601 timestamp"}, 400

    adapter = get_adapter(product_type, ctx)
    try:
        lines = await adapter.operation_logs(
            kind, operation_id, ctx, since=since, tail=tail
        )
    except AdapterError as exc:
        return _failure(exc, product_id, "operation_logs")

    return {
        "logs": [
            {
                "message": line.message,
                "level": line.level,
                "timestamp": _iso(line.timestamp),
            }
            for line in lines
        ],
        "operation_id": operation_id,
        "kind": kind,
    }, 200
