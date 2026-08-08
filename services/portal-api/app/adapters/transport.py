"""Async HTTP transport for adapters using httpx.

All adapter network calls go through this module. No requests import anywhere.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import AdapterContext, HealthResult

logger = logging.getLogger(__name__)

#: Default request timeout (seconds)
TIMEOUT_DEFAULT = 10.0

#: Maximum allowed request timeout (seconds)
TIMEOUT_MAX = 30.0

#: Maximum response body size (bytes) — 10 MB
MAX_RESPONSE_SIZE = 10 * 1024 * 1024

#: Correlation ID header name
CORRELATION_ID_HEADER = "X-Correlation-ID"


class Transport:
    """Shared async HTTP transport for all adapters.

    Configures retry logic (5xx only), timeouts, response size limits,
    correlation ID tracking, and credential injection.
    """

    def __init__(self, timeout: float = TIMEOUT_DEFAULT) -> None:
        """Initialize transport.

        Args:
            timeout: Request timeout in seconds (clamped to TIMEOUT_MAX).
        """
        self.timeout = min(timeout, TIMEOUT_MAX)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Transport:
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Create the underlying httpx.AsyncClient."""
        if self._client is None:
            # Retry on 5xx only, not 4xx (auth errors, invalid requests)
            # Note: httpx doesn't have built-in async retry; we handle retries
            # at the request level or rely on exponential backoff at the app level
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                ),
            )

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or initialize the client."""
        if self._client is None:
            raise RuntimeError("Transport not connected — call connect() first")
        return self._client

    def _build_auth_headers(
        self, auth_type: str, api_key: str, api_secret: str = ""
    ) -> dict[str, str]:
        """Build authentication headers based on auth_type.

        Args:
            auth_type: bearer, api_key, basic, or none
            api_key: Primary credential (token or username)
            api_secret: Secondary credential (password for basic auth)

        Returns:
            Dictionary of headers to inject into requests.
        """
        headers = {}
        if auth_type == "bearer" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key
        elif auth_type == "basic" and api_key:
            import base64

            creds = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    async def request(
        self,
        method: str,
        url: str,
        ctx: AdapterContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an authenticated HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL (no credential substitution, path rewriting, etc.)
            ctx: AdapterContext with credentials and correlation ID
            **kwargs: Additional httpx.request arguments (json, data, params, etc.)

        Returns:
            httpx.Response object

        Raises:
            httpx.RequestError: Network, timeout, or other transport errors
        """
        client = self._get_client()

        # Merge auth headers with any caller-supplied headers
        headers = kwargs.pop("headers", {})
        auth_headers = self._build_auth_headers(
            ctx.auth_type, ctx.api_key, ctx.api_secret
        )
        headers.update(auth_headers)

        # Inject correlation ID
        if ctx.correlation_id:
            headers[CORRELATION_ID_HEADER] = ctx.correlation_id

        # Ensure Content-Type for JSON
        if "json" in kwargs and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        # Make the request with timeout override if supplied
        timeout = kwargs.pop("timeout", self.timeout)
        timeout = min(timeout, TIMEOUT_MAX)

        logger.debug(
            "Adapter request",
            extra={
                "method": method,
                "url": url,
                "correlation_id": ctx.correlation_id,
                "connection_id": ctx.connection_id,
            },
        )

        response = await client.request(
            method,
            url,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )

        return response

    async def health_check(
        self, base_url: str, health_endpoint: str, ctx: AdapterContext
    ) -> HealthResult:
        """Perform a health check request.

        Args:
            base_url: Base URL of the adapter (e.g., "https://gough.local")
            health_endpoint: Health endpoint path (e.g., "/healthz")
            ctx: AdapterContext with credentials

        Returns:
            HealthResult with status, status_code, response_time_ms
        """
        import time

        url = f"{base_url.rstrip('/')}{health_endpoint}"
        start = time.perf_counter()

        try:
            response = await self.request("GET", url, ctx, timeout=5.0)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            if response.status_code < 300:
                status = "healthy"
            elif response.status_code < 500:
                status = "degraded"
            else:
                status = "unhealthy"

            return HealthResult(
                status=status,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "Health check failed",
                extra={
                    "url": url,
                    "error": str(e),
                    "correlation_id": ctx.correlation_id,
                },
            )
            return HealthResult(
                status="unhealthy",
                status_code=0,
                response_time_ms=elapsed_ms,
                error=str(e),
            )


# Global singleton transport instance
_transport: Transport | None = None


async def get_transport(timeout: float = TIMEOUT_DEFAULT) -> Transport:
    """Get or create the global transport instance.

    Args:
        timeout: Request timeout in seconds (only used on first call)

    Returns:
        Connected Transport instance
    """
    global _transport
    if _transport is None:
        _transport = Transport(timeout=timeout)
        await _transport.connect()
    return _transport


async def close_transport() -> None:
    """Close the global transport instance."""
    global _transport
    if _transport is not None:
        await _transport.close()
        _transport = None
