"""app.health_cache — Valkey-backed store with an in-process fallback.

Requirement 1: TTL 60s, key `health:{connection_id}`. Requirement 4:
"poller survives Redis outages (degrades to in-memory last-known)".
"""

from __future__ import annotations

from typing import Any

import pytest
from app import health_cache
from app.health_cache import CachedHealth, get_health, set_health


def _entry(status: str = "healthy") -> CachedHealth:
    return CachedHealth(
        status=status, latency_ms=12, checked_at="2026-01-01T00:00:00+00:00", error=None
    )


@pytest.mark.asyncio
async def test_round_trip_without_any_cache_backend_configured(app: Any) -> None:
    """TestingConfig leaves CACHE_HOST unset -- local fallback carries it alone."""
    async with app.app_context():
        assert app.config.get("CACHE_HOST", "") == ""

        await set_health(101, _entry())
        got = await get_health(101)

    assert got == _entry()


@pytest.mark.asyncio
async def test_unknown_connection_returns_none(app: Any) -> None:
    """A connection id nothing ever cached reads back as None, not an error."""
    async with app.app_context():
        got = await get_health(999999)
    assert got is None


@pytest.mark.asyncio
async def test_key_prefix_matches_the_requirement(app: Any) -> None:
    """Requirement 1: cache key is `health:{connection_id}`."""
    assert health_cache._cache_key(42) == "health:42"


@pytest.mark.asyncio
async def test_default_ttl_is_60_seconds() -> None:
    """Requirement 1: cache entries default to a 60s TTL."""
    assert health_cache._DEFAULT_TTL_SECONDS == 60


@pytest.mark.asyncio
async def test_local_fallback_expires_after_the_configured_ttl(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A value written with a short TTL is gone once that TTL elapses.

    Uses a fake monotonic clock rather than a real sleep so the test is
    fast and deterministic.
    """
    fake_now = {"t": 1000.0}
    monkeypatch.setattr("app.health_cache.time.monotonic", lambda: fake_now["t"])

    async with app.app_context():
        app.config["HEALTH_POLL_CACHE_TTL_SECONDS"] = 10
        await set_health(202, _entry())

        # Still inside the window.
        fake_now["t"] += 9.0
        assert await get_health(202) == _entry()

        # Past it.
        fake_now["t"] += 2.0
        assert await get_health(202) is None


@pytest.mark.asyncio
async def test_unreachable_cache_host_degrades_to_local_last_known(
    app: Any,
) -> None:
    """Requirement 4: a Valkey outage must not lose the value or crash.

    Points CACHE_HOST at a real TCP port nothing listens on (an
    OS-refused connection is fast, not a multi-second timeout) rather than
    mocking the client internals, so this proves the ACTUAL failure path,
    not a stand-in for it.
    """
    async with app.app_context():
        app.config["CACHE_HOST"] = "127.0.0.1"
        app.config["CACHE_PORT"] = 1  # nothing listens on port 1

        await set_health(303, _entry("unhealthy"))
        got = await get_health(303)

    assert got == _entry("unhealthy")


@pytest.mark.asyncio
async def test_cache_client_init_is_memoised_per_process(app: Any) -> None:
    """The client (or the "nothing configured" None) is built at most once.

    CACHE_HOST is unset in TestingConfig, so this proves the "no shared
    cache available" branch short-circuits on the second call rather than
    re-evaluating config every time.
    """
    async with app.app_context():
        first = await health_cache._get_cache_client()
        assert health_cache._cache_init_attempted is True
        second = await health_cache._get_cache_client()

    assert first is None
    assert second is None


@pytest.mark.asyncio
async def test_corrupt_cached_payload_is_treated_as_a_miss(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed cache entry must not raise out of get_health.

    Simulates a shared-store hit with an unparseable payload by installing
    a fake client directly -- the one path _get_cache_client's own
    construction logic cannot reach in the test venv (CACHE_HOST unset).
    """

    class _FakeClient:
        async def get(self, key: str) -> bytes:
            return b"not-json{{"

        async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
            raise AssertionError("not exercised in this test")

    monkeypatch.setattr(health_cache, "_cache_client", _FakeClient())
    monkeypatch.setattr(health_cache, "_cache_init_attempted", True)

    async with app.app_context():
        got = await get_health(404)

    assert got is None


class TestLogStartupState:
    """Fix wave 1 (I4): the CACHE_HOST-unset degradation must be unmistakable."""

    def test_warns_with_the_actual_consequence_when_cache_host_unset(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Names what breaks (cross-worker sharing), not just a state label."""
        with caplog.at_level("WARNING", logger="app.health_cache"):
            health_cache.log_startup_state({"CACHE_HOST": ""})

        assert len(caplog.records) == 1
        message = caplog.records[0].message
        assert caplog.records[0].levelname == "WARNING"
        assert "NOT shared across workers or replicas" in message
        # The whole point: REDIS_URL looking like it should be enough is
        # the trap this warning exists to prevent (docker-compose.yml sets
        # it; this module does not read it).
        assert "REDIS_URL" in message

    def test_no_warning_when_cache_host_is_configured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A configured CACHE_HOST logs informational confirmation, not a warning."""
        with caplog.at_level("INFO", logger="app.health_cache"):
            health_cache.log_startup_state({"CACHE_HOST": "valkey.example.internal"})

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "INFO"
