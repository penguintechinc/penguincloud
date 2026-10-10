"""app.health_cache exception-handling branches test_health_cache.py doesn't reach.

Requirement 4 ("poller survives Redis outages") extends past a refused TCP
connection (already covered) to: no app context at all, the penguin_dal
Valkey wrapper missing, the underlying valkey client library missing, an
exception during client construction itself, and a failure closing the
shared connection at shutdown. Every one of these must degrade to the
local fallback (or a clean no-op), never raise.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from app import health_cache


class TestTtlOutsideAppContext:
    """Ttl Outside App Context."""

    def test_no_app_context_falls_back_to_the_module_default(self) -> None:
        # Deliberately NOT inside `async with app.app_context()` --
        # current_app access raises RuntimeError, which _ttl_seconds catches.
        """No app context falls back to the module default."""
        assert health_cache._ttl_seconds() == health_cache._DEFAULT_TTL_SECONDS


class TestGetCacheClientImportFailures:
    """Get Cache Client Import Failures."""

    @pytest.mark.asyncio
    async def test_penguin_dal_valkey_wrapper_missing(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`from penguin_dal.cache.valkey import ...` itself fails."""
        monkeypatch.setitem(sys.modules, "penguin_dal.cache.valkey", None)

        async with app.app_context():
            app.config["CACHE_HOST"] = "valkey.example.internal"
            health_cache.reset_cache_client_for_tests()
            client = await health_cache._get_cache_client()

        assert client is None

    @pytest.mark.asyncio
    async def test_valkey_client_library_missing_during_construction(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AsyncValkeyCache() itself raises ImportError during construction.

        penguin_dal.cache.valkey imports fine, but AsyncValkeyCache's own
        __init__ imports valkey.asyncio directly.
        """
        from penguin_dal.cache import valkey as valkey_module

        def _boom(*args: Any, **kwargs: Any) -> Any:
            """Boom."""
            raise ImportError("valkey.asyncio not installed")

        monkeypatch.setattr(valkey_module, "AsyncValkeyCache", _boom)

        async with app.app_context():
            app.config["CACHE_HOST"] = "valkey.example.internal"
            health_cache.reset_cache_client_for_tests()
            client = await health_cache._get_cache_client()

        assert client is None


class TestSetAndGetHealthClientInitExceptions:
    """Set And Get Health Client Init Exceptions."""

    @pytest.mark.asyncio
    async def test_set_health_swallows_a_client_init_exception(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Set health swallows a client init exception."""

        async def _boom() -> Any:
            """Boom."""
            raise RuntimeError("cache backend exploded")

        monkeypatch.setattr(health_cache, "_get_cache_client", _boom)

        async with app.app_context():
            entry = health_cache.CachedHealth(
                status="healthy", latency_ms=1, checked_at="2026-01-01T00:00:00+00:00", error=None
            )
            await health_cache.set_health(505, entry)  # must not raise

            # The in-process fallback still recorded it (written before the
            # cache-client attempt).
            got = await health_cache.get_health(505)
        assert got == entry

    @pytest.mark.asyncio
    async def test_get_health_falls_back_locally_on_client_init_exception(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Get health falls back locally on client init exception."""
        entry = health_cache.CachedHealth(
            status="degraded", latency_ms=9, checked_at="2026-01-01T00:00:00+00:00", error=None
        )

        async with app.app_context():
            health_cache._remember_locally(606, entry, 60)

            async def _boom() -> Any:
                """Boom."""
                raise RuntimeError("cache backend exploded")

            monkeypatch.setattr(health_cache, "_get_cache_client", _boom)

            got = await health_cache.get_health(606)

        assert got == entry


class TestCloseCacheClient:
    """Close Cache Client."""

    @pytest.mark.asyncio
    async def test_close_swallows_an_exception_from_the_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Close swallows an exception from the client."""

        class _FakeClient:
            """Fake Client."""

            async def close(self) -> None:
                """Close."""
                raise RuntimeError("connection already gone")

        monkeypatch.setattr(health_cache, "_cache_client", _FakeClient())
        monkeypatch.setattr(health_cache, "_cache_init_attempted", True)

        await health_cache.close_cache_client()  # must not raise

        assert health_cache._cache_client is None
        assert health_cache._cache_init_attempted is False

    @pytest.mark.asyncio
    async def test_close_with_no_client_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Close with no client is a noop."""
        monkeypatch.setattr(health_cache, "_cache_client", None)
        await health_cache.close_cache_client()  # must not raise
