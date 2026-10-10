"""WaddleAI adapter — Phase 8 acceptance test (design §8), read-only cut.

Scope: a REPRESENTATIVE subset, not the whole product
=======================================================
This adapter exists to prove the onboarding mechanism (adapter + manifest +
registry lines, zero new webui/CLI code), not to cover WaddleAI's whole
surface. It implements exactly three read-only resources —
:data:`~app.adapters.waddleai.mapping.KIND_PROVIDER`,
:data:`~app.adapters.waddleai.mapping.KIND_KNOWLEDGE_DOCUMENT`,
:data:`~app.adapters.waddleai.mapping.KIND_QUOTA` — verified against
WaddleAI's own handler source
(``services/management/app/api/v1/{providers,knowledge,quotas}.py``,
``penguintechinc/waddleai`` on GitHub), not merely its OpenAPI spec.
Deliberately excluded, and why:

* **Anything naming a secret.** ``keys.py``'s ``/api/v1/keys`` surface
  handles virtual-key ``api_key`` values; even the masked form
  (``api_key_masked``) is the kind of field
  :attr:`~app.adapters.manifest.ConsoleManifest`'s ``SENSITIVE_FIELD``
  refusal exists to keep out of a committed manifest. Not implemented here,
  so there is nothing for that gate to have to refuse.
* **Portal-native domains.** ``users`` and ``organizations`` are identity
  concepts the portal already owns (tenants, users) — proxying WaddleAI's
  own copies would duplicate, not extend, the portal's data model.
* **Everything else** (routing policies, RAG config, llama.cpp deployments,
  Cilium status, cache configs, webhooks, ...) — real WaddleAI surface, out
  of scope for what this PR needs to prove.

No async operations, and no item route, for any of the three
================================================================
``providers``/``knowledge``/``quotas`` handlers all answer synchronously —
none of the three returns ``202`` with something to poll — so, matching
:mod:`app.adapters.tobogganing.adapter`'s "No operations" precedent,
``list_operations``/``get_operation``/``cancel_operation``/``operation_logs``
are unsupported.

Every resource here also declares ``item_path=None`` in the manifest (see
``manifest.py``), even though ``providers`` and ``knowledge`` genuinely have
item GET routes on the product — see ``routes.py``'s module docstring for
why: the provider detail response carries additional fields
(``extra_config``, ``tls_config``, ``ailb_route_config``) not reviewed for
this cut, and WaddleAI has NO per-id read for a ``quota`` row at all (ids are
not unique across its three row types — see ``mapping.py``). ``get_resource``
below is still implemented for all three kinds by filtering the collection,
matching :meth:`~app.adapters.tobogganing.adapter.TobogganingAdapter.get_resource`'s
approach — except for ``quota``, which refuses (see that method's docstring).

Authentication
==============
The stored credential is used as a bearer token directly: WaddleAI issues
one via ``POST /api/v1/auth/login`` and there is no separate refresh flow
this adapter needs to drive, matching Nest's and Tobogganing's precedent.
"""

from __future__ import annotations

from typing import Any, Final

from ...adapter_errors import AdapterCapabilityError, ResourceNotFoundError
from ..base import (
    AdapterContext,
    HealthOnlyAdapter,
    Page,
    Resource,
    RouteRule,
)
from ..transport import Transport, get_transport
from .mapping import (
    KIND_KNOWLEDGE_DOCUMENT,
    KIND_PROVIDER,
    KIND_QUOTA,
    RESOURCE_KINDS,
    envelope_key,
    to_resource,
)
from .responses import WaddleAIResponse, unwrap
from .routes import (
    HEALTH_ENDPOINT,
    PATH_KNOWLEDGE,
    PATH_PROVIDERS,
    PATH_QUOTAS,
    PRODUCT_TYPE,
    WADDLEAI_ROUTE_ALLOWLIST,
    WADDLEAI_UNEXPOSED_ROUTES,
)

__all__ = ["WaddleAIAdapter"]

