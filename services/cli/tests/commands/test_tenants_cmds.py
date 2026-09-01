"""Tests for `pcli tenants list` / `pcli tenants use`."""

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


def _logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    TokenStore("portal.example.com").save(
        TokenSet(
            access_token="tok",  # noqa: S106
            refresh_token="ref",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            expires_at=time.time() + 3600,
        )
    )


def test_tenants_list(fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenants list."""
    _logged_in(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tenants"
        return httpx.Response(
            200,
            json={"tenants": [{"id": 1, "name": "Acme", "plan": "free"}], "count": 1},
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "tenants", "list", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert '"name": "Acme"' in result.output


def test_tenants_use_by_slug_persists_new_token(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tenants use by slug persists new token."""
    _logged_in(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tenants":
            return httpx.Response(
                200,
                json={
                    "tenants": [
                        {"id": 1, "slug": "acme", "name": "Acme", "plan": "free"},
                        {"id": 2, "slug": "widgetco", "name": "WidgetCo", "plan": "free"},
                    ],
                    "count": 2,
                },
            )
        assert request.url.path == "/api/v1/tenants/2/switch"
        return httpx.Response(
            200,
            json={
                "access_token": "new-scoped-token",
                "tenant": {"id": 2, "slug": "widgetco", "name": "WidgetCo"},
                "tenant_role": "member",
                "scope": ["products:read"],
            },
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "tenants", "use", "widgetco"]
    )
    assert result.exit_code == 0, result.output
    assert "WidgetCo" in result.output

    stored = TokenStore("portal.example.com").load()
    assert stored is not None
    assert stored.access_token == "new-scoped-token"
    assert stored.tenant is not None
    assert stored.tenant.slug == "widgetco"
    # The prior refresh_token survives the switch -- TenantSwitchResponse
    # carries none of its own.
    assert stored.refresh_token == "ref"


def test_tenants_use_by_numeric_id(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tenants use by numeric id."""
    _logged_in(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tenants":
            return httpx.Response(
                200,
                json={
                    "tenants": [{"id": 7, "slug": "acme", "name": "Acme", "plan": "free"}],
                    "count": 1,
                },
            )
        assert request.url.path == "/api/v1/tenants/7/switch"
        return httpx.Response(
            200,
            json={
                "access_token": "tok2",
                "tenant": {"id": 7, "slug": "acme", "name": "Acme"},
                "tenant_role": "owner",
                "scope": [],
            },
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "tenants", "use", "7"]
    )
    assert result.exit_code == 0, result.output


def test_tenants_use_unknown_tenant_exits_not_found(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tenants use unknown tenant exits not found."""
    _logged_in(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tenants": [], "count": 0})

    _patch_async_client(monkeypatch, handler)
    from pcli.cli import main
    from pcli.exit_codes import EXIT_NOT_FOUND

    monkeypatch.setattr(
        "sys.argv",
        ["pcli", "--portal-url", "https://portal.example.com", "tenants", "use", "ghost"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == EXIT_NOT_FOUND
