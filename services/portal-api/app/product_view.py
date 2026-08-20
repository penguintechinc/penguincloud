"""The one projection every product-connection surface serves.

Why this module exists
======================
``GET /api/v1/products``, ``POST /api/v1/products`` and
``GET /api/v1/dashboard/overview`` all serve the same underlying row —
``app.models.get_tenant_product_connections`` / ``create_product_connection``
— and two of the three had no response schema at all: whatever
``dict(row)`` produced went straight onto the wire. ``security.md`` names
this exact failure:

    a bug meant an endpoint that was only supposed to return a single string
    ended up returning the entire database object it came from ... Nothing
    crashed, no error, no signal anything was wrong.

``api_key``/``api_secret`` are not the risk here — ``app.models.
_mask_connection_secrets`` already replaces them with ``MASKED_SECRET``
before a row ever reaches a route, and every accessor this module's
projector is fed from goes through it (see ``app.models.
get_tenant_product_connections``, ``get_product_connection_by_id``). The
risk is the same one ``app.audit_view`` was written for: an unscoped
passthrough silently starts publishing a column added tomorrow.

``metadata_json`` is excluded for exactly ``audit_view``'s reason — a
free-form ``Text`` column nothing currently writes to, which is exactly why
excluding it now is cheap: the first writer that starts filling it would
otherwise publish it through every surface built on this projector at once,
with no code change anywhere near them. Add it back deliberately, once, if a
product genuinely needs to surface it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _isoformat(value: Any) -> str | None:
    """Render a datetime column as ISO-8601, tolerating NULL or a string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


# NOTE: this class's docstring is EXPORTED into openapi/v1.yaml as the
# ProductConnection schema description, so it is written for the API's
# readers. The reasoning behind the field choices lives in this module's
# own docstring above, which is not published.
@dataclass(slots=True, frozen=True)
class ProductConnection:
    """One tenant's connection to a product.

    ``api_key``/``api_secret`` are always ``***`` when a credential is
    configured, or empty when none is — never the stored ciphertext.

    Attributes:
        id: Identifier of this connection.
        tenant_id: The tenant this connection belongs to.
        product_type: Which product this connects to, e.g. ``gough``.
        display_name: Operator-assigned label for this connection.
        base_url: The connected product's base URL.
        api_key: Masked — ``***`` if configured, else empty.
        api_secret: Masked — ``***`` if configured, else empty.
        auth_type: How the portal authenticates to the product.
        health_endpoint: Path the health poller probes on this connection.
        api_version: API major version the portal addresses on this product.
        is_active: Whether the health poller and proxy still serve this
            connection.
        health_status: Last cached health result: healthy, degraded,
            unhealthy or unknown.
        discovered: True when this connection was created by network
            discovery rather than entered by an operator.
        last_health_check: When the health status was last refreshed,
            ISO-8601.
        created_at: When this connection was registered, ISO-8601.
        updated_at: When this connection was last modified, ISO-8601.
    """

    id: int
    tenant_id: int
    product_type: str
    display_name: str
    base_url: str
    api_key: str
    api_secret: str
    auth_type: str
    health_endpoint: str
    api_version: str
    is_active: bool
    health_status: str
    discovered: bool
    last_health_check: str | None
    created_at: str | None
    updated_at: str | None


def to_product_connection(row: Any) -> ProductConnection:
    """Project one product_connections row onto the published field set.

    Reads by key rather than by attribute so it accepts a penguin-dal Row
    and a plain dict identically. Expects credentials already masked by
    ``app.models._mask_connection_secrets`` — this function does not mask
    them itself, so it must only ever be fed a row that already went
    through one of that module's public accessors.
    """
    data = dict(row)
    return ProductConnection(
        id=int(data["id"]),
        tenant_id=int(data["tenant_id"]),
        product_type=str(data.get("product_type") or ""),
        display_name=str(data.get("display_name") or ""),
        base_url=str(data.get("base_url") or ""),
        api_key=str(data.get("api_key") or ""),
        api_secret=str(data.get("api_secret") or ""),
        auth_type=str(data.get("auth_type") or ""),
        health_endpoint=str(data.get("health_endpoint") or ""),
        api_version=str(data.get("api_version") or ""),
        is_active=bool(data.get("is_active")),
        health_status=str(data.get("health_status") or "unknown"),
        discovered=bool(data.get("discovered")),
        last_health_check=_isoformat(data.get("last_health_check")),
        created_at=_isoformat(data.get("created_at")),
        updated_at=_isoformat(data.get("updated_at")),
    )


def to_product_connections(rows: Any) -> list[ProductConnection]:
    """Project a result set onto the published field set."""
    return [to_product_connection(row) for row in rows]
