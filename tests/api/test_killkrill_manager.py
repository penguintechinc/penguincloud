"""Unit tests for app.killkrill's KillKrillManager singleton and helpers.

Previously untested (0 references to KillKrillManager/track_* anywhere in
tests/api) despite being 41% covered by incidental use through the app
lifespan. conftest.py's autouse `_reset_killkrill_manager` fixture resets
the singleton's enabled/client/queues after every test, so each test here
starts from a clean disabled state regardless of execution order.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.killkrill import (
    KillKrillManager,
    killkrill_manager,
    track_api_request,
    track_feature_usage,
    track_user_action,
)


class TestSingleton:
    """Singleton."""

    def test_constructor_always_returns_the_process_wide_instance(self) -> None:
        """Constructor always returns the process wide instance."""
        assert KillKrillManager() is killkrill_manager
        assert KillKrillManager() is KillKrillManager()


class TestSetup:
    """Setup."""

    def test_disabled_leaves_client_unset(self) -> None:
        """Disabled leaves client unset."""
        killkrill_manager.setup("https://a", "b:50051", "cid", "sec", enabled=False)
        assert killkrill_manager.enabled is False
        assert killkrill_manager.client is None

    def test_enabled_builds_a_receiver_client(self) -> None:
        """Enabled builds a receiver client."""
        killkrill_manager.setup("https://a", "b:50051", "cid", "sec", enabled=True)
        assert killkrill_manager.enabled is True
        assert killkrill_manager.client is not None

    def test_construction_failure_disables_and_swallows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Construction failure disables and swallows."""

        def _boom(*a: Any, **k: Any) -> Any:
            """Boom."""
            raise RuntimeError("bad config")

        monkeypatch.setattr("app.killkrill_client.ReceiverClient", _boom)
        killkrill_manager.setup("https://a", "b:50051", "cid", "sec", enabled=True)
        assert killkrill_manager.enabled is False


class TestLog:
    """Log."""

    def test_disabled_does_not_queue(self) -> None:
        """Disabled does not queue."""
        killkrill_manager.enabled = False
        killkrill_manager.client = MagicMock()
        killkrill_manager.log("info", "hello")
        assert killkrill_manager._log_queue == []

    def test_no_client_does_not_queue(self) -> None:
        """No client does not queue."""
        killkrill_manager.enabled = True
        killkrill_manager.client = None
        killkrill_manager.log("info", "hello")
        assert killkrill_manager._log_queue == []

    def test_enabled_with_client_queues_ecs_entry(self) -> None:
        """Enabled with client queues ecs entry."""
        killkrill_manager.enabled = True
        killkrill_manager.client = MagicMock()
        killkrill_manager.log("warning", "disk low", host="node-1")

        assert len(killkrill_manager._log_queue) == 1
        entry = killkrill_manager._log_queue[0]
        assert entry["log.level"] == "WARNING"
        assert entry["message"] == "disk low"
        assert entry["service.name"] == "portal-api"
        assert entry["host"] == "node-1"
        assert "@timestamp" in entry

    def test_internal_failure_is_caught_not_raised(self) -> None:
        """Internal failure is caught not raised."""
        killkrill_manager.enabled = True
        killkrill_manager.client = MagicMock()

        class _RaisingList(list[Any]):
            """Raising List."""

            def append(self, *a: Any, **k: Any) -> None:
                """Append."""
                raise RuntimeError("queue full")

        killkrill_manager._log_queue = _RaisingList()
        killkrill_manager.log("info", "hello")  # must not raise


class TestMetric:
    """Metric."""

    def test_disabled_does_not_queue(self) -> None:
        """Disabled does not queue."""
        killkrill_manager.enabled = False
        killkrill_manager.client = MagicMock()
        killkrill_manager.metric("x", 1.0)
        assert killkrill_manager._metric_queue == []

    def test_no_client_does_not_queue(self) -> None:
        """No client does not queue."""
        killkrill_manager.enabled = True
        killkrill_manager.client = None
        killkrill_manager.metric("x", 1.0)
        assert killkrill_manager._metric_queue == []

    def test_enabled_without_labels(self) -> None:
        """Enabled without labels."""
        killkrill_manager.enabled = True
        killkrill_manager.client = MagicMock()
        killkrill_manager.metric("api.request.count", 3.0, "counter")

        assert len(killkrill_manager._metric_queue) == 1
        entry = killkrill_manager._metric_queue[0]
        assert entry["name"] == "api.request.count"
        assert entry["value"] == 3.0
        assert entry["type"] == "counter"
        assert "labels" not in entry

    def test_enabled_with_labels(self) -> None:
        """Enabled with labels."""
        killkrill_manager.enabled = True
        killkrill_manager.client = MagicMock()
        killkrill_manager.metric("api.request.count", 3.0, "counter", {"endpoint": "/x"})

        entry = killkrill_manager._metric_queue[0]
        assert entry["labels"] == {"endpoint": "/x"}

    def test_internal_failure_is_caught_not_raised(self) -> None:
        """Internal failure is caught not raised."""
        killkrill_manager.enabled = True
        killkrill_manager.client = MagicMock()

        class _RaisingList(list[Any]):
            """Raising List."""

            def append(self, *a: Any, **k: Any) -> None:
                """Append."""
                raise RuntimeError("queue full")

        killkrill_manager._metric_queue = _RaisingList()
        killkrill_manager.metric("x", 1.0)  # must not raise


def _sleep_then_cancel(successes: int) -> Any:
    """asyncio.sleep stand-in: no-ops `successes` times, then cancels the loop."""
    calls = {"n": 0}

    async def _fake_sleep(_seconds: float) -> None:
        """Fake sleep."""
        calls["n"] += 1
        if calls["n"] > successes:
            raise asyncio.CancelledError()

    return _fake_sleep


