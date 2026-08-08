"""Long-running operation APIs — the endpoints the UI polls.

Companion to the :class:`~app.adapters.base.Operation` contract added in
Phase 4G. A product action that returns ``202`` is only half an integration;
without a poll route the browser has no way to learn that a deploy finished,
and the portal would have to either block a request until the product was
done or lie about the outcome.

Routes (all under ``/api/v1/products/<product_id>``):

========================================================  =================
``GET    /operations``                                    list, newest first
``GET    /operations/<kind>/<operation_id>``              poll one
``POST   /operations/<kind>/<operation_id>/cancel``       request cancellation
``GET    /operations/<kind>/<operation_id>/logs``         log lines
``POST   /resources/<kind>/<id>/actions/<action>``        start one
========================================================  =================

The last route is the typed action path. An action that starts background work
must NOT be proxied: the proxy forwards the product's response verbatim, so the
browser receives a product-specific ``202`` body with no ``ActionResult`` and no
poll key, and can only invalidate its queries and hope. Routing it through
:meth:`Adapter.perform_action` is what makes :attr:`ActionResult.operations`
reachable, so the UI learns the ids of the deployments it just started. See
"Which mutations go through which path" in :mod:`app.adapters.base`.

``kind`` is in the path rather than a query parameter because it is part of
the operation's identity, not a filter: :attr:`Operation.kind` selects which
of a product's poll routes answers, so ``kind`` + ``id`` together are the
key. That also makes the URL reconstructible from an ``Operation`` alone,
which is what lets the UI poll an object it was handed without tracking
where it came from.

Security
========
Every route resolves the connection, checks tenant membership, enforces a
scope, then decrypts the credential — in that order, matching the ordering
established for the proxy in Phase 3 (A1).

Scopes are **per-product**: ``products:{product_type}:read`` for the polls and
the log tail, ``products:{product_type}:manage`` for cancel. Deriving the
scope from the connection's own product type is what makes these routes part
of the same authorisation model as the proxy allowlist. Gating them on the
coarse ``products:read`` / ``products:manage`` instead — as this module did
originally — meant the model's motivating principal, an operator granted
``products:gough:manage`` and nothing else, was refused the ability to poll or
cancel the very deploy they had just been authorised to start. The coarse
scopes still work: :class:`~app.adapters.base.RBACEnforcer` treats them as
satisfying the per-product form.

A non-member gets **404, not 403** — see the oracle note in :func:`_resolve`.

Nothing here accepts a caller-supplied path: ``kind`` is validated by the
adapter against a literal set, and ``operation_id`` is validated before it can
reach a URL segment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from quart import Blueprint, request
from quart_schema import validate_response

from .adapters import get_adapter
from .adapters.base import (
    ActionResult,
    AdapterContext,
    AdapterError,
    Operation,
    OperationState,
    Resource,
    adapter_error_status,
    product_scope,
)
from .authz import require_tenant_scope
from .encryption import decrypt_value
from .middleware import auth_required, get_current_user
from .models import (
    get_product_connection_by_id,
    get_product_connection_raw,
    get_product_tenant_map,
)
from .tenancy import tenancy_aware
from .tenancy.authz import resolve_effective_role

logger = logging.getLogger(__name__)

operations_bp = Blueprint("operations", __name__)

#: Upper bound on a page of operations. A poll loop that asks for thousands
#: of rows every few seconds is a self-inflicted load problem.
_MAX_PER_PAGE = 100

#: Upper bound on log lines per request, matching Gough's own cap.
_MAX_TAIL = 1000

#: The single "you get nothing" answer. Shared so that "no such connection"
#: and "not your tenant" are byte-identical — see the oracle note in
#: :func:`_resolve`.
_NOT_FOUND: Final[tuple[dict[str, Any], int]] = (
    {"error": "Product connection not found"},
    404,
)

#: Scope actions these routes require. Reads poll and tail logs; cancel
#: changes what the product is doing to real hardware, so it is a mutation.
_ACTION_READ: Final[str] = "read"
_ACTION_MANAGE: Final[str] = "manage"


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
    #: What a succeeded operation produced. See :attr:`Operation.result`.
    result: dict[str, Any] | None
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

        ``metadata`` is deliberately NOT published. It is the adapter's
        free-form bag, with no declared schema, so publishing it would make
        every key an adapter happens to stash there part of the portal's wire
        contract by accident — the output-validation failure this DTO exists
        to prevent. An adapter with something the UI must render puts it in
        ``result`` (or asks for a typed field), which is exactly why
        ``result`` had to exist.
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
            result=operation.result,
            created_at=_iso(operation.created_at),
            updated_at=_iso(operation.updated_at),
            completed_at=_iso(operation.completed_at),
        )


@dataclass(slots=True, frozen=True)
class OperationListResponse:
    """Envelope for a page of operations."""

    operations: list[OperationView]
    page: int
    per_page: int
    #: Absent for cursor paginators — see :class:`~app.adapters.base.Page`.
    total: int | None
    has_more: bool


@dataclass(slots=True, frozen=True)
class OperationLogLineView:
    """Wire shape for one log line."""

    message: str
    level: str
    timestamp: str | None


@dataclass(slots=True, frozen=True)
class OperationLogsResponse:
    """Envelope for an operation's log lines, oldest first."""

    logs: list[OperationLogLineView]
    operation_id: str
    kind: str


