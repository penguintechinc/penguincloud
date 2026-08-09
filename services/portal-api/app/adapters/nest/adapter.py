"""Nest adapter — contract v2 against the live nest-api service.

Scope of this adapter, and why it is narrower than "Nest"
========================================================
"Nest" is several services, not one, and they do not share an origin. The
portal addresses a connection by a single ``base_url`` and the transport
pins every outbound call to that origin, so this adapter covers exactly the
surface reachable there — which the deployed routing makes precise.

``~/code/nest/k8s/kustomize/base/httproute.yaml`` sends **all** of ``/api``
to ``nest-api:8080`` and everything else to ``nest-gateway:8082``. So at the
Nest origin:

* ``nest-api`` (``apps/api``, Quart) — data-resources, snapshots,
  protection-policies, search-pools, operations, catalog, cost-report,
  anomalies. **This is what the adapter implements.**
* ``nest-manager`` (``apps/manager``) — servers, cloud providers, scaling
  policies. Not routed under ``/api`` at all, so unreachable from a Nest
  connection. Its routes are named in ``NEST_UNEXPOSED_ROUTES``.
* ``saga-engine`` (workflows) and ``nest-gateway``'s own ``/api/v1`` handlers
  — also unreachable, the first because nothing routes to it, the second
  because ``/api`` is claimed by ``nest-api`` before the gateway sees it.

Operations
==========
Every write in Nest is long-running. Creates answer ``202`` with an
``operationId``; snapshot / restore / introspect / migrate do the same. All
of them are polled at ONE route, ``/tenants/{tid}/operations/{op_id}``, so
:data:`~.mapping.OP_KIND` is a single value rather than a family per action.

Nest publishes no cancel route and no operation log stream on this service,
and its list-operations route lives on ``nest-manager`` (unreachable, see
above). Those three methods therefore raise
:class:`~app.adapters.base.AdapterCapabilityError` (501) rather than
returning an empty result that would read as "no operations".
"""

from __future__ import annotations

from typing import Any, Final

from ..base import (
    ActionResult,
    AdapterCapabilityError,
    AdapterContext,
    HealthOnlyAdapter,
    Operation,
    OperationState,
    Page,
    Resource,
    RouteRule,
    UpstreamError,
)
from ..transport import Transport, get_transport
from .mapping import (
    KIND_DATABASE,
    KIND_PROTECTION_POLICY,
    KIND_SEARCH_POOL,
    KIND_SNAPSHOT,
    OP_KIND,
    OPERATION_KINDS,
    RESOURCE_KINDS,
    to_operation,
    to_resource,
)
from .responses import NestResponse, unwrap
from .routes import (
    COLLECTION_DATA_RESOURCES,
    COLLECTION_OPERATIONS,
    COLLECTION_PROTECTION_POLICIES,
    COLLECTION_SEARCH_POOLS,
    COLLECTION_SNAPSHOTS,
    HEALTH_ENDPOINT,
    NEST_ROUTE_ALLOWLIST,
    NEST_UNEXPOSED_ROUTES,
    PRODUCT_TYPE,
    tenant_path,
)

__all__ = ["NestAdapter"]

#: Portal kind → Nest collection segment.
_COLLECTIONS: Final[dict[str, str]] = {
    KIND_DATABASE: COLLECTION_DATA_RESOURCES,
    KIND_SNAPSHOT: COLLECTION_SNAPSHOTS,
    KIND_PROTECTION_POLICY: COLLECTION_PROTECTION_POLICIES,
    KIND_SEARCH_POOL: COLLECTION_SEARCH_POOLS,
}

#: Kinds Nest serves a single-resource GET for. Snapshots and protection
#: policies register only ``GET`` on the collection and ``DELETE`` on the
#: item (``apps/api/app.py:337-372``) — there is no detail route, so
#: ``get_resource`` for those kinds is a 501 rather than a request that
#: would 404 and read as "this snapshot does not exist".
_DETAIL_KINDS: Final[frozenset[str]] = frozenset({KIND_DATABASE, KIND_SEARCH_POOL})

#: Actions Nest exposes on a data-resource, each a literal sub-path. The
#: action is matched against this set and never interpolated from caller
#: input — see the boundary note in :mod:`app.adapters.base`.
_ACTIONS: Final[frozenset[str]] = frozenset(
    {"snapshot", "restore", "introspect", "migrate"}
)

#: Nest's key for the operation id it returns from every 202.
_OPERATION_ID_KEY: Final[str] = "operationId"


