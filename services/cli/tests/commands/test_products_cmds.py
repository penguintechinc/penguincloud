"""Tests for `pcli products list`."""

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


def test_products_list_sources_from_console_manifests(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Products list sources from console manifests."""
    _logged_in(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/console/manifests"
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
                            "resources": [
                                {
                                    "kind": "nodes",
                                    "label": "Node",
                                    "plural_label": "Nodes",
                                    "id_field": "id",
                                    "name_field": "name",
                                    "transport": "typed",
                                    "empty_state": "",
                                    "error_state": "",
                                    "columns": [],
                                    "list": None,
                                    "item_path": None,
                                }
                            ],
                        },
                    }
                ],
                "count": 1,
            },
        )

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "products", "list", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert '"product_type": "gough"' in result.output
    assert '"nodes"' in result.output


def test_products_list_without_login_fails_with_exit_2(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Products list without login fails with exit 2."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    from pcli.cli import main

    monkeypatch.setattr(
        "sys.argv",
        ["pcli", "--portal-url", "https://portal.example.com", "products", "list"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