@dataclass(slots=True, frozen=True)
class ActionResourceView:
    """The affected resource's post-action state, when the product returned it.

    A named subset rather than the whole :class:`~app.adapters.base.Resource`:
    ``metadata`` is the adapter's free-form bag and is not published here for
    the same reason :class:`OperationView` omits it.
    """

    id: str
    kind: str
    name: str
    status: str | None

    @classmethod
    def of(cls, resource: Resource) -> ActionResourceView:
        """Project an adapter Resource onto the wire shape."""
        return cls(
            id=resource.id,
            kind=resource.kind,
            name=resource.name,
            status=resource.status,
        )


@dataclass(slots=True, frozen=True)
class ActionResultResponse:
    """Outcome of a product action, including anything left to poll.

    ``operations`` is the field this route exists for. It is a LIST because a
    single Gough node deploy returns one deployment per assigned biome, and a
    caller handed only the first would poll a fraction of the work it started.
    An empty list means the action completed synchronously — which is how the
    UI tells "nothing to poll" from "poll these".
    """

    action: str
    accepted: bool
    operations: list[OperationView]
    resource: ActionResourceView | None
    message: str | None

    @classmethod
    def of(cls, result: ActionResult) -> ActionResultResponse:
        """Project an adapter ActionResult onto the wire shape."""
        return cls(
            action=result.action,
            accepted=result.accepted,
            operations=[OperationView.of(item) for item in result.operations],
            resource=(
                ActionResourceView.of(result.resource)
                if result.resource is not None
                else None
            ),
            message=result.message,
        )


def _iso(value: datetime | None) -> str | None:
    """Render a timestamp for the wire, or None."""
    return value.isoformat() if value is not None else None


