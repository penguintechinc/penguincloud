"""Tests for `pcli.session` -- load/refresh-if-expired credential resolution."""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from pcli.auth.keyring_store import TokenStore
from pcli.auth.tokens import TokenSet
from pcli.config import build_config
from pcli.errors import AuthenticationRequiredError
from pcli.session import ensure_valid_token


def _valid_token() -> TokenSet:
    return TokenSet(
        access_token="valid",  # noqa: S106
        refresh_token="refresh",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=time.time() + 3600,
    )


def _expired_token() -> TokenSet:
    return TokenSet(
        access_token="expired",  # noqa: S106
        refresh_token="refresh",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=time.time() - 10,
    )


_RealAsyncClient = httpx.AsyncClient


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> None:
    """Redirect every `httpx.AsyncClient(...)` `session._refresh` builds to a mock transport.

    `session._refresh` constructs its own `httpx.AsyncClient` inline (no
    injectable `transport` parameter, unlike `PortalClient`) -- captures
    the REAL class before patching so the factory below does not recurse
    into itself.
    """

    def factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_no_stored_token_raises_authentication_required(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No stored token raises authentication required."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    config = build_config(portal_url="https://portal.example.com", output="json")
    with pytest.raises(AuthenticationRequiredError):
        await ensure_valid_token(config)


@pytest.mark.asyncio
async def test_valid_token_returned_without_refresh_call(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid token returned without refresh call."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    config = build_config(portal_url="https://portal.example.com", output="json")
    store = TokenStore(config.host_key)
    store.save(_valid_token())

    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("must not call refresh for a still-valid token")

    _patch_async_client(monkeypatch, handler)

    tokens = await ensure_valid_token(config)
    assert tokens.access_token == "valid"
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_persisted(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired token is refreshed and persisted."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    config = build_config(portal_url="https://portal.example.com", output="json")
    store = TokenStore(config.host_key)
    store.save(_expired_token())

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/refresh"
        body = request.content
        assert b"refresh" in body
        return httpx.Response(
            200,
            json={
                "access_token": "refreshed",
                "refresh_token": "new-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    _patch_async_client(monkeypatch, handler)

    tokens = await ensure_valid_token(config)
    assert tokens.access_token == "refreshed"

    reloaded = store.load()
    assert reloaded is not None
    assert reloaded.access_token == "refreshed"


@pytest.mark.asyncio
async def test_expired_token_with_failed_refresh_raises_authentication_required(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired token with failed refresh raises authentication required."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    config = build_config(portal_url="https://portal.example.com", output="json")
    store = TokenStore(config.host_key)
    store.save(_expired_token())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid refresh token"})

    _patch_async_client(monkeypatch, handler)

    with pytest.raises(AuthenticationRequiredError):
        await ensure_valid_token(config)


@pytest.mark.asyncio
async def test_expired_token_with_no_refresh_token_raises_authentication_required(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired token with no refresh token raises authentication required."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    config = build_config(portal_url="https://portal.example.com", output="json")
    store = TokenStore(config.host_key)
    store.save(
        TokenSet(
            access_token="expired",  # noqa: S106
            refresh_token="",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            expires_at=time.time() - 10,
        )
    )
    with pytest.raises(AuthenticationRequiredError):
        await ensure_valid_token(config)


@pytest.mark.asyncio
async def test_pcli_token_env_is_always_treated_as_valid(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pcli token env is always treated as valid."""
    monkeypatch.setenv("PCLI_TOKEN", "ci-token")
    config = build_config(portal_url="https://portal.example.com", output="json")
    tokens = await ensure_valid_token(config)
    assert tokens.access_token == "ci-token"
