"""Background tasks for Flask backend."""

import logging
import threading
import time
from typing import Optional

from .license import license_manager
from .models import get_db

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks like license keepalive."""

    def __init__(self):
        """Initialize background task manager."""
        self._threads = []
        self._running = False

    def start(self) -> None:
        """Start all background tasks."""
        if self._running:
            return

        self._running = True

        # Start license keepalive task
        keepalive_thread = threading.Thread(
            target=self._license_keepalive_loop,
            daemon=True,
            name="LicenseKeepalive",
        )
        keepalive_thread.start()
        self._threads.append(keepalive_thread)

        logger.info("Background tasks started")

    def stop(self) -> None:
        """Stop all background tasks."""
        self._running = False
        logger.info("Background tasks stopped")

    def _license_keepalive_loop(self) -> None:
        """Background task that sends license keepalive every hour."""
        interval = 3600  # 1 hour in seconds

        while self._running:
            try:
                time.sleep(interval)

                if not self._running:
                    break

                # Collect usage statistics
                usage_stats = self._collect_usage_stats()

                # Send keepalive
                license_manager.checkin(usage_stats)

            except Exception as e:
                logger.error(f"Error in license keepalive task: {str(e)}")

    def _collect_usage_stats(self) -> dict:
        """Collect usage statistics for license keepalive."""
        try:
            db = get_db()

            # Count active users
            active_users = db.executesql(
                "SELECT COUNT(*) FROM users WHERE email_confirmed = true"
            )
            active_user_count = active_users[0][0] if active_users else 0

            return {
                "active_users": active_user_count,
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.warning(f"Failed to collect usage stats: {str(e)}")
            return {}


# Global background task manager instance
_background_manager: Optional[BackgroundTaskManager] = None


def get_background_manager() -> BackgroundTaskManager:
    """Get or create background task manager instance."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager
