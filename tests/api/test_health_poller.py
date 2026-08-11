"""Async health poller tests (Phase 6 — go-backend replacement).

Covers requirement 5 from the task brief: jittered scheduling (mock clock),
semaphore cap honoured, per-connection isolation, cache TTL, crash-restart
backoff. ``app/health_api.py``'s endpoint/DTO/tenant-scoping coverage lives
in ``test_health_api.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from app import health_poller
from app.adapters.base import HealthResult
from app.adapters.generic_adapter import GenericAdapter
from app.health_cache import get_health
from app.models import get_active_product_connections


def _has_series(metric: Any, connection_id: int, product: str) -> bool:
    """True if `metric` currently reports a sample for this label pair.

    `metric` is a prometheus_client Gauge/Histogram/Counter. Uses
    metric.collect() rather than metric.labels(...), which would create
    the label pair as a side effect of merely checking it.
    """
    wanted = {"connection": str(connection_id), "product": product}
    for family in metric.collect():
        for sample in family.samples:
            if all(sample.labels.get(k) == v for k, v in wanted.items()):
                return True
    return False


async def _register_connection(
    client: Any,
    headers: dict[str, str],
    tenant_id: int,
    product_type: str = "generic",
    **overrides: Any,
) -> dict[str, Any]:
    """Register an active product connection via the real API.

    Goes through the same path a real deployment would (auth, scope,
    validation) rather than inserting a row directly, matching the
    convention in test_products.py.
    """
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "product_type": product_type,
        "display_name": f"Poller Test {product_type}",
        "base_url": "https://example.invalid",
        "auth_type": "none",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/products", headers=headers, json=payload)
    assert response.status_code == 201, f"Failed to register product: {await response.get_json()}"
    body: dict[str, Any] = await response.get_json()
    return body


# -- next_interval: pure, deterministic, mockable clock --------------------


class TestNextInterval:
    """Requirement 5: "jittered scheduling (mock clock)"."""

    def test_default_constants_match_requirement_1(self) -> None:
        """15s base interval, ±20% jitter, 10s per-call timeout, cap 50."""
        assert health_poller.BASE_INTERVAL_SECONDS == 15.0
        assert health_poller.JITTER_FRACTION == 0.2
        assert health_poller.PER_CALL_TIMEOUT_SECONDS == 10.0
        assert health_poller.MAX_CONCURRENT_CHECKS == 50

    def test_low_end_of_jitter_range(self) -> None:
        """rand()==0.0 -> the minimum of the ±20% band."""
        interval = health_poller.next_interval(base=15.0, jitter_fraction=0.2, rand=lambda: 0.0)
        assert interval == pytest.approx(12.0)

    def test_high_end_of_jitter_range(self) -> None:
        """rand()==1.0 -> the maximum of the ±20% band."""
        interval = health_poller.next_interval(base=15.0, jitter_fraction=0.2, rand=lambda: 1.0)
        assert interval == pytest.approx(18.0)

    def test_midpoint_is_the_unjittered_base(self) -> None:
        """rand()==0.5 -> exactly the base interval, no jitter applied."""
        interval = health_poller.next_interval(base=15.0, jitter_fraction=0.2, rand=lambda: 0.5)
        assert interval == pytest.approx(15.0)

    def test_never_escapes_the_jitter_band_across_the_full_input_range(self) -> None:
        """Every rand() in [0, 1] stays inside [base*0.8, base*1.2]."""

        def _fixed(value: float) -> Callable[[], float]:
            return lambda: value

        for hundredth in range(0, 101):
            interval = health_poller.next_interval(
                base=15.0, jitter_fraction=0.2, rand=_fixed(hundredth / 100.0)
            )
            assert 12.0 <= interval <= 18.0


# -- poll_forever: scheduling + crash-restart backoff -----------------------


class TestPollForever:
    """poll_forever owns jittered scheduling AND crash-restart backoff."""

    @pytest.mark.asyncio
    async def test_sweeps_then_sleeps_a_jittered_interval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One run_sweep() call, then one asyncio.sleep() inside the jitter band.

        should_continue is a 2-call-true counter: the loop condition sees
        True once (enters, runs the sweep), the post-sweep check sees True
        once more (so it does not break before sleeping), and the THIRD
        call (the next loop's `while`) sees False and exits — proving the
        sleep actually happened between two sweeps rather than being
        skipped entirely.
        """
        sweep_calls = 0

        async def fake_run_sweep() -> None:
            nonlocal sweep_calls
            sweep_calls += 1

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr(health_poller, "run_sweep", fake_run_sweep)
        monkeypatch.setattr("app.health_poller.asyncio.sleep", fake_sleep)

        continue_calls = 0

        def should_continue() -> bool:
            nonlocal continue_calls
            continue_calls += 1
            return continue_calls <= 2

        await health_poller.poll_forever(should_continue)

        assert sweep_calls == 1
        assert len(sleep_calls) == 1
        assert 12.0 <= sleep_calls[0] <= 18.0

    @pytest.mark.asyncio
    async def test_crash_backoff_doubles_then_resets_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two failures back off 5s then 10s; a third, successful sweep resets."""
        outcomes = [Exception("boom 1"), Exception("boom 2"), None]

        async def fake_run_sweep() -> None:
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr(health_poller, "run_sweep", fake_run_sweep)
        monkeypatch.setattr("app.health_poller.asyncio.sleep", fake_sleep)

        # 4 loop entries: fail, fail, succeed, then stop before a 4th sweep.
        continue_calls = 0

        def should_continue() -> bool:
            nonlocal continue_calls
            continue_calls += 1
            return continue_calls <= 4

        await health_poller.poll_forever(should_continue)

        assert not outcomes, "all three fake sweeps must have run"
        # Backoff after failure 1 (5s), backoff after failure 2 (10s), then
        # the normal jittered interval after the successful third sweep.
        assert sleep_calls[0] == pytest.approx(5.0)
        assert sleep_calls[1] == pytest.approx(10.0)
        assert 12.0 <= sleep_calls[2] <= 18.0

    @pytest.mark.asyncio
    async def test_cancellation_propagates_rather_than_being_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A CancelledError from run_sweep must not be treated as a crash.

        If this were caught by the generic `except Exception` branch, a
        cooperative task.cancel() (BackgroundTaskManager.stop()) would be
        turned into a 5s backoff-and-retry instead of an actual shutdown.
        """

        async def cancelling_sweep() -> None:
            raise asyncio.CancelledError()

        monkeypatch.setattr(health_poller, "run_sweep", cancelling_sweep)

        with pytest.raises(asyncio.CancelledError):
            await health_poller.poll_forever(lambda: True)


