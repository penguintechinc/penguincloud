"""Async HTTP transport for adapters using httpx.

All adapter network calls go through this module. No requests import anywhere.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .base import AdapterContext, HealthResult

logger = logging.getLogger(__name__)


class ResponseTooLargeError(Exception):
    """Raised when a product's response body exceeds the configured cap."""


#: Default request timeout (seconds)
TIMEOUT_DEFAULT = 10.0

#: Maximum allowed request timeout (seconds)
TIMEOUT_MAX = 30.0

#: Maximum response body size (bytes) — 10 MB
MAX_RESPONSE_SIZE = 10 * 1024 * 1024

#: Correlation ID header name
CORRELATION_ID_HEADER = "X-Correlation-ID"

#: Total attempts for a retryable failure (1 initial + 2 retries).
MAX_ATTEMPTS = 3

#: Base for the exponential backoff between attempts, in seconds. Attempt n
#: waits BACKOFF_BASE * 2**(n-1): 0.1s, then 0.2s.
BACKOFF_BASE = 0.1

#: Only these are retried. 5xx and transport-level failures are plausibly
#: transient; 4xx are not — retrying a 401 or a 422 just multiplies a
#: request that was answered correctly the first time, and against a
#: rate-limited product it converts one rejection into three.
RETRYABLE_STATUS_FLOOR = 500

#: Methods that may be retried. A retried POST/PATCH can duplicate a
#: non-idempotent side effect on a product that processed the first attempt
#: and failed only while responding, so they get exactly one attempt.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


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

        attempts = MAX_ATTEMPTS if method.upper() in IDEMPOTENT_METHODS else 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    timeout=timeout,
                    **kwargs,
                )
            except httpx.RequestError as exc:
                # Connect errors, read timeouts and the like: no response was
                # produced, so nothing about the product's state is known.
                last_error = exc
                if attempt == attempts:
                    raise
            else:
                if response.status_code < RETRYABLE_STATUS_FLOOR or attempt == attempts:
                    self._enforce_size_cap(response)
                    return response
                logger.info(
                    "adapter_request_retry",
                    extra={
                        "status_code": response.status_code,
                        "attempt": attempt,
                        "correlation_id": ctx.correlation_id,
                    },
                )

            await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

        # Unreachable: the loop either returns or re-raises on its last
        # attempt. Present so the function has no implicit None path.
        raise last_error or RuntimeError("adapter request exhausted retries")

    @staticmethod
    def _enforce_size_cap(response: httpx.Response) -> None:
        """Reject a response body larger than the cap.

        Enforced here rather than only at the proxy so *every* adapter call
        is covered — an adapter method reading a product's resource list
        gets the same protection a proxied passthrough does, and a hostile
        or broken product cannot exhaust memory through the path that
        happens to lack the check.
        """
        if len(response.content) > MAX_RESPONSE_SIZE:
            raise ResponseTooLargeError(
                f"Response body exceeds {MAX_RESPONSE_SIZE} bytes"
            )

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
