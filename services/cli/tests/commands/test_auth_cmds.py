"""Tests for `pcli login` / `logout` / `whoami`."""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from pcli.auth.keyring_store import TokenStore
from pcli.auth.tokens import TokenSet
from pcli.cli import cli


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> None:
    real_async_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_login_device_flow_success(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Login device flow success."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)

    call_order: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/device/authorize":
            call_order.append("authorize")
            return httpx.Response(
                200,
                json={
                    "device_code": "dc",
                    "user_code": "AB12-CD34",
                    "verification_uri": "https://portal.example.com/device",
                    "verification_uri_complete": "https://portal.example.com/device?user_code=AB12-CD34",
                    "expires_in": 600,
                    "interval": 0,
                },
            )
        assert request.url.path == "/api/v1/auth/device/token"
        call_order.append("token")
        return httpx.Response(
            200,
            json={
                "access_token": "final-token",
                "refresh_token": "final-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    _patch_async_client(monkeypatch, handler)

    runner = CliRunner()
    result = runner.invoke(cli, ["--portal-url", "https://portal.example.com", "login"])
    assert result.exit_code == 0, result.output
    assert "AB12-CD34" in result.output
    assert call_order == ["authorize", "token"]

    stored = TokenStore("portal.example.com").load()
    assert stored is not None
    assert stored.access_token == "final-token"


def test_login_never_logs_the_device_code_or_user_code_secrets(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`device_code` (the actual bearer-equivalent secret) must never print."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/device/authorize":
            return httpx.Response(
                200,
                json={
                    "device_code": "super-secret-device-code",
                    "user_code": "AB12-CD34",
                    "verification_uri": "https://portal.example.com/device",
                    "verification_uri_complete": "https://portal.example.com/device?user_code=AB12-CD34",
                    "expires_in": 600,
                    "interval": 0,
                },
            )
        return httpx.Response(
            200,
            json={
                "access_token": "tok",
                "refresh_token": "ref",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(cli, ["--portal-url", "https://portal.example.com", "login"])
    assert "super-secret-device-code" not in result.output
    assert "tok" not in result.output  # the minted access token, also never echoed


def test_logout_clears_stored_token(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Logout clears stored token."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    store.save(
        TokenSet(
            access_token="tok",  # noqa: S106
            refresh_token="ref",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            expires_at=time.time() + 3600,
        )
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--portal-url", "https://portal.example.com", "logout"])
    assert result.exit_code == 0
    assert store.load() is None


def test_whoami_reports_profile_and_tenant(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whoami reports profile and tenant."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    from pcli.auth.tokens import TenantContext

    store = TokenStore("portal.example.com")
    store.save(
        TokenSet(
            access_token="tok",  # noqa: S106
            refresh_token="ref",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            expires_at=time.time() + 3600,
            tenant=TenantContext(id=9, slug="acme", name="Acme"),
            scope=("products:read",),
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/me"
        return httpx.Response(
            200,
            json={
                "id": 1,
                "email": "a@b.com",
                "full_name": "A B",
                "role": "admin",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "whoami", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert '"email": "a@b.com"' in result.output
    assert '"slug": "acme"' in result.output


def test_whoami_without_login_reports_authentication_required(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whoami without login reports authentication required."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    from pcli.cli import main

    monkeypatch.setattr(
        "sys.argv", ["pcli", "--portal-url", "https://portal.example.com", "whoami"]
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2  # EXIT_UNAUTHENTICATED
