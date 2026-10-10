"""``GET /api/v1/console/manifests`` — the descriptor document Design §3 serves.

Routes-layer (rank 4): imports proxy (adapters/product_access), auth,
tenancy and licensing/flags, nothing above it — see
``tests/architecture/test_layer_boundaries.py``.

Behind ``penguincloud.declarative_console``
============================================
A genuinely new feature (general.md: new flags default OFF), not a licensed
one — the manifest schema and this endpoint are reviewable/statically
checkable regardless of tier, so gating by licence would be the wrong axis.
Disabled, this route answers ``403`` with :func:`app.flags.feature_disabled_body`
rather than a 404: the route exists and is documented in the OpenAPI spec,
only switched off.

Membership is oracle-safe by construction, not by an explicit check
=====================================================================
This endpoint deliberately does **not** perform its own
"is the caller a member of ``tenant_id``" check before querying
connections. It resolves each connection through
:func:`app.product_access.resolve_product_context`, which already answers
``(None, None, NOT_FOUND)`` for a non-member — so a caller who is not a
member of ``tenant_id`` and a member with zero eligible products receive
the byte-identical ``{"manifests": [], "count": 0}``. Adding a separate
top-level membership check would either duplicate that (harmless) or use
the coarse ``products:read`` scope specifically (wrong per Design §5.4: a
caller holding only the narrow ``products:gough:read`` scope must still see
Gough's manifest through this tenant-wide listing, and a coarse-scope gate
in front would refuse them before ``resolve_product_context`` ever got the
chance to say yes).

Subtract-only overlay, per connection
======================================
Each connection's manifest is passed through
:func:`app.adapters.manifest.apply_capabilities_overlay` against that
connection's OWN :meth:`~app.adapters.base.Adapter.capabilities` answer — a
health-degraded connection can only ever lose columns/actions/reads from the
committed manifest, never gain any (Design §2, Approach B). A connection
whose context cannot be resolved (deactivated, flag off, decrypt failure) or
whose ``capabilities()`` call raises is skipped entirely rather than failing
the whole tenant's response — one broken product connection must not blank
every other product's console.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_response

from . import flags
from .adapter_errors import AdapterError
from .adapters import MANIFEST_REGISTRY, get_adapter
from .adapters.manifest import ConsoleManifest, ManifestError, apply_capabilities_overlay
from .middleware import auth_required, get_current_user
from .models import get_tenant_product_connections
from .product_access import ACTION_READ, resolve_product_context
from .tenancy import tenancy_aware

logger = logging.getLogger(__name__)

console_manifests_bp = Blueprint("console_manifests", __name__)

#: Flag key — see the module docstring.
_FEATURE = "declarative_console"


@dataclass(slots=True, frozen=True)
class ProductManifestEntry:
    """One product's overlaid manifest plus the connection it came from."""

    product_id: int
    product_type: str
    manifest: ConsoleManifest


@dataclass(slots=True, frozen=True)
class ConsoleManifestsResponse:
    """Envelope for ``GET /api/v1/console/manifests``."""

    manifests: list[ProductManifestEntry]
    count: int


async def _tenant_id_from_request() -> int | None:
    """Extract ``tenant_id`` from the query string.

    Matches :func:`app.products._get_tenant_id_from_request`'s convention
    rather than importing it: that helper is private to ``products.py`` and
    duplicating four lines here is cheaper than widening its export surface
    for one caller.
    """
    raw = request.args.get("tenant_id")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@console_manifests_bp.route("/manifests", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(ConsoleManifestsResponse)
async def list_console_manifests() -> tuple[Any, int]:
    """Every product this tenant is connected to that has a committed manifest.

    Pruned by (in order): flag, membership+per-product-scope+licence+
    deactivation (all via :func:`resolve_product_context`), and finally the
    subtract-only ``capabilities()`` overlay. See the module docstring for
    why there is no separate top-level membership check.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    if not await flags.is_feature_available(_FEATURE, str(user["id"])):
        return flags.feature_disabled_body(_FEATURE), 403

    tenant_id = await _tenant_id_from_request()
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    connections = await get_tenant_product_connections(tenant_id)
    entries: list[ProductManifestEntry] = []
    for conn in connections:
        product_type = str(conn.get("product_type", ""))
        manifest = MANIFEST_REGISTRY.get(product_type)
        if manifest is None:
            continue  # no committed manifest for this product yet

        product_id = int(conn["id"])
        ctx, resolved_type, error = await resolve_product_context(product_id, ACTION_READ)
        if error is not None or ctx is None or resolved_type is None:
            logger.info(
                "console_manifest_context_refused",
                extra={"product_id": product_id, "product_type": product_type},
            )
            continue

        adapter = get_adapter(resolved_type, ctx)
        try:
            capabilities = await adapter.capabilities(ctx)
        except AdapterError as exc:
            logger.info(
                "console_manifest_capabilities_failed",
                extra={
                    "product_id": product_id,
                    "product_type": product_type,
                    "error_type": type(exc).__name__,
                },
            )
            continue

        try:
            overlaid = apply_capabilities_overlay(manifest, capabilities)
        except ManifestError as exc:  # pragma: no cover - overlay only ever subtracts
            # Should not happen -- the overlay only ever subtracts from an
            # already-valid manifest -- but "never crash on a live
            # connection's answer" outranks "this branch is unreachable
            # today" for a route that fans out over every connection a
            # tenant has.
            logger.warning(
                "console_manifest_overlay_failed",
                extra={
                    "product_id": product_id,
                    "product_type": product_type,
                    "error_type": type(exc).__name__,
                },
            )
            continue
        entries.append(
            ProductManifestEntry(
                product_id=product_id, product_type=product_type, manifest=overlaid
            )
        )

    return ConsoleManifestsResponse(manifests=entries, count=len(entries)), 200
