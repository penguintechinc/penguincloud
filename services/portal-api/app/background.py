"""Background tasks for the Quart backend.

Runs as asyncio tasks on the app's event loop rather than daemon threads:
penguin-dal's AsyncDB and Quart's app context are both loop-bound, so a
bare thread cannot reach either.

``start()``/``stop()`` are wired to the app's own lifespan in
``app/__init__.py`` (``@app.before_serving`` / ``@app.after_serving``).
Previously nothing called ``start()`` from anywhere in ``create_app`` --
the license keepalive loop below had therefore never run in any
deployment. Task 6 fixes that and adds the product health poller
(``app.health_poller``) as a second task on the same manager, so both
start and stop together.
"""

import asyncio
import logging
import time
from typing import Any

from .health_cache import close_cache_client
from .license import license_manager
from .models import get_db

logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL_SECONDS = 3600


class BackgroundTaskManager:
    """Owns the app's long-running background asyncio tasks."""

    def __init__(self) -> None:
        """Initialize an empty, stopped task manager."""
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    def start(self) -> None:
        """Start all background tasks on the running event loop."""
        if self._running:
            return

        self._running = True
        self._tasks.append(asyncio.create_task(self._license_keepalive_loop()))
        self._tasks.append(asyncio.create_task(self._health_poll_loop()))
        logger.info("Background tasks started")

    async def stop(self) -> None:
        """Signal shutdown and await every background task's exit."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        await close_cache_client()
        logger.info("Background tasks stopped")

    async def _health_poll_loop(self) -> None:
        """Run the product health poller until stopped.

        Delegates the actual sweep/jitter/backoff logic to
        ``app.health_poller`` (which owns its own SanitizedLogger and
        Prometheus series) rather than duplicating it here -- this method
        exists only to give the poller a task this manager's ``stop()``
        already knows how to cancel and await.
        """
        from .health_poller import poll_forever

        await poll_forever(lambda: self._running)

    async def _license_keepalive_loop(self) -> None:
        """Send a license keepalive with usage stats once per hour."""
        while self._running:
            try:
                await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)

                if not self._running:
                    break

                usage_stats = await self._collect_usage_stats()

                # license_manager.checkin is blocking (requests-based), so it
                # must not run inline on the event loop.
                await asyncio.to_thread(license_manager.checkin, usage_stats)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in license keepalive task: {str(e)}")

    async def _collect_usage_stats(self) -> dict[str, Any]:
        """Collect usage statistics reported alongside the keepalive."""
        try:
            db = get_db()

            # executesql's return type is a broad union (Rows, list of
            # tuples, list of dicts, int...) depending on the driver and
            # query, so narrow explicitly rather than blind-indexing.
            rows = await db.executesql("SELECT COUNT(*) FROM users WHERE email_confirmed = true")
            active_user_count = 0
            if isinstance(rows, list) and rows:
                first = rows[0]
                if isinstance(first, list | tuple) and first:
                    active_user_count = int(first[0])

            return {
                "active_users": active_user_count,
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.warning(f"Failed to collect usage stats: {str(e)}")
            return {}


# Global background task manager instance
_background_manager: BackgroundTaskManager | None = None


def get_background_manager() -> BackgroundTaskManager:
    """Get or create the process-wide background task manager."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager
