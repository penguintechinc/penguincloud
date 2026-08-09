"""Typed create and delete for a connected product's resources.

Routes (under ``/api/v1/products/<product_id>``):

=====================================  ==========================================
``POST   /resources/<kind>``           create; returns the row and any poll handle
``DELETE /resources/<kind>/<id>``      delete
=====================================  ==========================================

Why these are typed and not proxied
===================================
Reads are not here. A product's collections are read through the PROXY, whose
deny-by-default allowlist each adapter declares — that is the established path
(see :mod:`app.proxy`) and it hands the browser the product's own payload,
which is what a product-specific screen renders.

Writes are different, and Nest is the case that forces the distinction. Its
adapter's allowlist is deliberately **GET-only**: every Nest write answers
``202`` with an ``operationId`` because provisioning continues after the
response, and :mod:`app.adapters.base` states that a mutation whose result the
portal must interpret belongs on a typed adapter method rather than the byte
pipe. So ``NestAdapter.create_resource`` and ``delete_resource`` were
implemented, tested against a live Nest — and unreachable, because nothing
exposed them over HTTP. A Databases screen could list and act but not create
or delete.

Two things this route does that a proxied write cannot:

* **Publishes the create's poll handle.** ``create_resource`` returns a
  ``Resource``, so an async create carries its operation id in
  ``metadata[RESOURCE_OPERATION_ID_KEY]``. That is promoted to a typed
  ``operation_id`` field here, so the UI can follow provisioning instead of
  rendering a row as ready the moment creation was accepted.
* **Preserves the delete conflict.** Nest answers ``409`` when a resource is
  still referenced; the adapter maps it to ``ResourceConflictError`` and the
  shared taxonomy renders it as ``409`` with a product-neutral message. A
  proxied 409 body is product-specific, so a confirm dialog cannot tell
  "still referenced" from "already gone".

Security
========
Authorisation is :func:`app.product_access.resolve_product_context`, shared
verbatim with :mod:`app.operations_api`: membership, then scope, then
credential decryption, and 404 rather than 403 for a non-member. Creates and
deletes both require ``manage``.

``kind`` is never interpolated into a product URL here — the adapter validates
it against its own literal table and raises
:class:`~app.adapters.base.AdapterCapabilityError` (501) for anything else.

``resource_id`` reaches the adapter as an opaque value, and **the adapter**
encodes it where it becomes a path segment
(:func:`~app.adapters.base.quote_path_segment`). This paragraph previously said
the *transport* did that; it does not. ``Transport.request`` takes a built URL
string and hands it to httpx, and its only path check is
:func:`~app.adapters.base.normalize_proxy_path` inside the origin pin, which
refuses traversal rather than encoding anything. The distinction matters
because Werkzeug percent-DECODES ``<resource_id>`` before this handler sees it,
so ``%3F`` arrives as a literal ``?`` — interpolated raw, that would start a
query string at the product. Any adapter reached through these routes owns that
encoding; do not assume a layer below has done it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_response

from .adapters import get_adapter
from .adapters.base import (
    AdapterError,
    RESOURCE_OPERATION_ID_KEY,
    Resource,
)
from .middleware import auth_required
from .product_access import (
    ACTION_MANAGE,
    NOT_FOUND,
    adapter_failure,
    iso,
    resolve_product_context,
)
from .tenancy import tenancy_aware

logger = logging.getLogger(__name__)

resources_bp = Blueprint("resources", __name__)


@dataclass(slots=True, frozen=True)
class ResourceView:
    """Wire shape for one resource.

    A named projection rather than the dataclass itself, for the reason
    :class:`~app.operations_api.OperationView` gives: ``metadata`` is the
    adapter's free-form bag with no declared schema, so publishing it wholesale
    would make every key an adapter happens to stash there part of the portal's
    wire contract by accident.

    ``operation_id`` is the one thing lifted out of it, and only because the
    contract names that key (:data:`~app.adapters.base.RESOURCE_OPERATION_ID_KEY`)
    for exactly this purpose — a create the product completes asynchronously.
    ``None`` means the create finished synchronously, which is how the UI tells
    "nothing to poll" from "poll this".
    """

    id: str
    kind: str
    name: str
    status: str | None
    parent_id: str | None
    parent_kind: str | None
    operation_id: str | None
    created_at: str | None
    updated_at: str | None

    @classmethod
    def of(cls, resource: Resource) -> ResourceView:
        """Project an adapter Resource onto the wire shape."""
        handle = resource.metadata.get(RESOURCE_OPERATION_ID_KEY)
        return cls(
            id=resource.id,
            kind=resource.kind,
            name=resource.name,
            status=resource.status,
            parent_id=resource.parent_id,
            parent_kind=resource.parent_kind,
            operation_id=str(handle) if handle else None,
            created_at=iso(resource.created_at),
            updated_at=iso(resource.updated_at),
        )


@dataclass(slots=True, frozen=True)
class ResourceDeletedResponse:
    """Acknowledgement that a resource was deleted.

    A body rather than a bare ``204`` because the deletion may be the start of
    teardown rather than the end of it, and the UI needs somewhere to read that
    from. ``kind`` and ``id`` are echoed so a client handling several deletions
    can attribute the answer without tracking request order.
    """

    kind: str
    id: str
    deleted: bool = True


@resources_bp.route("/<int:product_id>/resources/<kind>", methods=["POST"])
@auth_required
@tenancy_aware
@validate_response(ResourceView, 201)
async def create_resource(product_id: int, kind: str) -> tuple[Any, int]:
    """Create one resource in the connected product.

    ``201`` even when the product answered ``202``: from the portal's side the
    resource now exists and is addressable. Whether it is finished provisioning
    is what ``operation_id`` is for — collapsing the two into a ``202`` here
    would leave a client that ignores the body unable to tell a created
    resource from a rejected one.
    """
    ctx, product_type, error = await resolve_product_context(
        product_id, ACTION_MANAGE
    )
    if error is not None or ctx is None or product_type is None:
        return error or NOT_FOUND

    body = await request.get_json(silent=True)
    if not isinstance(body, dict):
        return {"error": "request body must be a JSON object"}, 400

    adapter = get_adapter(product_type, ctx)
    try:
        resource = await adapter.create_resource(kind, body, ctx)
    except AdapterError as exc:
        return adapter_failure(exc, product_id, f"create_resource:{kind}")

    logger.info(
        "resource_created",
        extra={"product_id": product_id, "kind": kind, "resource_id": resource.id},
    )
    return ResourceView.of(resource), 201


@resources_bp.route(
    "/<int:product_id>/resources/<kind>/<resource_id>", methods=["DELETE"]
)
@auth_required
@tenancy_aware
@validate_response(ResourceDeletedResponse)
async def delete_resource(
    product_id: int, kind: str, resource_id: str
) -> tuple[Any, int]:
    """Delete one resource from the connected product.

    A product that refuses because the resource is still referenced surfaces as
    ``409`` through the shared taxonomy, which is the distinction a confirm
    dialog needs — see the module docstring.
    """
    ctx, product_type, error = await resolve_product_context(
        product_id, ACTION_MANAGE
    )
    if error is not None or ctx is None or product_type is None:
        return error or NOT_FOUND

    adapter = get_adapter(product_type, ctx)
    try:
        await adapter.delete_resource(kind, resource_id, ctx)
    except AdapterError as exc:
        return adapter_failure(exc, product_id, f"delete_resource:{kind}")

    logger.info(
        "resource_deleted",
        extra={"product_id": product_id, "kind": kind, "resource_id": resource_id},
    )
    return ResourceDeletedResponse(kind=kind, id=resource_id), 200
