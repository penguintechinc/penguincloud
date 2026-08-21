"""Tobogganing adapter — contract v2 against the live hub_api service.

Scope of this adapter, and why three of the brief's five resources are absent
============================================================================
Task 4T named five resources: ``sase``, ``sdwan``, ``firewall``, ``wireguard``
and ``headend``. Checked against a live boot of Tobogganing's ``app.url_map``
rather than against its spec, three of those cannot back a portal screen at all,
and the reason is structural rather than a matter of effort.

Tobogganing has **two auth planes**, and the portal only ever holds a credential
for one of them:

* **User plane** — ``@require_tenant`` / ``@require_scope``. The token comes
  from ``POST /api/v1/auth/login`` and carries ``aud = config.product_name`` =
  ``"tobogganing"`` (``hub_api/auth/service.py:341``,
  ``hub_api/config/__init__.py:36``). **This is what a portal connection
  stores.**
* **Machine plane** — ``@require_machine_jwt``. Its token is issued to a node by
  ``POST /api/v1/auth/token`` against a ``node_id``/``node_type``/``api_key``
  triple, and validation rejects anything whose ``aud`` is not ``"headend"``
  (``hub_api/auth/middleware.py:516-517``).

``/api/v1/firewall/rules``, ``/api/v1/wireguard/peers`` and
``/api/v1/headend/{id}/ports`` live entirely on the machine plane —
``hub_api/api/headend_routes.py:1-8`` says so outright: *"These endpoints are
called by the Go hub-router headend service."* No token the portal can obtain
satisfies them. The scopes are not the obstacle (``ROLE_SCOPES`` grants the
wildcards ``*:read``/``*:write``, which do satisfy ``firewall:read``); the
audience check fails first and there is no way to pass it with a login token.

The one mechanism that would reach them — storing Tobogganing's shared
``HEADEND_API_TOKEN`` as the connection credential, which the legacy
dual-accept branch still honours while ``tobogganing.core.machine_jwt_required``
is OFF (``middleware.py:587-626``) — is rejected deliberately: it is a
fleet-wide secret carrying ``firewall:read wireguard:read ports:read
metrics:write certs:issue swg:read`` (``hub_api/auth/machine_claims.py:9``), and
that branch pins ``g.machine_tenant = "default"`` (``:619``), so it bypasses
tenant scoping entirely. Putting a cross-tenant credential behind a per-tenant
UI would be a worse defect than the missing screen.

What IS implemented is the user-plane surface: SD-WAN clients and clusters, the
**user-reachable** WireGuard peer list (``/api/v1/sdwan/wireguard/peers``, which
is a different route from the machine-plane ``/api/v1/wireguard/peers`` with the
same name), and the SASE authoring surface (block pages, block-page routes, SWG
policy).

No operations
=============
Nest's every write answers ``202`` with an ``operationId``. Tobogganing's
user-reachable surface has **no asynchronous operations at all** — no handler
under ``hub_api/modules/sase``, ``hub_api/modules/sdwan/api`` or ``hub_api/api``
returns ``202``; every mutation answers ``200``/``201`` with the resulting
object. So ``list_operations``, ``get_operation``, ``cancel_operation`` and
``operation_logs`` raise :class:`~app.adapters.base.AdapterCapabilityError`
(501) rather than returning an empty page that would read as "nothing running",
and the SASE mutations are proxied rather than typed (see
:mod:`app.adapters.tobogganing.routes`).

Authentication
==============
The stored credential is used as a bearer token directly, as with Nest: there is
no login exchange to perform, so a ``401``/``403`` means the stored credential is
wrong (or its ``tenant`` claim does not match) and retrying would only repeat the
failure. The brief's "login + refresh with connection credentials" would require
the portal to hold a Tobogganing *password* per connection rather than a token,
which is a larger credential than the integration needs.
"""

from __future__ import annotations

from typing import Any, Final

from ..base import (
    AdapterCapabilityError,
    AdapterContext,
    HealthOnlyAdapter,
    Page,
    Resource,
    RouteRule,
)
from ..transport import Transport, get_transport
from .mapping import (
    KIND_BLOCK_PAGE,
    KIND_BLOCKPAGE_ROUTE,
    KIND_SDWAN_CLIENT,
    KIND_SDWAN_CLUSTER,
    KIND_SWG_POLICY,
    KIND_WIREGUARD_PEER,
    RESOURCE_KINDS,
    envelope_key,
    to_resource,
)
from .responses import TobogganingResponse, unwrap
from .routes import (
    HEALTH_ENDPOINT,
    PATH_BLOCKPAGE_PAGES,
    PATH_BLOCKPAGE_ROUTES,
    PATH_SDWAN_CLIENTS,
    PATH_SDWAN_CLUSTERS,
    PATH_SWG_POLICY,
    PATH_WIREGUARD_PEERS,
    PRODUCT_TYPE,
    TOBOGGANING_ROUTE_ALLOWLIST,
    TOBOGGANING_UNEXPOSED_ROUTES,
)

