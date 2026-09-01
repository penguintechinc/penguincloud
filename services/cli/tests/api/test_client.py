"""Tests for `pcli.api.client` -- proxy path building, envelope unwrap, error mapping."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from pcli.api.client import PortalClient, raise_for_portal_error, to_proxy_path, unwrap_envelope
from pcli.api.manifest_types import EnvelopeSpec
from pcli.errors import ManifestError, PortalAPIError
from pcli.exit_codes import (
    EXIT_FORBIDDEN,
    EXIT_NOT_FOUND,
    EXIT_RATE_LIMITED,
    EXIT_UNAUTHENTICATED,
    EXIT_UPSTREAM,
    EXIT_VALIDATION,
)


def test_to_proxy_path_strips_one_leading_slash() -> None:
    """To proxy path strips one leading slash."""
    assert to_proxy_path("/api/v1/nodes/") == "api/v1/nodes/"


def test_to_proxy_path_leaves_relative_path_unchanged() -> None:
    """To proxy path leaves relative path unchanged."""
    assert to_proxy_path("api/v1/nodes/") == "api/v1/nodes/"


def test_to_proxy_path_only_strips_one_slash() -> None:
    """Matches the webui's own `toProxyPath` byte-for-byte.

    A double leading slash in the manifest (should never happen) is not
    further mangled.
    """
    assert to_proxy_path("//weird") == "/weird"


class TestUnwrapEnvelope:
    """Unwrap envelope."""

    def test_nested_data_key(self) -> None:
        """Nested data key."""
        payload = {"status": "success", "data": {"nodes": [{"id": "1"}]}, "meta": {}}
        rows = unwrap_envelope(payload, EnvelopeSpec(keys=("data", "nodes")))
        assert rows == [{"id": "1"}]

    def test_bare_key(self) -> None:
        """Bare key."""
        payload = {"groups": [{"id": "g1"}], "total": 1}
        rows = unwrap_envelope(payload, EnvelopeSpec(keys=("groups",)))
        assert rows == [{"id": "g1"}]

    def test_missing_key_raises_manifest_error(self) -> None:
        """Missing key raises manifest error."""
        payload = {"status": "success"}
        with pytest.raises(ManifestError, match="nodes"):
            unwrap_envelope(payload, EnvelopeSpec(keys=("data", "nodes")))

    def test_non_list_result_raises_manifest_error(self) -> None:
        """Non list result raises manifest error."""
        payload: dict[str, Any] = {"nodes": {"not": "a list"}}
        with pytest.raises(ManifestError):
            unwrap_envelope(payload, EnvelopeSpec(keys=("nodes",)))

    def test_zero_rows_is_not_an_error(self) -> None:
        """An empty (but present, correctly-shaped) array is a legitimate answer."""
        payload: dict[str, Any] = {"nodes": []}
        assert unwrap_envelope(payload, EnvelopeSpec(keys=("nodes",))) == []


class TestRaiseForPortalError:
    """Raise for portal error."""

    def test_success_returns_none(self) -> None:
        """Success returns none."""
        response = httpx.Response(200, json={"ok": True})
        raise_for_portal_error(response)  # must not raise

    def test_error_shape_extracts_message(self) -> None:
        """Error shape extracts message."""
        response = httpx.Response(404, json={"error": "not found"})
        with pytest.raises(PortalAPIError) as exc_info:
            raise_for_portal_error(response)
        assert str(exc_info.value) == "not found"
        assert exc_info.value.status_code == 404
        assert exc_info.value.exit_code == EXIT_NOT_FOUND

    def test_non_json_body_falls_back_to_text(self) -> None:
        """Non json body falls back to text."""
        response = httpx.Response(500, text="upstream on fire")
        with pytest.raises(PortalAPIError, match="upstream on fire"):
            raise_for_portal_error(response)

    @pytest.mark.parametrize(
        ("status", "expected_exit"),
        [
            (401, EXIT_UNAUTHENTICATED),
            (403, EXIT_FORBIDDEN),
            (404, EXIT_NOT_FOUND),
            (422, EXIT_VALIDATION),
            (429, EXIT_RATE_LIMITED),
            (502, EXIT_UPSTREAM),
        ],
    )
    def test_status_maps_to_exit_code(self, status: int, expected_exit: int) -> None:
        """Status maps to exit code."""
        response = httpx.Response(status, json={"error": "x"})
        with pytest.raises(PortalAPIError) as exc_info:
            raise_for_portal_error(response)
        assert exc_info.value.exit_code == expected_exit


def _mock_client(
    handler: Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> PortalClient:
    return PortalClient(
        base_url="https://portal.example.com",
        token="tok",  # noqa: S106
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_me_sends_bearer_header() -> None:
    """Me sends bearer header."""
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        return httpx.Response(
            200, json={"id": 1, "email": "a@b.com", "full_name": "A", "role": "admin"}
        )

    async with _mock_client(handler) as client:
        profile = await client.me()
    assert seen["auth"] == "Bearer tok"
    assert seen["path"] == "/api/v1/auth/me"
    assert profile["email"] == "a@b.com"


@pytest.mark.asyncio
async def test_list_manifests_parses_envelope() -> None:
    """List manifests parses envelope."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [
                    {
                        "product_id": 1,
                        "product_type": "gough",
                        "manifest": {
                            "manifest_version": 2,
                            "product_type": "gough",
                            "display_name": "Gough",
                            "nav": {"items": []},
                            "resources": [],
                        },
                    }
                ],
                "count": 1,
            },
        )

    async with _mock_client(handler) as client:
        entries = await client.list_manifests()
    assert len(entries) == 1
    assert entries[0].product_type == "gough"


@pytest.mark.asyncio
async def test_list_manifests_error_raises_portal_api_error() -> None:
    """List manifests error raises portal api error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    async with _mock_client(handler) as client:
        with pytest.raises(PortalAPIError):
            await client.list_manifests()


@pytest.mark.asyncio
async def test_proxy_get_builds_correct_url() -> None:
    """Proxy get builds correct url."""
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"nodes": []})

    async with _mock_client(handler) as client:
        await client.proxy_get(7, "api/v1/nodes/")
    assert seen["path"] == "/api/v1/products/7/proxy/api/v1/nodes/"


@pytest.mark.asyncio
async def test_switch_tenant_posts_to_correct_path() -> None:
    """Switch tenant posts to correct path."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tenants/9/switch"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "access_token": "new-tok",
                "tenant": {"id": 9, "slug": "acme", "name": "Acme"},
                "tenant_role": "member",
                "scope": ["products:read"],
            },
        )

    async with _mock_client(handler) as client:
        result = await client.switch_tenant(9)
    assert result["tenant"]["slug"] == "acme"


@pytest.mark.asyncio
async def test_no_token_sends_no_authorization_header() -> None:
    """No token sends no authorization header."""
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"products": [], "count": 0})

    client = PortalClient(
        base_url="https://portal.example.com", transport=httpx.MockTransport(handler)
    )
    async with client:
        await client.list_products()
    assert seen["auth"] is None
