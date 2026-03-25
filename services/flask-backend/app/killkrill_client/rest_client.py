"""
REST client implementation for Killkrill receiver communication.
"""

from typing import Any, List

import httpx
import structlog

from .exceptions import ConnectionError, SubmissionError

logger = structlog.get_logger(__name__)


class RESTSubmitter:
    """Handles REST/HTTP submissions to Killkrill receivers."""

    def __init__(self, api_url: str, jwt_token: str, timeout: int = 30) -> None:
        """
        Initialize REST submitter.

        Args:
            api_url: Base API URL (e.g., https://receiver.example.com)
            jwt_token: JWT authentication token
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.jwt_token = jwt_token
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None

    async def connect(self) -> bool:
        """
        Initialize HTTP client.

        Returns:
            True if connection successful
        """
        try:
            self.client = httpx.AsyncClient(
                base_url=self.api_url,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.jwt_token}"},
                http2=True,  # Enable HTTP/2
            )

            # Test connection with health check
            healthy = await self.health_check()
            if healthy:
                logger.info("rest_connection_established", url=self.api_url)
            return healthy

        except Exception as e:
            logger.warning("rest_connection_failed", url=self.api_url, error=str(e))
            return False

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("rest_connection_closed", url=self.api_url)

    async def health_check(self) -> bool:
        """
        Check REST endpoint health.

        Returns:
            True if healthy, False otherwise
        """
        if not self.client:
            return False

        try:
            response = await self.client.get("/healthz")
            healthy = response.status_code == 200
            if not healthy:
                logger.warning(
                    "rest_health_check_unhealthy",
                    status_code=response.status_code,
                    url=self.api_url,
                )
            return healthy

        except httpx.RequestError as e:
            logger.warning("rest_health_check_failed", url=self.api_url, error=str(e))
            return False

    async def submit_logs(self, logs: List[dict]) -> bool:
        """
        Submit logs via REST API.

        Args:
            logs: List of log entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails
            ConnectionError: If not connected
        """
        if not self.client:
            raise ConnectionError("REST client not initialized")

        try:
            response = await self.client.post("/api/v1/logs", json={"logs": logs})

            if response.status_code == 200:
                logger.info("rest_logs_submitted", count=len(logs))
                return True
            elif response.status_code == 401:
                raise SubmissionError("Authentication failed - token may be expired")
            else:
                raise SubmissionError(
                    f"Log submission failed with status {response.status_code}: "
                    f"{response.text}"
                )

        except httpx.RequestError as e:
            logger.error("rest_log_submission_failed", error=str(e))
            raise SubmissionError(f"REST log submission failed: {str(e)}")

    async def submit_metrics(self, metrics: List[dict]) -> bool:
        """
        Submit metrics via REST API.

        Args:
            metrics: List of metric entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails
            ConnectionError: If not connected
        """
        if not self.client:
            raise ConnectionError("REST client not initialized")

        try:
            response = await self.client.post(
                "/api/v1/metrics", json={"metrics": metrics}
            )

            if response.status_code == 200:
                logger.info("rest_metrics_submitted", count=len(metrics))
                return True
            elif response.status_code == 401:
                raise SubmissionError("Authentication failed - token may be expired")
            else:
                raise SubmissionError(
                    f"Metric submission failed with status {response.status_code}: "
                    f"{response.text}"
                )

        except httpx.RequestError as e:
            logger.error("rest_metric_submission_failed", error=str(e))
            raise SubmissionError(f"REST metric submission failed: {str(e)}")

    async def __aenter__(self) -> "RESTSubmitter":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