class NestAdapter(HealthOnlyAdapter):
    """Nest data/storage adapter over the nest-api REST surface."""

    PRODUCT_TYPE: str = PRODUCT_TYPE
    DISPLAY_NAME: str = "Nest"

    #: Nest registers ``/health`` and ``/ready``; it registers ``/healthz``
    #: nowhere, so the contract's default would probe a 404 and report every
    #: healthy Nest as unhealthy.
    HEALTH_ENDPOINT: str = HEALTH_ENDPOINT

    route_allowlist: list[RouteRule] = NEST_ROUTE_ALLOWLIST
    unexposed_routes: tuple[tuple[str, str], ...] = NEST_UNEXPOSED_ROUTES

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """Report what this adapter can actually do against nest-api."""
        return [
            "health",
            "list_resources",
            "get_resource",
            "create_resource",
            "delete_resource",
            "perform_action",
            "get_operation",
        ]

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    async def _transport() -> Transport:
        """Fetch the shared transport."""
        return await get_transport()

    async def _call(
        self,
        method: str,
        path: str,
        ctx: AdapterContext,
        context: str,
        **kwargs: Any,
    ) -> NestResponse:
        """Make one authenticated Nest call and decode it.

        ``path`` is always built from module literals plus ``ctx.external_id``
        — never caller input. Nest authenticates with the stored bearer
        token directly (no login exchange), so unlike Gough there is no
        token-refresh retry to perform: a 401 here means the stored
        credential is wrong or its ``tenant`` claim does not match the mapped
        tenant, and retrying it would only repeat the failure.
        """
        transport = await self._transport()
        url = f"{ctx.base_url.rstrip('/')}{path}"
        response = await transport.request(method, url, ctx, **kwargs)
        return unwrap(response, context)

    @staticmethod
    def _require_kind(kind: str) -> str:
        """Resolve a portal kind to its Nest collection, or raise 501."""
        collection = _COLLECTIONS.get(kind)
        if collection is None:
            raise AdapterCapabilityError(
                f"nest does not serve resource kind {kind!r} "
                f"(supported: {sorted(RESOURCE_KINDS)})"
            )
        return collection

    def _collection_path(self, kind: str, ctx: AdapterContext) -> str:
        """Path of a kind's collection for this connection's tenant."""
        return tenant_path(ctx.external_id, self._require_kind(kind))

    def _item_path(self, kind: str, name: str, ctx: AdapterContext) -> str:
        """Path of one named item for this connection's tenant."""
        return tenant_path(ctx.external_id, self._require_kind(kind), name)

    # -- resources --------------------------------------------------------

    async def list_resources(
        self,
        kind: str,
        ctx: AdapterContext,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        cursor: str | None = None,
    ) -> Page[Resource]:
        """List one kind of Nest resource.

        Nest paginates by ``limit``/``offset`` (``handlers/dataresource.py``)
        and never returns a total, so ``Page.total`` stays ``None`` rather
        than being fabricated from the page's own length — which would render
        as fact and be wrong for every page but the last.

        ``has_more`` is derived by asking for one row more than requested and
        reporting whether it arrived. That is the only honest answer
        available from an endpoint with no count, and it costs nothing.
        """
        path = self._collection_path(kind, ctx)
        offset = max(page - 1, 0) * per_page
        params: dict[str, Any] = {"limit": per_page + 1, "offset": offset}
        if filters:
            params.update(
                {key: value for key, value in filters.items() if value is not None}
            )

        payload = await self._call("GET", path, ctx, f"list {kind}", params=params)
        items = payload.items()
        has_more = len(items) > per_page
        rows = [to_resource(kind, item) for item in items[:per_page]]

        return Page(
            items=rows,
            page=page,
            per_page=per_page,
            total=None,
            has_more=has_more,
        )

    async def get_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> Resource:
        """Fetch one Nest resource by name."""
        if kind not in _DETAIL_KINDS:
            self._require_kind(kind)
            raise AdapterCapabilityError(
                f"nest exposes no single-resource route for {kind!r}; it is "
                f"readable only through list_resources"
            )
        path = self._item_path(kind, resource_id, ctx)
        payload = await self._call("GET", path, ctx, f"get {kind} {resource_id}")
        return to_resource(kind, payload.dict_data())

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Create a Nest resource.

        Nest answers ``202`` with the new resource's fields AND an
        ``operationId`` — provisioning continues after the response. The
        contract's ``create_resource`` returns a ``Resource``, so the poll
        handle is carried in ``metadata['operationId']`` alongside the route
        that polls it; a caller that ignores it still gets a correct row,
        and one that does not can watch the provisioning finish instead of
        reporting a resource as ready the moment creation was accepted.
        """
        path = self._collection_path(kind, ctx)
        response = await self._call("POST", path, ctx, f"create {kind}", json=payload)
        data = response.dict_data()
        resource = to_resource(kind, data)

        operation_id = data.get(_OPERATION_ID_KEY) or response.headers.get(
            "x-operation-id"
        )
        if operation_id:
            resource.metadata[_OPERATION_ID_KEY] = str(operation_id)
            resource.metadata["operationPath"] = tenant_path(
                ctx.external_id, COLLECTION_OPERATIONS, str(operation_id)
            )
        return resource

    async def delete_resource(
        self, kind: str, resource_id: str, ctx: AdapterContext
    ) -> None:
        """Delete a Nest resource by name.

        Nest answers ``204``. A ``409`` becomes ``ResourceConflictError`` via
        the shared taxonomy, which is what lets a confirm dialog distinguish
        "still referenced" from "already gone".
        """
        path = self._item_path(kind, resource_id, ctx)
        await self._call("DELETE", path, ctx, f"delete {kind} {resource_id}")

    async def perform_action(
        self,
        kind: str,
        resource_id: str,
        action: str,
        payload: dict[str, Any] | None,
        ctx: AdapterContext,
    ) -> ActionResult:
        """Start a long-running action on a data-resource.

        Nest exposes ``snapshot``, ``restore``, ``introspect`` and
        ``migrate``, all on a data-resource and all answering ``202`` with an
        ``operationId``. The returned :class:`ActionResult` carries an
        :class:`Operation` in ``PENDING`` so the UI has a poll key
        immediately, without a second request to discover one.
        """
        if kind != KIND_DATABASE:
            self._require_kind(kind)
            raise AdapterCapabilityError(
                f"nest exposes no actions on {kind!r}; actions "
                f"{sorted(_ACTIONS)} are defined on {KIND_DATABASE!r} only"
            )
        if action not in _ACTIONS:
            raise AdapterCapabilityError(
                f"nest does not support action {action!r} "
                f"(supported: {sorted(_ACTIONS)})"
            )

        path = tenant_path(
            ctx.external_id, COLLECTION_DATA_RESOURCES, resource_id, action
        )
        response = await self._call(
            "POST",
            path,
            ctx,
            f"{action} {kind} {resource_id}",
            json=payload or {},
        )
        data = response.dict_data()

        operation_id = data.get(_OPERATION_ID_KEY) or response.headers.get(
            "x-operation-id"
        )
        operations: list[Operation] = []
        if operation_id:
            operations.append(
                Operation(
                    id=str(operation_id),
                    kind=OP_KIND,
                    state=OperationState.PENDING,
                    status=str(data.get("phase") or "Pending"),
                    resource_id=resource_id,
                    resource_kind=KIND_DATABASE,
                    detail=action,
                )
            )

        return ActionResult(
            action=action,
            accepted=response.status_code in (200, 201, 202),
            operations=operations,
            message=str(data.get("message")) if data.get("message") else None,
        )

    # -- operations -------------------------------------------------------

    @staticmethod
    def _require_operation_kind(kind: str) -> None:
        """Reject an operation family Nest does not have."""
        if kind not in OPERATION_KINDS:
            raise AdapterCapabilityError(
                f"nest has no operation kind {kind!r} "
                f"(supported: {sorted(OPERATION_KINDS)})"
            )

    async def get_operation(
        self, kind: str, operation_id: str, ctx: AdapterContext
    ) -> Operation:
        """Poll one Nest operation.

        A ``SUCCEEDED`` operation carries Nest's own ``result`` object —
        the snapshot produced, the restore target, the migration report —
        through :attr:`Operation.result`.
        """
        self._require_operation_kind(kind)
        path = tenant_path(ctx.external_id, COLLECTION_OPERATIONS, operation_id)
        payload = await self._call("GET", path, ctx, f"get operation {operation_id}")
        data = payload.dict_data()
        operation = to_operation(data)
        if not operation.id:
            raise UpstreamError("nest returned an operation with no id")
        return operation

    async def list_operations(
        self,
        ctx: AdapterContext,
        kind: str | None = None,
        resource_id: str | None = None,
        state: OperationState | None = None,
        page: int = 1,
        per_page: int = 20,
        cursor: str | None = None,
    ) -> Page[Operation]:
        """Unsupported: nest-api serves no operation collection.

        The route exists (``GET /api/v1/tenants/<tid>/operations``) but it is
        registered by ``nest-manager``, which the deployed HTTPRoute never
        routes ``/api`` to. Returning an empty page would misreport a
        reachability gap as "no operations are running".
        """
        raise AdapterCapabilityError(
            "nest exposes no operation collection at the api service; "
            "operations are polled individually by id via get_operation"
        )

    async def cancel_operation(
        self, kind: str, operation_id: str, ctx: AdapterContext
    ) -> Operation:
        """Unsupported: Nest's cancel route is internal-only.

        ``POST /internal/v1/operations/<op_id>/cancel`` is mounted by
        nest-manager on its internal control plane and is deliberately named
        in ``NEST_UNEXPOSED_ROUTES``.
        """
        raise AdapterCapabilityError(
            "nest exposes no tenant-facing cancel route; its cancel endpoint "
            "is an internal control-plane route the portal must not call"
        )

    async def operation_logs(
        self,
        kind: str,
        operation_id: str,
        ctx: AdapterContext,
        since: Any = None,
        tail: int = 100,
    ) -> list[Any]:
        """Unsupported: Nest publishes no per-operation log stream."""
        raise AdapterCapabilityError(
            "nest publishes no operation log stream; an operation's outcome "
            "is reported by its phase, error and result fields"
        )
