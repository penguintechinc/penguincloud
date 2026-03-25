"""KillKrill logging and metrics integration."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional


class KillKrillManager:
    """Singleton manager for KillKrill integration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize KillKrill manager."""
        self.enabled = False
        self.client = None
        self.logger = logging.getLogger(__name__)
        self._log_queue = []
        self._metric_queue = []

    def setup(
        self,
        api_url: str,
        grpc_url: str,
        client_id: str,
        client_secret: str,
        enabled: bool = True,
    ):
        """Initialize KillKrill connection."""
        self.enabled = enabled
        if not enabled:
            self.logger.info("KillKrill disabled")
            return

        try:
            # Import ReceiverClient from killkrill_client package
            from .killkrill_client import ReceiverClient

            self.client = ReceiverClient(
                api_url=api_url,
                grpc_url=grpc_url,
                client_id=client_id,
                client_secret=client_secret,
            )
            self.logger.info("KillKrill manager initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize KillKrill: {e}")
            self.enabled = False

    def log(self, level: str, message: str, **kwargs):
        """Queue log entry in ECS format."""
        if not self.enabled or not self.client:
            return

        try:
            entry = {
                "@timestamp": datetime.utcnow().isoformat() + "Z",
                "log.level": level.upper(),
                "message": message,
                "service.name": "flask-backend",
            }
            entry.update(kwargs)
            self._log_queue.append(entry)
        except Exception as e:
            self.logger.error(f"Error queueing log: {e}")

    def metric(
        self,
        name: str,
        value: float,
        metric_type: str = "counter",
        labels: Optional[Dict[str, str]] = None,
    ):
        """Queue metric entry."""
        if not self.enabled or not self.client:
            return

        try:
            entry = {
                "name": name,
                "value": value,
                "type": metric_type,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "service": "flask-backend",
            }
            if labels:
                entry["labels"] = labels
            self._metric_queue.append(entry)
        except Exception as e:
            self.logger.error(f"Error queueing metric: {e}")

    async def _flush_queues(self):
        """Background task to flush logs/metrics every 5 seconds."""
        if not self.enabled or not self.client:
            return

        while True:
            try:
                await asyncio.sleep(5)
                if self._log_queue:
                    await self.client.send_logs(self._log_queue)
                    self._log_queue = []
                if self._metric_queue:
                    await self.client.send_metrics(self._metric_queue)
                    self._metric_queue = []
            except Exception as e:
                self.logger.error(f"Error flushing KillKrill queues: {e}")

    async def health_check(self) -> bool:
        """Check KillKrill availability."""
        if not self.enabled or not self.client:
            return False

        try:
            return await self.client.health_check()
        except Exception as e:
            self.logger.error(f"KillKrill health check failed: {e}")
            return False


# Singleton instance
killkrill_manager = KillKrillManager()


# Helper functions for common metrics
def track_api_request(endpoint: str, method: str, status: int, duration_ms: float):
    """Track API request metric."""
    killkrill_manager.metric(
        f"api.request.{method.lower()}",
        1,
        "counter",
        {"endpoint": endpoint, "status": str(status)},
    )
    killkrill_manager.metric(
        "api.request.duration_ms", duration_ms, "histogram", {"endpoint": endpoint}
    )


def track_user_action(action: str, user_id: str, team_id: Optional[str] = None):
    """Track user action metric."""
    labels = {"user_id": user_id}
    if team_id:
        labels["team_id"] = team_id
    killkrill_manager.metric(f"user.action.{action}", 1, "counter", labels)


def track_feature_usage(feature_name: str, team_id: str):
    """Track feature usage metric."""
    killkrill_manager.metric(
        f"feature.usage.{feature_name}", 1, "counter", {"team_id": team_id}
    )