# -- run_sweep / _check_one: semaphore cap + per-connection isolation ------


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_checks(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 1: asyncio.Semaphore(50) — proven at a smaller cap.

    Nine connections, cap forced to 3: every health() call increments a
    shared in-flight counter, sleeps briefly (so overlaps are actually
    observable rather than resolving instantly), then decrements. The
    tracked maximum must never exceed the cap.
    """
    monkeypatch.setattr(health_poller, "MAX_CONCURRENT_CHECKS", 3)

    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def tracked_health(self: Any, ctx: Any) -> HealthResult:
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return HealthResult(status="healthy", status_code=200, response_time_ms=1)

    monkeypatch.setattr(GenericAdapter, "health", tracked_health)

    # The free-tier default (DEFAULT_MAX_PRODUCTS=5) would refuse a 9th
    # connection with 403 before the semaphore is ever exercised -- raise
    # this tenant's quota directly rather than asserting anything about
    # billing tiers, which is not what this test is about.
    from app.models import get_db

    async with app.app_context():
        db = get_db()
        await db(db.tenants.id == tenant_id).update(max_products=20)
        await db.commit()

    for _ in range(9):
        await _register_connection(client, admin_headers, tenant_id)

    async with app.app_context():
        await health_poller.run_sweep()

    assert max_in_flight == 3, f"observed concurrency {max_in_flight}, cap was 3"


@pytest.mark.asyncio
async def test_one_connections_failure_does_not_affect_another(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
) -> None:
    """Requirement 4: "one connection's failure never affects others".

    waddleai is a valid PRODUCT_TYPES entry with no ADAPTER_REGISTRY entry
    (get_adapter raises ValueError), sitting in the same sweep as a
    healthy generic connection.
    """
    broken = await _register_connection(client, admin_headers, tenant_id, product_type="waddleai")
    healthy = await _register_connection(client, admin_headers, tenant_id, product_type="generic")

    async with app.app_context():
        await health_poller.run_sweep()

        broken_entry = await get_health(int(broken["id"]))
        healthy_entry = await get_health(int(healthy["id"]))

    assert broken_entry is not None
    assert broken_entry.status == "unhealthy"
    assert broken_entry.error is not None and "waddleai" in broken_entry.error

    # generic's real health() hits transport against an unreachable
    # https://example.invalid base_url, so it also reports unhealthy --
    # the point of this assertion is that it got a DISTINCT, independently
    # recorded outcome at all, not that it timed out cleanly.
    assert healthy_entry is not None


@pytest.mark.asyncio
async def test_healthy_result_is_cached_and_gauge_reports_one(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely healthy poll is cached verbatim and sets the gauge to 1."""

    async def healthy(self: Any, ctx: Any) -> HealthResult:
        return HealthResult(status="healthy", status_code=200, response_time_ms=42)

    monkeypatch.setattr(GenericAdapter, "health", healthy)

    conn = await _register_connection(client, admin_headers, tenant_id)

    async with app.app_context():
        await health_poller.run_sweep()
        entry = await get_health(int(conn["id"]))

    assert entry is not None
    assert entry.status == "healthy"
    assert entry.latency_ms == 42
    assert entry.error is None

    gauge_value = health_poller.PRODUCT_HEALTH_GAUGE.labels(
        connection=str(conn["id"]), product="generic"
    )._value.get()
    assert gauge_value == 1.0


@pytest.mark.asyncio
async def test_poll_error_increments_the_error_counter(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
) -> None:
    """Requirement 2: "counter poll errors" — only for a raised/timed-out check."""
    conn = await _register_connection(client, admin_headers, tenant_id, product_type="waddleai")

    before = health_poller.POLL_ERRORS_COUNTER.labels(
        connection=str(conn["id"]), product="waddleai"
    )._value.get()

    async with app.app_context():
        await health_poller.run_sweep()

    after = health_poller.POLL_ERRORS_COUNTER.labels(
        connection=str(conn["id"]), product="waddleai"
    )._value.get()

    assert after == before + 1


@pytest.mark.asyncio
async def test_per_call_timeout_is_enforced(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hanging adapter.health() is cut off at PER_CALL_TIMEOUT_SECONDS.

    Forces the timeout down to something a test can actually wait for
    rather than sleeping the real 10s.
    """
    monkeypatch.setattr(health_poller, "PER_CALL_TIMEOUT_SECONDS", 0.05)

    async def hangs_forever(self: Any, ctx: Any) -> HealthResult:
        await asyncio.sleep(10)
        raise AssertionError("should have been cancelled by the timeout")

    monkeypatch.setattr(GenericAdapter, "health", hangs_forever)

    conn = await _register_connection(client, admin_headers, tenant_id)

    async with app.app_context():
        await asyncio.wait_for(health_poller.run_sweep(), timeout=5.0)
        entry = await get_health(int(conn["id"]))

    assert entry is not None
    assert entry.status == "unhealthy"
    assert entry.error is not None


@pytest.mark.asyncio
async def test_deactivated_connection_is_not_polled(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
) -> None:
    """is_active is honoured: a deactivated connection stops being swept.

    Regression for the "no kill-switch resurrection" concern raised
    during design: the poller must not resurrect a deactivated
    connection's health status.
    """
    conn = await _register_connection(client, admin_headers, tenant_id)

    response = await client.put(
        f"/api/v1/products/{conn['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    async with app.app_context():
        connections = await get_active_product_connections()

    assert all(int(c["id"]) != int(conn["id"]) for c in connections)


@pytest.mark.asyncio
async def test_stale_connection_releases_its_metric_series(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix wave 1 (I3): a connection leaving the active set loses its series.

    Without this, a deleted/deactivated connection's gauge/histogram
    series keep reporting their LAST value forever -- an alert on
    portal_product_health == 0 would fire indefinitely for a connection
    an operator already removed.
    """

    async def healthy(self: Any, ctx: Any) -> HealthResult:
        return HealthResult(status="healthy", status_code=200, response_time_ms=5)

    monkeypatch.setattr(GenericAdapter, "health", healthy)

    conn = await _register_connection(client, admin_headers, tenant_id)
    connection_id = int(conn["id"])

    async with app.app_context():
        await health_poller.run_sweep()

    assert _has_series(health_poller.PRODUCT_HEALTH_GAUGE, connection_id, "generic")
    assert _has_series(health_poller.POLL_LATENCY_HISTOGRAM, connection_id, "generic")

    response = await client.put(
        f"/api/v1/products/{connection_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    async with app.app_context():
        await health_poller.run_sweep()

    assert not _has_series(health_poller.PRODUCT_HEALTH_GAUGE, connection_id, "generic")
    assert not _has_series(health_poller.POLL_LATENCY_HISTOGRAM, connection_id, "generic")


@pytest.mark.asyncio
async def test_deleted_connection_releases_its_metric_series(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same as above, for an outright DELETE rather than is_active=False."""

    async def healthy(self: Any, ctx: Any) -> HealthResult:
        return HealthResult(status="healthy", status_code=200, response_time_ms=5)

    monkeypatch.setattr(GenericAdapter, "health", healthy)

    conn = await _register_connection(client, admin_headers, tenant_id)
    connection_id = int(conn["id"])

    async with app.app_context():
        await health_poller.run_sweep()

    assert _has_series(health_poller.PRODUCT_HEALTH_GAUGE, connection_id, "generic")

    response = await client.delete(f"/api/v1/products/{connection_id}", headers=admin_headers)
    assert response.status_code == 200

    async with app.app_context():
        await health_poller.run_sweep()

    assert not _has_series(health_poller.PRODUCT_HEALTH_GAUGE, connection_id, "generic")