__all__ = ["TobogganingAdapter"]

#: The collection path each portal kind is listed from. Built from the shared
#: literals in :mod:`.routes` rather than spelled here, so the adapter and the
#: proxy allowlist cannot disagree by a trailing slash — the Phase 4G defect.
_COLLECTIONS: Final[dict[str, str]] = {
    KIND_SDWAN_CLIENT: PATH_SDWAN_CLIENTS,
    KIND_SDWAN_CLUSTER: PATH_SDWAN_CLUSTERS,
    KIND_WIREGUARD_PEER: PATH_WIREGUARD_PEERS,
    KIND_BLOCK_PAGE: PATH_BLOCKPAGE_PAGES,
    KIND_BLOCKPAGE_ROUTE: PATH_BLOCKPAGE_ROUTES,
    KIND_SWG_POLICY: PATH_SWG_POLICY,
}


class TobogganingAdapter(HealthOnlyAdapter):
    """Tobogganing networking/SASE adapter over the hub_api user-plane surface."""

    PRODUCT_TYPE: str = PRODUCT_TYPE
    DISPLAY_NAME: str = "Tobogganing"

    #: Tobogganing registers ``/health`` and ``/ready`` at the app root and
    #: registers ``/healthz`` nowhere, so the contract's default would probe a
    #: 404 and report every healthy Tobogganing as unhealthy.
    HEALTH_ENDPOINT: str = HEALTH_ENDPOINT

    route_allowlist: list[RouteRule] = TOBOGGANING_ROUTE_ALLOWLIST
    unexposed_routes: tuple[tuple[str, str], ...] = TOBOGGANING_UNEXPOSED_ROUTES

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """Report what this adapter can actually do against hub_api.

        Deliberately short. ``create_resource`` / ``update_resource`` are
        absent because the SASE authoring mutations are proxied rather than
        typed (nothing to poll — see the module docstring), and every
        operation method is absent because Tobogganing has no async
        operations on this surface.
        """
        return ["health", "list_resources", "get_resource"]

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
    ) -> TobogganingResponse:
        """Make one authenticated Tobogganing call and decode it.

        ``path`` is always built from the module literals in :mod:`.routes` —
        never caller input, so there is no segment to encode here. The
        transport pins the request to ``ctx.base_url``'s origin and injects
        the stored credential itself.
        """
        transport = await self._transport()
        url = f"{ctx.base_url.rstrip('/')}{path}"
        response = await transport.request(method, url, ctx, **kwargs)
        return unwrap(response, context)

    @staticmethod
    def _require_kind(kind: str) -> str:
        """Resolve a portal kind to its Tobogganing collection path, or 501."""
        collection = _COLLECTIONS.get(kind)
        if collection is None:
            raise AdapterCapabilityError(
                f"tobogganing does not serve resource kind {kind!r} "
                f"(supported: {sorted(RESOURCE_KINDS)})"
            )
        return collection

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
        """List one kind of Tobogganing resource.

        Tobogganing paginates **nothing** — every list handler returns the
        tenant's whole collection in one response, with no ``page``/``limit``
        query parameter anywhere on the user plane. So the page is sliced
        portal-side and ``total`` IS known exactly (the whole set arrived),
        which is the one case where reporting a total is honest rather than
        fabricated.

        ``cursor`` is accepted to satisfy the contract and ignored: the product
        has no cursor paginator, and pretending otherwise would let a caller
        believe it was paging server-side.
        """
        path = self._require_kind(kind)
        response = await self._call("GET", path, ctx, f"list {kind}")
        rows = response.items(envelope_key(kind))
        resources = [to_resource(kind, row) for row in rows]

        start = max(page - 1, 0) * per_page
        window = resources[start : start + per_page]
        return Page(
            items=window,
            page=page,
            per_page=per_page,
            total=len(resources),
            has_more=start + per_page < len(resources),
        )

    async def get_resource(self, kind: str, resource_id: str, ctx: AdapterContext) -> Resource:
        """Fetch one resource by id.

        Tobogganing serves no item route for any of these kinds — the
        block-page item path is ``PUT``-only and the rest are list-only — so
        this filters the collection rather than requesting a path that would
        404 and read to the operator as "this resource does not exist" when
        the truth is "this product has no detail endpoint".
        """
        from ..base import ResourceNotFoundError

        path = self._require_kind(kind)
        response = await self._call("GET", path, ctx, f"get {kind} {resource_id}")
        for row in response.items(envelope_key(kind)):
            resource = to_resource(kind, row)
            if resource.id == resource_id:
                return resource
        raise ResourceNotFoundError(
            f"tobogganing has no {kind} with id {resource_id!r} in this tenant"
        )
