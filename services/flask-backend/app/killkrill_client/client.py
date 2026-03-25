"""
Main ReceiverClient implementation with JWT authentication and protocol fallback.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List

import httpx
import structlog

from .exceptions import AuthenticationError, ConnectionError, SubmissionError
from .grpc_client import GRPCSubmitter
from .rest_client import RESTSubmitter

logger = structlog.get_logger(__name__)


@dataclass
class TokenInfo:
    """JWT token information."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    def is_expired(self) -> bool:
        """Check if token is expired or will expire soon."""
        return datetime.utcnow() >= self.expires_at - timedelta(minutes=5)


class ReceiverClient:
    """
    Unified client for Killkrill receivers with JWT auth and gRPC/REST fallback.
    """

    def __init__(
        self,
        api_url: str,
        grpc_url: str,
        client_id: str,
        client_secret: str,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ) -> None:
        """
        Initialize receiver client.

        Args:
            api_url: REST API base URL (https://receiver.example.com)
            grpc_url: gRPC endpoint (receiver.example.com:50051)
            client_id: OAuth2 client ID for authentication
            client_secret: OAuth2 client secret
            max_retries: Maximum retry attempts for failed operations
            retry_backoff: Initial backoff delay in seconds for retries
        """
        self.api_url = api_url.rstrip("/")
        self.grpc_url = grpc_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        self.token_info: TokenInfo | None = None
        self.use_grpc = True
        self.grpc_client: GRPCSubmitter | None = None
        self.rest_client: RESTSubmitter | None = None

        self._authenticated = False
        self._lock = asyncio.Lock()

    async def authenticate(self) -> bool:
        """
        Authenticate with the receiver and obtain JWT token.

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If authentication fails
        """
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/v1/auth/login",
                        json={
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                        },
                        timeout=10.0,
                    )

                    if response.status_code != 200:
                        raise AuthenticationError(
                            f"Authentication failed: {response.status_code} - "
                            f"{response.text}"
                        )

                    data = response.json()
                    expires_in = data.get("expires_in", 3600)

                    self.token_info = TokenInfo(
                        access_token=data["access_token"],
                        refresh_token=data["refresh_token"],
                        expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
                    )

                    self._authenticated = True
                    logger.info("authentication_successful", client_id=self.client_id)

                    # Initialize protocol clients
                    await self._initialize_clients()
                    return True

            except httpx.RequestError as e:
                logger.error("authentication_request_failed", error=str(e))
                raise AuthenticationError(f"Authentication request failed: {str(e)}")
            except KeyError as e:
                logger.error("authentication_response_invalid", missing_field=str(e))
                raise AuthenticationError(f"Invalid authentication response: {str(e)}")

    async def refresh_token(self) -> bool:
        """
        Refresh JWT token using refresh token.

        Returns:
            True if refresh successful

        Raises:
            AuthenticationError: If refresh fails
        """
        if not self.token_info:
            raise AuthenticationError("No token to refresh")

        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/v1/auth/refresh",
                        json={"refresh_token": self.token_info.refresh_token},
                        timeout=10.0,
                    )

                    if response.status_code != 200:
                        logger.warning("token_refresh_failed", reauthenticating=True)
                        return await self.authenticate()

                    data = response.json()
                    expires_in = data.get("expires_in", 3600)

                    self.token_info.access_token = data["access_token"]
                    self.token_info.expires_at = datetime.utcnow() + timedelta(
                        seconds=expires_in
                    )

                    logger.info("token_refreshed")

                    # Reinitialize clients with new token
                    await self._initialize_clients()
                    return True

            except httpx.RequestError as e:
                logger.error("token_refresh_request_failed", error=str(e))
                raise AuthenticationError(f"Token refresh failed: {str(e)}")

    async def _initialize_clients(self) -> None:
        """Initialize gRPC and REST clients with current token."""
        if not self.token_info:
            return

        # Close existing clients
        if self.grpc_client:
            self.grpc_client.disconnect()
        if self.rest_client:
            await self.rest_client.disconnect()

        # Try gRPC first
        if await self._try_grpc():
            logger.info("protocol_selected", protocol="grpc")
        else:
            await self._fallback_to_rest()

    async def _try_grpc(self) -> bool:
        """
        Attempt to establish gRPC connection.

        Returns:
            True if gRPC connection successful
        """
        if not self.token_info:
            return False

        try:
            self.grpc_client = GRPCSubmitter(
                self.grpc_url, self.token_info.access_token
            )

            if self.grpc_client.connect():
                self.use_grpc = True
                return True

            return False

        except Exception as e:
            logger.warning("grpc_initialization_failed", error=str(e))
            return False

    async def _fallback_to_rest(self) -> None:
        """Fallback to REST protocol."""
        if not self.token_info:
            return

        logger.info("protocol_fallback", from_protocol="grpc", to_protocol="rest")

        self.rest_client = RESTSubmitter(self.api_url, self.token_info.access_token)
        await self.rest_client.connect()
        self.use_grpc = False
        logger.info("protocol_selected", protocol="rest")

    async def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated and token is valid."""
        if not self._authenticated or not self.token_info:
            await self.authenticate()
        elif self.token_info.is_expired():
            await self.refresh_token()

    async def _retry_with_backoff(self, operation: str, func: Any, *args: Any) -> bool:
        """
        Execute operation with exponential backoff retry logic.

        Args:
            operation: Operation name for logging
            func: Function to execute
            *args: Arguments to pass to function

        Returns:
            True if operation successful

        Raises:
            SubmissionError: If all retries fail
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                await self._ensure_authenticated()
                result = await func(*args)
                return result

            except SubmissionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_backoff * (2**attempt)
                    logger.warning(
                        "operation_retry",
                        operation=operation,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

                    # Try protocol fallback on gRPC failure
                    if self.use_grpc and self.grpc_client:
                        logger.info("attempting_protocol_fallback")
                        await self._fallback_to_rest()

        logger.error(
            "operation_failed_all_retries", operation=operation, error=str(last_error)
        )
        raise SubmissionError(f"{operation} failed after {self.max_retries} retries")

    async def submit_logs(self, logs: List[dict]) -> bool:
        """
        Submit logs via gRPC or REST fallback.

        Args:
            logs: List of log entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails after retries
        """

        async def _submit() -> bool:
            if self.use_grpc and self.grpc_client:
                return self.grpc_client.submit_logs(logs)
            elif self.rest_client:
                return await self.rest_client.submit_logs(logs)
            else:
                raise ConnectionError("No active protocol client")

        return await self._retry_with_backoff("submit_logs", _submit)

    async def submit_metrics(self, metrics: List[dict]) -> bool:
        """
        Submit metrics via gRPC or REST fallback.

        Args:
            metrics: List of metric entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails after retries
        """

        async def _submit() -> bool:
            if self.use_grpc and self.grpc_client:
                return self.grpc_client.submit_metrics(metrics)
            elif self.rest_client:
                return await self.rest_client.submit_metrics(metrics)
            else:
                raise ConnectionError("No active protocol client")

        return await self._retry_with_backoff("submit_metrics", _submit)

    async def health_check(self) -> bool:
        """
        Check connection health.

        Returns:
            True if connection is healthy
        """
        try:
            await self._ensure_authenticated()

            if self.use_grpc and self.grpc_client:
                return self.grpc_client.health_check()
            elif self.rest_client:
                return await self.rest_client.health_check()

            return False

        except Exception as e:
            logger.warning("health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close all connections."""
        if self.grpc_client:
            self.grpc_client.disconnect()
        if self.rest_client:
            await self.rest_client.disconnect()

        self._authenticated = False
        logger.info("receiver_client_closed")

    async def __aenter__(self) -> "ReceiverClient":
        """Async context manager entry."""
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
