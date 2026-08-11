"""Background task lifecycle wiring (Task 6 defect #1) + dead config (defect #2).

Both were found by the prior implementer while reading app/background.py
and app/config.py to extend them for the health poller:

1. ``BackgroundTaskManager.start()`` was never called from anywhere in
   ``create_app`` -- the license keepalive loop it has always owned had
   therefore never run in any deployment.
2. ``Config.GO_HEALTH_GRPC_URL`` was the last live reference to
   ``services/go-backend``, deleted in Phase 0.
"""

from __future__ import annotations

import pytest
from app.background import get_background_manager
from app.config import Config
from quart import Quart


@pytest.mark.asyncio
async def test_background_tasks_start_on_app_startup(app: Quart) -> None:
    """The task actually exists and is running after before_serving.

    Deliberately NOT a mock assertion ("was start() called") -- that would
    pass even if start() were a no-op, which is exactly the shape of the
    original defect. Goes through the app's real ASGI lifespan
    (app.test_app()) rather than calling the hook function directly, so
    this is proof the WIRING in create_app works, not just that
    BackgroundTaskManager.start() works in isolation.
    """
    manager = get_background_manager()
    assert manager._running is False
    assert manager._tasks == []

    async with app.test_app():
        assert manager._running is True
        # License keepalive + product health poller (app.health_poller).
        assert len(manager._tasks) == 2
        assert all(not task.done() for task in manager._tasks)

    # after_serving must cancel and await both cleanly on shutdown.
    assert manager._running is False
    assert manager._tasks == []


def test_background_tasks_stop_before_the_dal_closes(app: Quart) -> None:
    """Fix wave 1 (I1): _stop_background_tasks must run before _shutdown_dal.

    Quart calls after_serving hooks in REGISTRATION order (app.py:
    ``for func in self.after_serving_funcs``, a plain list appended to in
    order -- not reversed). penguin-dal's ``init_dal()`` registers
    ``_shutdown_dal`` as an after_serving hook internally; app/__init__.py
    must register ``_stop_background_tasks`` BEFORE calling ``init_dal()``
    so background tasks -- including a health-poll sweep that may be
    mid-flight -- are cancelled before the connection pool they read from
    closes underneath them. Asserted directly against the registered
    sequence, not merely that shutdown eventually completes: a wrong order
    still "completes" without ever failing an end-to-end lifespan test,
    since poll_forever's crash-backoff swallows the resulting error.
    """
    names = [func.__name__ for func in app.after_serving_funcs]
    assert "_stop_background_tasks" in names
    assert "_shutdown_dal" in names
    assert names.index("_stop_background_tasks") < names.index(
        "_shutdown_dal"
    ), f"after_serving order is {names}; _stop_background_tasks must come first"


@pytest.mark.asyncio
async def test_start_background_tasks_logs_cache_degradation_warning(
    app: Quart, caplog: pytest.LogCaptureFixture
) -> None:
    """Fix wave 2 (W2-1): the I4 startup warning must fire at the WIRING point.

    Both of I4's original tests called app.health_cache.log_startup_state()
    directly with a plain dict -- nothing asserted that
    _start_background_tasks (app/__init__.py) actually CALLS it. Deleting
    that call left every existing test green, which defeats the entire
    point of a startup warning whose purpose is that an operator cannot
    miss the degraded cache. Drives the real ASGI lifespan
    (app.test_app()), the same way test_background_tasks_start_on_app_startup
    proves BackgroundTaskManager.start() is actually wired rather than
    merely callable in isolation.
    """
    assert app.config.get("CACHE_HOST", "") == ""  # TestingConfig default

    with caplog.at_level("WARNING", logger="app.health_cache"):
        async with app.test_app():
            pass

    messages = [r.message for r in caplog.records if r.name == "app.health_cache"]
    assert any(
        "health_cache_is_per_process_only" in m for m in messages
    ), f"expected the cache-degradation warning during startup; captured: {messages}"


@pytest.mark.asyncio
async def test_background_manager_is_idempotent_across_restarts(app: Quart) -> None:
    """Two startup/shutdown cycles on the same (singleton) manager both work.

    The manager is process-wide (get_background_manager() returns one
    instance), so a SECOND app's lifespan reusing it after the first has
    fully torn down must not double-append tasks or refuse to start again.
    """
    manager = get_background_manager()

    async with app.test_app():
        first_cycle_task_count = len(manager._tasks)

    async with app.test_app():
        assert len(manager._tasks) == first_cycle_task_count

    assert manager._tasks == []


def test_go_health_grpc_url_config_removed() -> None:
    """The last live reference to the deleted go-backend service is gone.

    GO_HEALTH_GRPC_URL used to default to "go-backend:50052"; that service
    was deleted in Phase 0 and its health-polling duty is now
    app/health_poller.py.
    """
    assert not hasattr(Config, "GO_HEALTH_GRPC_URL")
