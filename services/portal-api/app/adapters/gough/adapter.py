"""Gough adapter — contract v2 against the live api-manager surface.

Built by reading ``~/code/gough/services/api-manager/app/api/*.py``, not the
committed ``docs/api/openapi-spec.yaml``. The spec is stale in ways that
matter: it documents ``/servers``, ``/servers/{id}/power/{action}``,
``/jobs`` and ``/stats``, none of which the service registers. What exists is
``/api/v1/nodes``, ``/api/v1/biomes`` (with ``groups`` and ``deployments``
beneath it), ``/api/v1/agents`` and a set of per-cluster sub-resources.

Deliberate capability gaps, each a 501 rather than an empty list:

* ``clusters`` cannot be listed. Gough registers no ``GET /api/v1/clusters``
  — the blueprint only serves ``/{cluster_id}/...`` sub-resources, so a
  cluster id is something the caller already knows. A single cluster is
  readable via its LXD status document.
* ``list_users`` / ``invite_user`` are not wired. Gough has
  ``/api/v1/users``, but the portal has its own identity model and a
  half-mapped user surface is worse than a declared absence.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final

import httpx

from ..base import (
    ActionResult,
    AdapterCapabilityError,
    AdapterContext,
    HealthOnlyAdapter,
    MetricsSummary,
    Operation,
    OperationLogLine,
    OperationState,
    Page,
    Resource,
    ResourceNotFoundError,
    RouteRule,
    TimeRange,
    UpstreamError,
)
from ..transport import Transport, get_transport
from . import mapping
from .mapping import OP_BIOME_UPGRADE, OP_DEPLOYMENT, OPERATION_KINDS
from .responses import GoughResponse, raise_for_status, unwrap
from .routes import GOUGH_ROUTE_ALLOWLIST, GOUGH_UNEXPOSED_ROUTES
from .session import GoughSession

__all__ = ["GoughAdapter"]

#: Gough's cursor-paginated collections cap ``page_size`` at 500.
_MAX_PAGE_SIZE: Final[int] = 500

#: Resource kinds this adapter serves, and the collection path for each.
#: Membership is checked before any request is built, so ``kind`` is a
#: selector rather than a path fragment — nothing caller-supplied is ever
#: interpolated into a URL.
_COLLECTIONS: Final[dict[str, str]] = {
    "nodes": "/api/v1/nodes",
    "biomes": "/api/v1/biomes",
    "biome_groups": "/api/v1/biomes/groups",
    "agents": "/api/v1/agents",
}

#: The EXACT path Gough registers for each COLLECTION endpoint, trailing
#: slash included or omitted to match the product's own route table.
#:
#: This cannot be derived by appending ``/`` to :data:`_COLLECTIONS`, and the
#: attempt was a live defect. Gough registers ``nodes_bp.route("/")``,
#: ``biomes_bp.route("/")`` and ``agents_bp.route("/")`` — trailing slash — but
#: ``biomes_bp.route("/groups")`` WITHOUT one, and never sets
#: ``strict_slashes``. Werkzeug's default is asymmetric: a request missing a
#: registered trailing slash gets a 308 redirect, while a request carrying one
#: the route does not declare gets a flat 404 with no redirect back. So
#: ``/api/v1/biomes/groups/`` did not "nearly work" — it 404'd outright.
#:
#: Only the collection route varies this way; item paths are built as
#: ``f"{_COLLECTIONS[kind]}/{id}"`` and are unaffected.
_COLLECTION_ROUTES: Final[dict[str, str]] = {
    "nodes": "/api/v1/nodes/",
    "biomes": "/api/v1/biomes/",
    "biome_groups": "/api/v1/biomes/groups",
    "agents": "/api/v1/agents/",
}


#: Which key inside Gough's response envelope holds the array, per kind.
_ITEM_KEYS: Final[dict[str, str]] = {
    "nodes": "nodes",
    "biomes": "biomes",
    "biome_groups": "groups",
    "agents": "agents",
}

_MAPPERS: Final[dict[str, Callable[[dict[str, Any]], Resource]]] = {
    "nodes": mapping.map_node,
    "biomes": mapping.map_biome,
    "biome_groups": mapping.map_biome_group,
    "agents": mapping.map_agent,
}

#: Every table keyed by resource kind. They MUST agree.
#:
#: ``_require_kind`` validates a caller's kind against ``_COLLECTIONS`` only,
#: and the call sites then index ``_COLLECTION_ROUTES``, ``_ITEM_KEYS`` and
#: ``_MAPPERS`` unguarded. A kind present in one table and missing from
#: another therefore passes validation and raises ``KeyError`` — surfacing as
#: a 500, where the contract promises ``AdapterCapabilityError`` (501, a
#: *declared* absence the caller can act on).
#:
#: Checked at import, so a mistake here is an ImportError in CI rather than a
#: 500 on whichever resource kind nobody wrote a test for — the same choice
#: :class:`~app.adapters.base.RouteRule` makes about anchoring.
_KIND_TABLES: Final[dict[str, dict[str, Any]]] = {
    "_COLLECTIONS": _COLLECTIONS,
    "_COLLECTION_ROUTES": _COLLECTION_ROUTES,
    "_ITEM_KEYS": _ITEM_KEYS,
    "_MAPPERS": _MAPPERS,
}

_KINDS: Final[frozenset[str]] = frozenset(_COLLECTIONS)
for _table_name, _table in _KIND_TABLES.items():
    if frozenset(_table) != _KINDS:
        raise RuntimeError(
            f"gough adapter: {_table_name} does not cover the same resource "
            f"kinds as _COLLECTIONS; symmetric difference = "
            f"{sorted(frozenset(_table) ^ _KINDS)}. A kind missing from one "
            f"table passes _require_kind and then raises KeyError (500) "
            f"instead of AdapterCapabilityError (501)."
        )

#: Non-CRUD verbs, per kind. A literal table rather than string formatting:
#: ``action`` arrives from the caller, and a table lookup cannot become a
#: path injection the way an f-string can.
_ACTIONS: Final[dict[str, dict[str, str]]] = {
    "nodes": {
        "deploy": "deploy",
        "evacuate": "evacuate",
        "reject": "reject",
    },
    "biomes": {"upgrade": "upgrade"},
    "agents": {"suspend": "suspend", "resume": "resume"},
}

#: Gough demands an idempotency key on node deploys and rejects the request
#: without one.
_IDEMPOTENCY_HEADER: Final[str] = "X-Idempotency-Key"


class GoughAdapter(HealthOnlyAdapter):
    """Gough hypervisor adapter."""

    PRODUCT_TYPE: str = "gough"
    DISPLAY_NAME: str = "Gough"
    HEALTH_ENDPOINT: str = "/healthz"

    route_allowlist: list[RouteRule] = GOUGH_ROUTE_ALLOWLIST

    #: Real Gough routes this adapter must never admit. See routes.py.
    unexposed_routes: tuple[tuple[str, str], ...] = GOUGH_UNEXPOSED_ROUTES

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """Report the operations this adapter actually implements."""
        return [
            "health",
            "list_resources",
            "get_resource",
            "create_resource",
            "update_resource",
            "delete_resource",
            "perform_action",
            "list_operations",
            "get_operation",
            "cancel_operation",
            "operation_logs",
            "metrics_summary",
        ]

    # -- plumbing ---------------------------------------------------------

    async def _call(
        self,
        method: str,
        path: str,
        ctx: AdapterContext,
        context: str,
        **kwargs: Any,
    ) -> GoughResponse:
        """Make one authenticated Gough call, refreshing the token on 401.

        The single retry is what makes a 30-minute token invisible to
        callers. It fires only on 401 and only once: a second 401 after a
        freshly minted token is not a stale-token problem, it is a bad
        service-account credential, and retrying past that would hammer the
        product's login endpoint on every request of a broken connection.

        ``path`` is always a module literal, never caller input — see the
        boundary note in :mod:`app.adapters.base`.
        """
        transport = await self._transport()
        session = GoughSession(transport)
        url = f"{ctx.base_url.rstrip('/')}{path}"

        authed = await session.authorize(ctx)
        response = await transport.request(method, url, authed, **kwargs)
        if response.status_code == 401:
            authed = await session.reauthorize(ctx)
            response = await transport.request(method, url, authed, **kwargs)
        return unwrap(response, context)

    @staticmethod
    async def _transport() -> Transport:
        """Fetch the shared transport."""
        return await get_transport()

    @staticmethod
    def _require_kind(kind: str) -> str:
        """Resolve a resource kind to its collection path, or raise 501."""
        path = _COLLECTIONS.get(kind)
        if path is None:
            raise AdapterCapabilityError(
                f"gough does not serve resource kind {kind!r} "
                f"(supported: {sorted(_COLLECTIONS)})"
            )
        return path

    @staticmethod
    def _items(payload: GoughResponse, kind: str) -> list[dict[str, Any]]:
        """Pull the array out of a Gough collection response."""
        data = payload.dict_data()
        raw = data.get(_ITEM_KEYS[kind])
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise UpstreamError(f"gough returned a non-list {kind} collection")
        return [item for item in raw if isinstance(item, dict)]

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
        """List a Gough collection.

        Clusters raise rather than return an empty page: Gough has no
        enumeration endpoint for them, and an empty list would read as "this
        deployment has no clusters" — the exact confusion the contract's
        capability/emptiness split exists to prevent.

        ``Page.total`` is left unset for every kind. Gough's ``total`` field
        is the length of the page it just serialised, not the collection
        size; forwarding it would render a per-page count as a fleet count.
        """
        if kind == "clusters":
            raise AdapterCapabilityError(
                "gough exposes no cluster collection endpoint; clusters are "
                "addressed individually by id via get_resource('clusters', id)"
            )
        self._require_kind(kind)

        params: dict[str, Any] = {}
        if kind in ("nodes", "biomes"):
            params["page_size"] = max(1, min(per_page, _MAX_PAGE_SIZE))
            if cursor:
                params["cursor"] = cursor
        params.update(self._safe_filters(kind, filters))

        payload = await self._call(
            "GET",
            _COLLECTION_ROUTES[kind],
            ctx,
            f"list {kind}",
            params=params or None,
        )
        mapper = _MAPPERS[kind]
        items = [mapper(item) for item in self._items(payload, kind)]
        next_cursor = payload.next_cursor
        return Page(
            items=items,
            page=page,
            per_page=per_page,
            cursor=cursor,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
        )

    @staticmethod
    def _safe_filters(kind: str, filters: dict[str, Any] | None) -> dict[str, Any]:
        """Keep only the query parameters Gough documents for this kind.

        An allowlist, not a passthrough. Forwarding arbitrary caller keys
        would let a portal user set ``tenant_id`` on ``GET /nodes`` — Gough
        honours that parameter for cross-tenant super-admins, so relaying it
        unfiltered would make the portal's tenant isolation depend on the
        privilege of the *service account* rather than the calling user.
        """
        allowed: Final[dict[str, frozenset[str]]] = {
            "nodes": frozenset({"state", "tag", "name_contains"}),
            "biomes": frozenset(
                {
                    "type",
                    "category",
                    "is_active",
                    "is_default",
                    "biome_kind",
                    "phase",
                    "workload_type",
                    "name_contains",
                    "signed_only",
                }
            ),
            "biome_groups": frozenset(),
            "agents": frozenset({"status"}),
        }
        permitted = allowed.get(kind, frozenset())
        if not filters:
            return {}
        return {
            key: value for key, value in filters.items() if key in permitted and value is not None
        }

    async def get_resource(self, kind: str, resource_id: str, ctx: AdapterContext) -> Resource:
        """Fetch one resource.

        Clusters are read from their LXD status document, the only per-cluster
        endpoint that returns a cluster-shaped object rather than a slice of
        its configuration.
        """
        if kind == "clusters":
            payload = await self._call(
                "GET",
                f"/api/v1/clusters/{self._segment(resource_id)}/lxd/status",
                ctx,
                f"get cluster {resource_id}",
            )
            return mapping.map_cluster(resource_id, payload.dict_data())

        path = self._require_kind(kind)
        payload = await self._call(
            "GET",
            f"{path}/{self._segment(resource_id)}",
            ctx,
            f"get {kind} {resource_id}",
        )
        return _MAPPERS[kind](self._unwrap_single(payload, kind))

    @staticmethod
    def _unwrap_single(payload: GoughResponse, kind: str) -> dict[str, Any]:
        """Return the object body, unwrapping Gough's per-kind nesting.

        The agent detail route answers ``{"agent": {...}}`` while node and
        biome detail routes answer the object directly. Checking for the
        wrapper by name is safe because a Gough resource never has a field
        named after its own singular kind.
        """
        data = payload.dict_data()
        singular = {"agents": "agent", "biomes": "biome", "nodes": "node"}.get(kind)
        if singular and isinstance(data.get(singular), dict):
            return dict(data[singular])
        return data

    @staticmethod
    def _segment(value: str) -> str:
        """Validate an id destined for a URL path segment.

        Ids reach this adapter from a portal route parameter. They are the one
        caller-influenced value that legitimately becomes part of a URL, so
        they are constrained to characters that cannot restructure it: a
        slash, a dot-segment, a query or fragment marker, or whitespace would
        each change which endpoint is called.

        The transport's origin pin would still contain the damage, but a
        rejected id is a clearer failure than a mysterious 404, and this keeps
        the trusted-path claim honest rather than leaning on the backstop.
        """
        text = str(value)
        if not text or len(text) > 128:
            raise ResourceNotFoundError(f"invalid resource id {value!r}")
        if not all(char.isalnum() or char in "-_" for char in text):
            raise ResourceNotFoundError(f"invalid resource id {value!r}")
        return text

    async def create_resource(
        self, kind: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Create a biome or a biome group.

        Nodes and agents are not creatable through the portal by design:
        Gough discovers nodes from hardware and enrols agents through a
        key-exchange handshake, so a portal "create" would be a fiction.
        """
        if kind not in ("biomes", "biome_groups"):
            raise AdapterCapabilityError(
                f"gough does not support creating {kind!r}; nodes are discovered "
                f"and agents are enrolled by the product itself"
            )
        self._require_kind(kind)
        response = await self._call(
            "POST", _COLLECTION_ROUTES[kind], ctx, f"create {kind}", json=payload
        )
        return _MAPPERS[kind](self._unwrap_single(response, kind))

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: AdapterContext
    ) -> Resource:
        """Update a resource, using whichever verb Gough declares for it.

        Nodes take PATCH; biomes and groups take PUT. Sending the wrong one
        yields a 405 the portal cannot explain, so the verb is looked up
        rather than assumed uniform.
        """
        methods: Final[dict[str, str]] = {
            "nodes": "PATCH",
            "biomes": "PUT",
            "biome_groups": "PUT",
        }
        method = methods.get(kind)
        if method is None:
            raise AdapterCapabilityError(f"gough does not support updating {kind!r}")
        path = self._require_kind(kind)
        response = await self._call(
            method,
            f"{path}/{self._segment(resource_id)}",
            ctx,
            f"update {kind} {resource_id}",
            json=payload,
        )
        return _MAPPERS[kind](self._unwrap_single(response, kind))

    async def delete_resource(self, kind: str, resource_id: str, ctx: AdapterContext) -> None:
        """Delete a node, biome or biome group."""
        if kind not in ("nodes", "biomes", "biome_groups"):
            raise AdapterCapabilityError(f"gough does not support deleting {kind!r}")
        path = self._require_kind(kind)
        await self._call(
            "DELETE",
            f"{path}/{self._segment(resource_id)}",
            ctx,
            f"delete {kind} {resource_id}",
        )

    # -- actions ----------------------------------------------------------

    async def perform_action(
        self,
        kind: str,
        resource_id: str,
        action: str,
        payload: dict[str, Any] | None,
        ctx: AdapterContext,
    ) -> ActionResult:
        """Invoke a non-CRUD verb and report any operations it started."""
        verbs = _ACTIONS.get(kind, {})
        suffix = verbs.get(action)
        if suffix is None:
            raise AdapterCapabilityError(
                f"gough has no action {action!r} for {kind!r} " f"(supported: {sorted(verbs)})"
            )
        path = self._require_kind(kind)
        url_path = f"{path}/{self._segment(resource_id)}/{suffix}"

        # An empty dict, never None: the transport merges the caller's headers
        # with the injected credential via ``.update()``, so a None here is an
        # AttributeError three frames down rather than "no extra headers".
        headers: dict[str, str] = {}
        if kind == "nodes" and action == "deploy":
            headers[_IDEMPOTENCY_HEADER] = self._idempotency_key(resource_id, action)

        response = await self._call(
            "POST",
            url_path,
            ctx,
            f"{action} {kind} {resource_id}",
            json=payload or {},
            headers=headers,
        )
        return self._action_result(kind, resource_id, action, response)

    @staticmethod
    def _idempotency_key(resource_id: str, action: str) -> str:
        """Build the key Gough requires on a node deploy.

        Derived from the target and a UTC timestamp rather than a random
        value: two identical deploys issued in the same second are far more
        likely to be a double-submitted form than a deliberate repeat, and
        Gough collapsing them is the desired outcome.
        """
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"portal-{action}-{resource_id}-{stamp}"

    @staticmethod
    def _action_result(
        kind: str, resource_id: str, action: str, response: GoughResponse
    ) -> ActionResult:
        """Turn Gough's action response into operations the caller can poll.

        A node deploy answers ``202`` with ``assignment_ids`` — one deployment
        per assigned biome — so this returns one Operation each. A biome
        upgrade answers with a single ``upgrade_run_id``. Actions that finish
        synchronously (agent suspend/resume) return no operations at all,
        which is how the caller knows there is nothing to poll.
        """
        data = response.dict_data()
        operations: list[Operation] = []

        raw_ids = data.get("assignment_ids")
        if isinstance(raw_ids, list):
            operations.extend(
                Operation(
                    id=str(assignment_id),
                    kind=OP_DEPLOYMENT,
                    state=OperationState.PENDING,
                    status="pending",
                    resource_id=resource_id,
                    resource_kind=kind,
                    metadata={"node_id": data.get("node_id")},
                )
                for assignment_id in raw_ids
                if assignment_id is not None
            )

        run_id = data.get("upgrade_run_id") or data.get("run_id")
        if run_id:
            operations.append(
                Operation(
                    id=str(run_id),
                    kind=OP_BIOME_UPGRADE,
                    state=OperationState.PENDING,
                    status=str(data.get("status") or "pending"),
                    resource_id=resource_id,
                    resource_kind=kind,
                    metadata={"biome_id": resource_id},
                )
            )

        message = data.get("note") or data.get("message")
        return ActionResult(
            action=action,
            accepted=True,
            operations=operations,
            message=str(message) if message else None,
        )

    # -- operations -------------------------------------------------------

    @staticmethod
    def _require_operation_kind(kind: str) -> str:
        """Reject an unknown operation family before building a URL."""
        if kind not in OPERATION_KINDS:
            raise AdapterCapabilityError(
                f"gough has no operation kind {kind!r} " f"(supported: {sorted(OPERATION_KINDS)})"
            )
        return kind

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
        """List deployments, newest first.

        Only deployments are listable. Gough exposes an upgrade run through
        its own id and offers no collection route, so filtering to
        ``biome_upgrade`` is a declared gap rather than an empty result.
        """
        if kind is not None and kind != OP_DEPLOYMENT:
            self._require_operation_kind(kind)
            raise AdapterCapabilityError(
                "gough exposes no collection endpoint for upgrade runs; poll one "
                "by id with get_operation('biome_upgrade', run_id, ctx)"
            )

        params: dict[str, Any] = {
            "limit": max(1, min(per_page, 100)),
            "offset": max(0, (page - 1) * per_page),
        }
        if resource_id:
            params["node_id"] = resource_id
        if state is not None:
            params["status"] = self._gough_status_filter(state)

        payload = await self._call(
            "GET", "/api/v1/biomes/deployments", ctx, "list deployments", params=params
        )
        data = payload.dict_data()
        raw = data.get("deployments")
        rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
        items = [mapping.map_deployment(row) for row in rows]

        total = data.get("total")
        return Page(
            items=items,
            page=page,
            per_page=per_page,
            total=total if isinstance(total, int) else None,
            has_more=len(items) >= params["limit"],
        )

    @staticmethod
    def _gough_status_filter(state: OperationState) -> str:
        """Translate a portal state back into Gough's own status vocabulary.

        Only the states Gough can filter on round-trip. RUNNING becomes
        ``in_progress`` — its single spelling for work underway.
        """
        by_state: Final[dict[OperationState, str]] = {
            OperationState.PENDING: "pending",
            OperationState.RUNNING: "in_progress",
            OperationState.SUCCEEDED: "succeeded",
            OperationState.FAILED: "failed",
            OperationState.CANCELLED: "cancelled",
        }
        return by_state[state]

    async def get_operation(self, kind: str, operation_id: str, ctx: AdapterContext) -> Operation:
        """Poll one operation. The portal's refetch loop calls exactly this.

        An upgrade run's id is the composite ``biome_id:run_id`` built by
        :func:`mapping.upgrade_operation_id`, because Gough nests the route
        under the biome — see that function for why the parent is carried in
        the id rather than expected from the caller.
        """
        self._require_operation_kind(kind)
        raw_id = str(operation_id)

        if kind == OP_DEPLOYMENT:
            deployment_id = self._segment(raw_id)
            payload = await self._call(
                "GET",
                f"/api/v1/biomes/deployments/{deployment_id}",
                ctx,
                f"get deployment {deployment_id}",
            )
            return mapping.map_deployment(payload.dict_data())

        try:
            biome_id, run_id = mapping.split_upgrade_operation_id(raw_id)
        except ValueError as exc:
            raise ResourceNotFoundError(str(exc)) from exc
        payload = await self._call(
            "GET",
            f"/api/v1/biomes/{self._segment(biome_id)}" f"/upgrade-runs/{self._segment(run_id)}",
            ctx,
            f"get upgrade run {raw_id}",
        )
        return mapping.map_upgrade_run(payload.dict_data())

    async def cancel_operation(
        self, kind: str, operation_id: str, ctx: AdapterContext
    ) -> Operation:
        """Cancel a deployment and return its resulting state.

        Gough answers 409 for an operation already in a terminal state, which
        the shared taxonomy renders as ResourceConflictError — the UI should
        not have offered the button, and the conflict says so precisely.
        """
        self._require_operation_kind(kind)
        if kind != OP_DEPLOYMENT:
            raise AdapterCapabilityError(
                "gough cannot cancel an upgrade run once submitted; it rolls back "
                "on failure under its own orchestration"
            )
        operation_id = self._segment(operation_id)
        await self._call(
            "POST",
            f"/api/v1/biomes/deployments/{operation_id}/cancel",
            ctx,
            f"cancel deployment {operation_id}",
        )
        # Re-read rather than trusting the cancel response: it reports only
        # {"cancelled": true, "status": "cancelled"} and omits the timestamps
        # and phase the caller's view needs.
        return await self.get_operation(kind, operation_id, ctx)

    async def operation_logs(
        self,
        kind: str,
        operation_id: str,
        ctx: AdapterContext,
        since: datetime | None = None,
        tail: int = 100,
    ) -> list[OperationLogLine]:
        """Fetch a deployment's log lines, oldest first."""
        self._require_operation_kind(kind)
        if kind != OP_DEPLOYMENT:
            raise AdapterCapabilityError(f"gough exposes no log stream for {kind!r}")
        params: dict[str, Any] = {"tail": max(1, min(tail, 1000))}
        if since is not None:
            params["since"] = since.isoformat()

        payload = await self._call(
            "GET",
            f"/api/v1/biomes/deployments/{self._segment(operation_id)}/logs",
            ctx,
            f"get deployment logs {operation_id}",
            params=params,
        )
        raw = payload.dict_data().get("logs")
        if not isinstance(raw, list):
            return []
        return [mapping.map_log_line(row) for row in raw if isinstance(row, dict)]

    # -- metrics ----------------------------------------------------------

    async def metrics_summary(self, ctx: AdapterContext) -> MetricsSummary:
        """Summarise Gough's Prometheus exposition into portal totals.

        ``series`` is empty and that is honest, not incomplete: ``/metrics``
        is an instantaneous scrape, so Gough's REST surface has no time
        dimension to draw. Charting history is Prometheus's job, and
        fabricating a two-point series from one scrape would render as data.

        This method cannot use :meth:`_call`, because ``/metrics`` answers
        Prometheus text rather than Gough's JSON envelope and ``unwrap`` would
        fail to decode a perfectly good response. It does NOT follow that the
        error taxonomy is optional: failures go through the same
        :func:`raise_for_status` every other call uses, so a 403 here is an
        ``UpstreamAuthError`` and a 429 is a ``RateLimitedError`` with the
        product's retry hint — exactly as a caller of any other adapter method
        would get. Collapsing all of them to a bare ``UpstreamError`` (as this
        did) meant the dashboard card reported "upstream error" for a throttle
        the portal should have backed off from, and for a permission problem an
        operator could have fixed.
        """
        transport = await self._transport()
        session = GoughSession(transport)
        authed = await session.authorize(ctx)
        url = f"{ctx.base_url.rstrip('/')}/metrics"
        response = await transport.request("GET", url, authed, headers={})
        if response.status_code == 401:
            authed = await session.reauthorize(ctx)
            response = await transport.request("GET", url, authed, headers={})
        raise_for_status(response, "gough metrics scrape")

        now = datetime.now(UTC)
        return MetricsSummary(
            range=TimeRange(start=now, end=now),
            series=[],
            totals=self._parse_prometheus(response),
        )

    @staticmethod
    def _parse_prometheus(response: httpx.Response) -> dict[str, float]:
        """Reduce a Prometheus text exposition to scalar totals.

        Uses ``prometheus_client``'s own parser rather than splitting lines:
        the format has escaping, label sets and multi-line HELP text that a
        hand-rolled reader gets wrong on the first exotic metric name.

        Labelled samples are summed under the metric name, which is the right
        reduction for the counter tiles this feeds — ``gough_nodes{state=...}``
        across all states is the fleet size.
        """
        from prometheus_client.parser import text_string_to_metric_families

        totals: dict[str, float] = {}
        try:
            families = text_string_to_metric_families(response.text)
            for family in families:
                if family.type not in ("gauge", "counter"):
                    continue
                for sample in family.samples:
                    try:
                        value = float(sample.value)
                    except (TypeError, ValueError):
                        continue
                    totals[family.name] = totals.get(family.name, 0.0) + value
        except (ValueError, KeyError) as exc:
            raise UpstreamError(f"gough returned unparseable metrics: {exc}") from exc
        return totals
