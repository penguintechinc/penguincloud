"""Async HTTP transport for adapters using httpx.

All adapter network calls go through this module. No requests import anywhere.

This module is the second half of the security boundary described in
:mod:`app.adapters.base`: the proxy's ``route_allowlist`` decides which
caller-supplied paths are forwarded, and the transport decides *where the
connection's decrypted credential may go*. Every request is pinned to the
origin of :attr:`AdapterContext.base_url` and redirects are never followed,
so no adapter method — trusted or buggy — can send the stored secret to a
host the operator did not configure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

from .base import AdapterContext, HealthResult, PathTraversalError, normalize_proxy_path

logger = logging.getLogger(__name__)


class ResponseTooLargeError(Exception):
    """Raised when a product's response body exceeds the configured cap."""


class CredentialEgressError(Exception):
    """Raised when a request would send the credential off the pinned origin.

    Not a policy warning: the request is not made. It fires on a URL whose
    scheme or host differs from the connection's ``base_url``, which is what
    an SSRF through an adapter, a mis-built URL, or a redirect chased by
    mistake would all look like at this layer.
    """


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
                # A 302 to another host would carry the injected credential
                # there, past the origin pin below. httpx defaults to False;
                # stated explicitly because the default changing silently
                # would reopen credential egress.
                follow_redirects=False,
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
        auth_headers = self._build_auth_headers(ctx.auth_type, ctx.api_key, ctx.api_secret)
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

        self._assert_pinned_origin(url, ctx)

        attempts = MAX_ATTEMPTS if method.upper() in IDEMPOTENT_METHODS else 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            outbound = client.build_request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
            try:
                # stream=True so status and headers are available before any
                # body is read: a retryable 5xx is discarded without pulling
                # its payload, and the cap below can refuse an oversized body
                # instead of buffering it first.
                response = await client.send(outbound, stream=True, follow_redirects=False)
            except httpx.RequestError as exc:
                # Connect errors, read timeouts and the like: no response was
                # produced, so nothing about the product's state is known.
                last_error = exc
                if attempt == attempts:
                    raise
            else:
                if response.status_code < RETRYABLE_STATUS_FLOOR or attempt == attempts:
                    return await self._read_capped(response)
                await response.aclose()
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
    def _assert_pinned_origin(url: str, ctx: AdapterContext) -> None:
        """Refuse a URL that is not on the connection's own origin.

        The credential belongs to one product at one address. Pinning the
        scheme and host to ``ctx.base_url`` means an adapter cannot send it
        anywhere else — whether through a mis-built URL, a caller-influenced
        value that reached a supposedly-trusted adapter method, or an
        internal address probed for SSRF. It is the structural half of the
        boundary decision documented in :mod:`app.adapters.base`: policy
        says adapter methods are trusted, and this makes the blast radius of
        that trust exactly one origin.

        An empty ``base_url`` pins to nothing and is therefore refused
        outright rather than treated as "no restriction".
        """
        base = urlsplit(ctx.base_url)
        if not base.scheme or not base.netloc:
            raise CredentialEgressError("connection has no usable base_url to pin the request to")
        target = urlsplit(url)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise CredentialEgressError(
                f"refusing to send connection {ctx.connection_id}'s credential to "
                f"{target.scheme}://{target.netloc}; pinned to "
                f"{base.scheme}://{base.netloc}"
            )
        try:
            normalize_proxy_path(target.path or "/")
        except PathTraversalError as exc:
            raise CredentialEgressError(f"refusing malformed request path: {exc}") from exc

    @staticmethod
    async def _read_capped(response: httpx.Response) -> httpx.Response:
        """Buffer a streamed body, refusing one that exceeds the cap.

        Two checks, because either alone is insufficient. ``Content-Length``
        is consulted first so an oversized body is refused before a single
        chunk is read — but it is advisory (absent under chunked encoding,
        and understated for a compressed body that inflates past the cap on
        decode), so the incremental read enforces the real bound and stops
        at the first chunk that crosses it.

        This is what makes the memory-exhaustion guarantee true: the previous
        implementation measured ``len(response.content)`` *after* httpx had
        already buffered the entire body, so a hostile product had allocated
        whatever it wanted before the check ran.

        The rebuilt response drops ``content-length`` and ``content-encoding``:
        the body here is decoded and its length recomputed, so carrying the
        wire values forward would describe it wrongly.
        """
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_RESPONSE_SIZE:
                    await response.aclose()
                    raise ResponseTooLargeError(
                        f"Response declares {declared} bytes, over the "
                        f"{MAX_RESPONSE_SIZE} byte cap"
                    )
            except ValueError:
                # Malformed header. The incremental read still bounds it.
                pass

        body = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_SIZE:
                    raise ResponseTooLargeError(f"Response body exceeds {MAX_RESPONSE_SIZE} bytes")
        finally:
            await response.aclose()

        headers = [
            (name, value)
            for name, value in response.headers.multi_items()
            if name.lower() not in ("content-length", "content-encoding")
        ]
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            content=bytes(body),
            request=response.request,
            extensions=response.extensions,
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


async def get_transport(connect_timeout: float = TIMEOUT_DEFAULT) -> Transport:
    """Get or create the global transport instance.

    Args:
        connect_timeout: Per-request timeout in seconds for the underlying
            HTTP client, applied only on first call

    Returns:
        Connected Transport instance
    """
    global _transport
    if _transport is None:
        _transport = Transport(timeout=connect_timeout)
        await _transport.connect()
    return _transport


async def close_transport() -> None:
    """Close the global transport instance."""
    global _transport
    if _transport is not None:
        await _transport.close()
        _transport = None