#: The collection path each portal kind is listed from — built from the
#: shared literals in :mod:`.routes`, never re-typed, so the adapter and the
#: proxy allowlist cannot disagree by a trailing slash (the Phase 4G defect).
_COLLECTIONS: Final[dict[str, str]] = {
    KIND_PROVIDER: PATH_PROVIDERS,
    KIND_KNOWLEDGE_DOCUMENT: PATH_KNOWLEDGE,
    KIND_QUOTA: PATH_QUOTAS,
}


class WaddleAIAdapter(HealthOnlyAdapter):
    """WaddleAI adapter over its management API — read-only cut, see module docstring."""

    PRODUCT_TYPE: str = PRODUCT_TYPE
    DISPLAY_NAME: str = "WaddleAI"

    #: WaddleAI registers ``/healthz`` at the app root — the same value
    #: :class:`~app.adapters.base.HealthOnlyAdapter` already defaults to,
    #: spelled out for legibility.
    HEALTH_ENDPOINT: str = HEALTH_ENDPOINT

    route_allowlist: list[RouteRule] = WADDLEAI_ROUTE_ALLOWLIST
    unexposed_routes: tuple[tuple[str, str], ...] = WADDLEAI_UNEXPOSED_ROUTES

    async def capabilities(self, ctx: AdapterContext) -> list[str]:
        """Report what this adapter can actually do against WaddleAI.

        ``create_resource``/``update_resource``/``delete_resource`` and every
        operation method are absent — this cut is read-only and WaddleAI's
        three implemented resources have no async operations to poll (see
        the module docstring).
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
    ) -> WaddleAIResponse:
        """Make one authenticated WaddleAI call and decode it.

        ``path`` is always built from the module literals in :mod:`.routes`
        — never caller input, so there is no segment to encode here. The
        transport pins the request to ``ctx.base_url``'s origin and injects
        the stored credential itself.
        """
        transport = await self._transport()
        url = f"{ctx.base_url.rstrip('/')}{path}"
        response = await transport.request(method, url, ctx, **kwargs)
        return unwrap(response, context)

    @staticmethod
    def _require_kind(kind: str) -> str:
        """Resolve a portal kind to its WaddleAI collection path, or 501."""
        collection = _COLLECTIONS.get(kind)
        if collection is None:
            raise AdapterCapabilityError(
                f"waddleai does not serve resource kind {kind!r} "
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
        """List one kind of WaddleAI resource.

        WaddleAI paginates **none** of these three collections — every list
        handler (``list_providers``, ``list_knowledge``, ``list_quotas``)
        returns the caller's whole set in one response, with no
        ``page``/``limit`` query parameter. So the page is sliced
        portal-side and ``total`` IS known exactly, matching
        :meth:`~app.adapters.tobogganing.adapter.TobogganingAdapter.list_resources`'s
        identical reasoning.

        ``cursor`` is accepted to satisfy the contract and ignored: there is
        no cursor paginator to honour.
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
        """Fetch one resource by id, by filtering its collection.

        WaddleAI serves a real ``GET .../{id}`` for ``provider`` and
        ``knowledge_document`` — deliberately not used here; see the module
        docstring for why (unreviewed extra fields on the provider detail
        response; no field the knowledge detail response adds over the list
        row). Filtering the already-fetched collection avoids relying on
        either.

        ``quota`` refuses outright: WaddleAI itself has no
        ``GET /api/v1/quotas/{id}`` (only ``/quotas/status/{entity_id}``,
        which REQUIRES an ``entity_type`` disambiguator precisely because an
        organization, a user and a virtual key can share the same id — see
        ``mapping.py``'s module docstring). Filtering ``quota`` rows by id
        alone could silently return the wrong entity, which is a worse
        outcome than a 501.
        """
        if kind == KIND_QUOTA:
            raise AdapterCapabilityError(
                "waddleai quota ids are not unique across organization/user/key "
                "rows in a single GET /api/v1/quotas response — get_resource(quota) "
                "would risk returning the wrong entity, so it is refused rather "
                "than guessed"
            )

        path = self._require_kind(kind)
        response = await self._call("GET", path, ctx, f"get {kind} {resource_id}")
        for row in response.items(envelope_key(kind)):
            resource = to_resource(kind, row)
            if resource.id == resource_id:
                return resource
        raise ResourceNotFoundError(f"waddleai has no {kind} with id {resource_id!r}")