async def _resolve(
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
        return None, None, _NOT_FOUND

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
        return None, None, _NOT_FOUND

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
        return None, None, _NOT_FOUND

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
@validate_response(OperationListResponse)
async def list_operations(product_id: int) -> tuple[Any, int]:
    """List a product's long-running operations, newest first."""
    ctx, product_type, error = await _resolve(product_id, _ACTION_READ)
    if error is not None or ctx is None or product_type is None:
        return error or _NOT_FOUND

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

    return (
        OperationListResponse(
            operations=[OperationView.of(item) for item in result.items],
            page=result.page,
            per_page=result.per_page,
            total=result.total,
            has_more=result.has_more,
        ),
        200,
    )


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>", methods=["GET"]
)
@auth_required
@tenancy_aware
@validate_response(OperationView)
async def get_operation(
    product_id: int, kind: str, operation_id: str
) -> tuple[Any, int]:
    """Poll one operation. This is the route the UI's refetch loop calls."""
    ctx, product_type, error = await _resolve(product_id, _ACTION_READ)
    if error is not None or ctx is None or product_type is None:
        return error or _NOT_FOUND

    adapter = get_adapter(product_type, ctx)
    try:
        operation = await adapter.get_operation(kind, operation_id, ctx)
    except AdapterError as exc:
        return _failure(exc, product_id, "get_operation")

    return OperationView.of(operation), 200


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>/cancel", methods=["POST"]
)
@auth_required
@tenancy_aware
@validate_response(OperationView)
async def cancel_operation(
    product_id: int, kind: str, operation_id: str
) -> tuple[Any, int]:
    """Request cancellation and return the operation's resulting state.

    Requires ``products:manage``: cancelling a deploy mid-flight changes what
    the product does with real hardware, which is not a read.
    """
    ctx, product_type, error = await _resolve(product_id, _ACTION_MANAGE)
    if error is not None or ctx is None or product_type is None:
        return error or _NOT_FOUND

    adapter = get_adapter(product_type, ctx)
    try:
        operation = await adapter.cancel_operation(kind, operation_id, ctx)
    except AdapterError as exc:
        return _failure(exc, product_id, "cancel_operation")

    return OperationView.of(operation), 200


@operations_bp.route(
    "/<int:product_id>/operations/<kind>/<operation_id>/logs", methods=["GET"]
)
@auth_required
@tenancy_aware
@validate_response(OperationLogsResponse)
async def operation_logs(
    product_id: int, kind: str, operation_id: str
) -> tuple[Any, int]:
    """Return an operation's log lines, oldest first.

    ``since`` lets the DetailDrawer's log tab fetch only what is new on each
    poll instead of re-reading the whole stream every interval.
    """
    ctx, product_type, error = await _resolve(product_id, _ACTION_READ)
    if error is not None or ctx is None or product_type is None:
        return error or _NOT_FOUND

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

    return (
        OperationLogsResponse(
            logs=[
                OperationLogLineView(
                    message=line.message,
                    level=line.level,
                    timestamp=_iso(line.timestamp),
                )
                for line in lines
            ],
            operation_id=operation_id,
            kind=kind,
        ),
        200,
    )


@operations_bp.route(
    "/<int:product_id>/resources/<kind>/<resource_id>/actions/<action>",
    methods=["POST"],
)
@auth_required
@tenancy_aware
@validate_response(ActionResultResponse)
async def perform_resource_action(
    product_id: int, kind: str, resource_id: str, action: str
) -> tuple[Any, int]:
    """Invoke a product action and return the operations it started.

    This is the TYPED path for actions, and it exists because the proxy
    cannot serve this case. Proxying ``POST /nodes/{id}/deploy`` forwards
    Gough's raw ``202`` body to the browser, which leaves the UI holding a
    product-specific payload with no :class:`ActionResult`, no normalised
    state, and no poll key — so it can only invalidate its queries and hope
    the deploy it just started eventually shows up somewhere.

    Going through :meth:`Adapter.perform_action` instead means the response
    carries the deployment ids as :class:`OperationView` objects, each already
    addressable at ``/operations/{kind}/{id}``. The UI learns exactly what it
    started. See "Which mutations go through which path" in
    :mod:`app.adapters.base`.

    Requires ``manage``: every action reaching here changes product state.
    ``kind`` and ``action`` are validated by the adapter against literal
    tables before any URL is built — neither is interpolated into a path here.
    """
    ctx, product_type, error = await _resolve(product_id, _ACTION_MANAGE)
    if error is not None or ctx is None or product_type is None:
        return error or _NOT_FOUND

    payload: dict[str, Any] = {}
    if await request.get_data():
        body = await request.get_json(silent=True)
        if body is not None and not isinstance(body, dict):
            return {"error": "request body must be a JSON object"}, 400
        payload = body or {}

    adapter = get_adapter(product_type, ctx)
    try:
        outcome = await adapter.perform_action(kind, resource_id, action, payload, ctx)
    except AdapterError as exc:
        return _failure(exc, product_id, f"perform_action:{action}")

    return ActionResultResponse.of(outcome), 200
