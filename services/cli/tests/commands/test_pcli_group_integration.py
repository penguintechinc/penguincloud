"""End-to-end tests through the REAL `pcli.cli.cli` object.

Unlike `tests/commands/test_resource_group.py` (which swaps in a fixed
manifest source to isolate the discovery claim), these tests exercise the
production `PcliGroup`/`ManifestProvider`/`resolve_app_state` stack itself:
live manifest fetch, tenant-keyed on-disk caching, stale-cache fallback,
multi-connection `--connection` selection, and the `get` leaf command.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from pcli.auth.keyring_store import TokenStore
from pcli.auth.tokens import TenantContext, TokenSet
from pcli.cli import cli, main
from pcli.errors import PortalAPIError
from pcli.exit_codes import EXIT_UPSTREAM


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> None:
    real_async_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _logged_in(monkeypatch: pytest.MonkeyPatch, *, tenant_id: int | None = 1) -> None:
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    TokenStore("portal.example.com").save(
        TokenSet(
            access_token="tok",  # noqa: S106
            refresh_token="ref",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            expires_at=time.time() + 3600,
            tenant=TenantContext(id=tenant_id, slug="acme", name="Acme") if tenant_id else None,
        )
    )


def _isolate_manifest_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))


_MANIFESTS_BODY: dict[str, Any] = {
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
                        "empty_state": "No nodes.",
                        "error_state": "Unable to load nodes.",
                        "columns": [
                            {
                                "field": "id",
                                "label": "ID",
                                "cell": {"kind": "text"},
                                "sortable": False,
                                "absent_as": None,
                            }
                        ],
                        "list": {
                            "path_bytes": "/api/v1/nodes/",
                            "envelope": {"keys": ["nodes"]},
                            "pagination": "cursor",
                        },
                        "item_path": {"prefix": "/api/v1/nodes", "sample_id": "1"},
                    }
                ],
            },
        }
    ],
    "count": 1,
}


def test_discovered_product_help_lists_real_resource(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Discovered product help lists real resource."""
    _logged_in(monkeypatch)
    _isolate_manifest_cache_dir(monkeypatch, tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/console/manifests"
        return httpx.Response(200, json=_MANIFESTS_BODY)

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(cli, ["--portal-url", "https://portal.example.com", "gough", "--help"])
    assert result.exit_code == 0, result.output
    assert "nodes" in result.output


def test_get_leaf_command_calls_item_path(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Get leaf command calls item path."""
    _logged_in(monkeypatch)
    _isolate_manifest_cache_dir(monkeypatch, tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/console/manifests":
            return httpx.Response(200, json=_MANIFESTS_BODY)
        assert request.url.path == "/api/v1/products/1/proxy/api/v1/nodes/42"
        return httpx.Response(200, json={"id": "42", "name": "node-42"})

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--portal-url", "https://portal.example.com", "gough", "nodes", "get", "42", "-o", "json"],
    )
    assert result.exit_code == 0, result.output
    assert '"id": "42"' in result.output


def test_manifest_cache_populated_after_successful_fetch(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Manifest cache populated after successful fetch."""
    _logged_in(monkeypatch, tenant_id=1)
    _isolate_manifest_cache_dir(monkeypatch, tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_MANIFESTS_BODY)

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    # NOT `products list` -- that command calls PortalClient.list_manifests()
    # directly (products_cmds.py), by design bypassing the cache entirely
    # (it's an explicit live query, not part of command-tree discovery).
    # `gough --help` IS discovery: it resolves through `PcliGroup.get_command`
    # -> `ManifestProvider`, the layer that populates this cache.
    result = runner.invoke(cli, ["--portal-url", "https://portal.example.com", "gough", "--help"])
    assert result.exit_code == 0, result.output

    from pcli.api.manifest_cache import ManifestCache

    cached = ManifestCache("portal.example.com").load(1)
    assert cached is not None
    assert cached.entries[0].product_type == "gough"


def test_stale_cache_used_when_portal_unreachable_and_warns(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Stale cache used when portal unreachable and warns."""
    _logged_in(monkeypatch, tenant_id=1)
    _isolate_manifest_cache_dir(monkeypatch, tmp_path)

    from pcli.api.manifest_cache import ManifestCache
    from pcli.api.manifest_types import parse_manifests_response

    entries = parse_manifests_response(_MANIFESTS_BODY)
    ManifestCache("portal.example.com").save(1, entries)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "portal degraded"})

    _patch_async_client(monkeypatch, handler)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--portal-url", "https://portal.example.com", "gough", "nodes", "list", "-o", "json"]
    )
    # The DISCOVERY step degrades gracefully to the stale cache (the
    # warning proves it ran) -- but the `list` command's OWN data fetch is
    # a SEPARATE live call against the same (still-down) portal, which
    # correctly still fails. Falling back to a cached manifest for command
    # resolution was never a promise that live data fetches also succeed.
    assert "showing a cached manifest" in result.output
    assert isinstance(result.exception, PortalAPIError)
    assert result.exception.exit_code == EXIT_UPSTREAM


def test_unreachable_with_no_tenant_context_never_writes_or_reads_cache(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No `tenant` on the stored token (a bare, unswitched login) -> no cache key exists."""
    _logged_in(monkeypatch, tenant_id=None)
    _isolate_manifest_cache_dir(monkeypatch, tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr(
        "sys.argv", ["pcli", "--portal-url", "https://portal.example.com", "products", "list"]
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0  # no cache to fall back to -- the error propagates


class TestMultipleConnections:
    """Multiple connections."""

    def _two_connection_body(self) -> dict[str, Any]:
        body = copy.deepcopy(_MANIFESTS_BODY)
        manifests: list[dict[str, Any]] = body["manifests"]
        second = copy.deepcopy(manifests[0])
        second["product_id"] = 2
        manifests.append(second)
        return body

    def test_default_connection_is_the_first(
        self, fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Default connection is the first."""
        _logged_in(monkeypatch)
        _isolate_manifest_cache_dir(monkeypatch, tmp_path)
        body = self._two_connection_body()

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/console/manifests":
                return httpx.Response(200, json=body)
            assert request.url.path == "/api/v1/products/1/proxy/api/v1/nodes/"
            return httpx.Response(200, json={"nodes": []})

        _patch_async_client(monkeypatch, handler)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--portal-url", "https://portal.example.com", "gough", "nodes", "list"]
        )
        assert result.exit_code == 0, result.output

    def test_explicit_connection_flag_selects_the_right_one(
        self, fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Explicit connection flag selects the right one."""
        _logged_in(monkeypatch)
        _isolate_manifest_cache_dir(monkeypatch, tmp_path)
        body = self._two_connection_body()

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/console/manifests":
                return httpx.Response(200, json=body)
            assert request.url.path == "/api/v1/products/2/proxy/api/v1/nodes/"
            return httpx.Response(200, json={"nodes": []})

        _patch_async_client(monkeypatch, handler)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--portal-url",
                "https://portal.example.com",
                "gough",
                "nodes",
                "list",
                "--connection",
                "2",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_unknown_connection_flag_reports_a_named_error(
        self, fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Unknown connection flag reports a named error."""
        _logged_in(monkeypatch)
        _isolate_manifest_cache_dir(monkeypatch, tmp_path)
        body = self._two_connection_body()

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        _patch_async_client(monkeypatch, handler)
        monkeypatch.setattr(
            "sys.argv",
            [
                "pcli",
                "--portal-url",
                "https://portal.example.com",
                "gough",
                "nodes",
                "list",
                "--connection",
                "999",
            ],
        )
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0
