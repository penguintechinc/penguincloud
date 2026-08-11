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