class TestFlushQueues:
    """Flush Queues."""

    @pytest.mark.asyncio
    async def test_disabled_returns_without_looping(self) -> None:
        """Disabled returns without looping."""
        killkrill_manager.enabled = False
        killkrill_manager.client = MagicMock()
        await killkrill_manager._flush_queues()  # must return immediately, not hang

    @pytest.mark.asyncio
    async def test_no_client_returns_without_looping(self) -> None:
        """No client returns without looping."""
        killkrill_manager.enabled = True
        killkrill_manager.client = None
        await killkrill_manager._flush_queues()

    @pytest.mark.asyncio
    async def test_flushes_both_queues_then_clears_them(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flushes both queues then clears them."""
        killkrill_manager.enabled = True
        fake_client = MagicMock()
        fake_client.submit_logs = AsyncMock(return_value=True)
        fake_client.submit_metrics = AsyncMock(return_value=True)
        killkrill_manager.client = fake_client
        killkrill_manager._log_queue = [{"message": "hi"}]
        killkrill_manager._metric_queue = [{"name": "x"}]

        monkeypatch.setattr("app.killkrill.asyncio.sleep", _sleep_then_cancel(1))

        with pytest.raises(asyncio.CancelledError):
            await killkrill_manager._flush_queues()

        fake_client.submit_logs.assert_awaited_once_with([{"message": "hi"}])
        fake_client.submit_metrics.assert_awaited_once_with([{"name": "x"}])
        assert killkrill_manager._log_queue == []
        assert killkrill_manager._metric_queue == []

    @pytest.mark.asyncio
    async def test_submission_failure_is_caught_and_loop_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Submission failure is caught and loop continues."""
        killkrill_manager.enabled = True
        fake_client = MagicMock()
        fake_client.submit_logs = AsyncMock(side_effect=RuntimeError("receiver down"))
        killkrill_manager.client = fake_client
        killkrill_manager._log_queue = [{"message": "hi"}]
        killkrill_manager._metric_queue = []

        monkeypatch.setattr("app.killkrill.asyncio.sleep", _sleep_then_cancel(1))

        with pytest.raises(asyncio.CancelledError):
            await killkrill_manager._flush_queues()

        # The queue is only cleared on a SUCCESSFUL submit -- an exception
        # mid-flush must leave the entries in place for the next attempt,
        # not silently drop them.
        assert killkrill_manager._log_queue == [{"message": "hi"}]


class TestHealthCheck:
    """Health Check."""

    @pytest.mark.asyncio
    async def test_disabled_is_unhealthy(self) -> None:
        """Disabled is unhealthy."""
        killkrill_manager.enabled = False
        killkrill_manager.client = MagicMock()
        assert await killkrill_manager.health_check() is False

    @pytest.mark.asyncio
    async def test_no_client_is_unhealthy(self) -> None:
        """No client is unhealthy."""
        killkrill_manager.enabled = True
        killkrill_manager.client = None
        assert await killkrill_manager.health_check() is False

    @pytest.mark.asyncio
    async def test_healthy_client_reports_true(self) -> None:
        """Healthy client reports true."""
        killkrill_manager.enabled = True
        fake_client = MagicMock()
        fake_client.health_check = AsyncMock(return_value=True)
        killkrill_manager.client = fake_client
        assert await killkrill_manager.health_check() is True

    @pytest.mark.asyncio
    async def test_client_exception_reports_unhealthy_not_raised(self) -> None:
        """Client exception reports unhealthy not raised."""
        killkrill_manager.enabled = True
        fake_client = MagicMock()
        fake_client.health_check = AsyncMock(side_effect=RuntimeError("down"))
        killkrill_manager.client = fake_client
        assert await killkrill_manager.health_check() is False


class TestTrackHelpers:
    """Track Helpers."""

    def test_track_api_request_emits_count_and_duration_metrics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Track api request emits count and duration metrics."""
        recorded: list[tuple[Any, ...]] = []
        monkeypatch.setattr(killkrill_manager, "metric", lambda *a, **k: recorded.append((a, k)))

        track_api_request("/api/v1/teams", "POST", 201, 12.5)

        names = [call[0][0] for call in recorded]
        assert "api.request.post" in names
        assert "api.request.duration_ms" in names
        count_call = next(c for c in recorded if c[0][0] == "api.request.post")
        assert count_call[0][2] == "counter"
        assert count_call[0][3] == {"endpoint": "/api/v1/teams", "status": "201"}

    def test_track_user_action_without_team_omits_team_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Track user action without team omits team label."""
        recorded: list[tuple[Any, ...]] = []
        monkeypatch.setattr(killkrill_manager, "metric", lambda *a, **k: recorded.append((a, k)))

        track_user_action("login", "user-1")

        (args, _kwargs) = recorded[0]
        assert args[0] == "user.action.login"
        assert args[3] == {"user_id": "user-1"}

    def test_track_user_action_with_team_includes_team_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Track user action with team includes team label."""
        recorded: list[tuple[Any, ...]] = []
        monkeypatch.setattr(killkrill_manager, "metric", lambda *a, **k: recorded.append((a, k)))

        track_user_action("login", "user-1", team_id="team-9")

        (args, _kwargs) = recorded[0]
        assert args[3] == {"user_id": "user-1", "team_id": "team-9"}

    def test_track_feature_usage_labels_by_team(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Track feature usage labels by team."""
        recorded: list[tuple[Any, ...]] = []
        monkeypatch.setattr(killkrill_manager, "metric", lambda *a, **k: recorded.append((a, k)))

        track_feature_usage("sso", "team-9")

        (args, _kwargs) = recorded[0]
        assert args[0] == "feature.usage.sso"
        assert args[3] == {"team_id": "team-9"}
