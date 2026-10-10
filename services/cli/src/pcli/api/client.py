"""Async HTTP client for the portal's REST API (`/api/v1/...`).

Every read pcli performs -- manifests, products, tenants, and every
manifest-discovered `list`/`get` -- goes through this one class, so the
error taxonomy (`raise_for_portal_error`) and auth-header injection are
applied uniformly rather than re-implemented per command.

Reads (list/get) for a manifest-discovered resource go through the byte
PROXY (`/api/v1/products/{id}/proxy/{path}`), never a typed endpoint --
`ResourceDescriptor`'s own docstring states this is the only read path this
schema version has (`transport` only governs the typed-mutation surface).
See `to_proxy_path`/`unwrap_envelope`.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from ..errors import ManifestError, PortalAPIError
from .manifest_types import EnvelopeSpec, ProductManifestEntry, parse_manifests_response

API_PREFIX: str = "/api/v1"


def to_proxy_path(path_bytes: str) -> str:
    """Strip exactly one leading `/` from a manifest-declared path.

    `ListSpec.path_bytes`/`ItemPathSpec.prefix` are byte-equal to the
    ADAPTER's own registered route (e.g. `/api/v1/nodes/`, leading slash
    included -- `ResourceDescriptor`'s docstring), but the byte-proxy route
    (`/api/v1/products/{id}/proxy/{proxy_path}`) wants the PRODUCT-relative
    fragment with no leading slash. Handing the raw `path_bytes` to the
    proxy builds a double slash (`.../proxy//api/v1/nodes/`), which several
    products' own routers 404 on with no redirect -- see
    `services/webui/src/client/components/kit/manifestListFetcher.ts`'s
    `toProxyPath`, whose exact one-character stripping rule this mirrors so
    pcli and the webui build byte-identical proxy paths from the same
    manifest field.
    """
    return path_bytes[1:] if path_bytes.startswith("/") else path_bytes


def unwrap_envelope(payload: Any, envelope: EnvelopeSpec) -> list[dict[str, Any]]:
    """Descend `payload[key]` for each key in `envelope.keys`, in order.

    `EnvelopeSpec.keys` is the exact, validated, ordered path from a
    proxied response's raw body to its item array (see that class's own
    docstring for two real examples: `("data", "nodes")` vs. `("groups",)`
    for two resources declared in the same product module). Unlike the
    webui's own `readManifestEnvelope` (which GUESSES between a top-level
    key and one nested under `data` because schema v1 could not express the
    difference), schema v2's `EnvelopeSpec.keys` is authoritative -- so a
    missing key or a non-list result at the end is a genuine mismatch
    between what the manifest promised and what the product returned, and
    is raised as `ManifestError` rather than silently degraded to an empty
    list. A script piping pcli's output needs to be able to tell "zero
    rows" from "something is broken" apart.
    """
    current: Any = payload
    for key in envelope.keys:
        if not isinstance(current, dict) or key not in current:
            raise ManifestError(
                f"expected key {key!r} while unwrapping the response "
                f"(envelope keys={envelope.keys!r}); the product's response "
                f"shape does not match what its manifest declared."
            )
        current = current[key]
    if not isinstance(current, list):
        raise ManifestError(
            f"envelope {envelope.keys!r} resolved to a {type(current).__name__}, " f"not a list."
        )
    return current


def raise_for_portal_error(response: httpx.Response) -> None:
    """Raise `PortalAPIError` for any non-2xx response, else return None.

    Reads the portal's `{"error": "<message>"}` shape (`app.product_access.
    adapter_failure`, `app.device_auth._device_error`, and every plain
    `{"error": ...}` 4xx across the API share this one convention) when
    present, falling back to the raw response text otherwise -- never
    raises on a body it cannot parse, since the failure to report is itself
    the more urgent fact.
    """
    if response.is_success:
        return
    body: Any = None
    message = f"HTTP {response.status_code}"
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = response.json()
        except ValueError:
            body = None
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        message = body["error"]
    elif response.text:
        message = response.text[:500]
    raise PortalAPIError(message, status_code=response.status_code, body=body)


class PortalClient:
    """Thin async wrapper around `httpx.AsyncClient`, scoped to one portal + token."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        token_type: str = "Bearer",  # noqa: S107 -- an auth SCHEME name, not a credential
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Build the underlying `httpx.AsyncClient`.

        `transport` is exposed purely for tests (`httpx.MockTransport`) --
        no real network call in the test suite for this module.
        """
        headers = {"Authorization": f"{token_type} {token}"} if token else {}
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        """Support `async with PortalClient(...) as client:`."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying `httpx.AsyncClient`."""
        await self._http.aclose()

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = await self._http.get(f"{API_PREFIX}{path}", params=params)
        raise_for_portal_error(response)
        return response.json()

    async def _post(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        response = await self._http.post(f"{API_PREFIX}{path}", json=json_body)
        raise_for_portal_error(response)
        return response.json()

    async def me(self) -> dict[str, Any]:
        """`GET /api/v1/auth/me` -- the caller's own profile."""
        result: dict[str, Any] = await self._get("/auth/me")
        return result

    async def list_manifests(self) -> tuple[ProductManifestEntry, ...]:
        """`GET /api/v1/console/manifests` -- every connected product's manifest."""
        body = await self._get("/console/manifests")
        return parse_manifests_response(body)

    async def list_products(self) -> list[dict[str, Any]]:
        """`GET /api/v1/products` -- the tenant's product connections."""
        body = await self._get("/products")
        products: list[dict[str, Any]] = body.get("products", [])
        return products

    async def list_tenants(self, *, include_children: bool = False) -> list[dict[str, Any]]:
        """`GET /api/v1/tenants` -- tenants the caller is a member of (+ admins over)."""
        params = {"include_children": "true"} if include_children else None
        body = await self._get("/tenants", params=params)
        tenants: list[dict[str, Any]] = body.get("tenants", [])
        return tenants

    async def switch_tenant(self, tenant_id: int) -> dict[str, Any]:
        """`POST /api/v1/tenants/{tenant_id}/switch` -- re-issues a tenant-scoped JWT."""
        result: dict[str, Any] = await self._post(f"/tenants/{tenant_id}/switch")
        return result

    async def proxy_get(self, connection_id: int, proxy_path: str) -> Any:
        """`GET /api/v1/products/{connection_id}/proxy/{proxy_path}` -- raw passthrough.

        `proxy_path` must already be PRODUCT-relative (no leading slash) --
        see `to_proxy_path`. Returns the parsed JSON body verbatim; callers
        that need a list unwrap it themselves via `unwrap_envelope`.
        """
        response = await self._http.get(f"{API_PREFIX}/products/{connection_id}/proxy/{proxy_path}")
        raise_for_portal_error(response)
        return response.json()
