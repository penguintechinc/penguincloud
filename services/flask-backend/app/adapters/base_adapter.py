"""Base Product Adapter — all adapters inherit from this."""

import asyncio
import logging
from functools import partial
from typing import Any

import requests
from werkzeug.wrappers.response import Response as WerkzeugResponse

from quart import Response, make_response

from ..encryption import decrypt_value

logger = logging.getLogger(__name__)


class ProductAdapter:
    """Base class for all product adapters."""

    PRODUCT_TYPE: str = "generic"
    DISPLAY_NAME: str = "Generic Product"
    CATEGORY: str = "operations"
    ICON: str = "package"
    DEFAULT_HEALTH_ENDPOINT: str = "/healthz"
    DEFAULT_API_VERSION: str = "v1"
    DISCOVERY_PORTS: list[int] = []
    DISCOVERY_SIGNATURES: list[str] = []

    def __init__(self, connection: dict[str, Any]) -> None:
        self.connection = connection
        self.base_url = connection.get("base_url", "").rstrip("/")
        self.auth_type = connection.get("auth_type", "bearer")
        self.api_version = connection.get("api_version", self.DEFAULT_API_VERSION)
        self.health_endpoint = connection.get(
            "health_endpoint", self.DEFAULT_HEALTH_ENDPOINT
        )
        self._api_key = connection.get("api_key", "")
        self._api_secret = connection.get("api_secret", "")

    def _decrypt_key(self) -> str:
        """Decrypt stored API key."""
        if not self._api_key or self._api_key == "***":
            return ""
        try:
            return decrypt_value(self._api_key)
        except (ValueError, Exception):
            return ""

    def _decrypt_secret(self) -> str:
        """Decrypt stored API secret."""
        if not self._api_secret or self._api_secret == "***":
            return ""
        try:
            return decrypt_value(self._api_secret)
        except (ValueError, Exception):
            return ""

    def get_headers(self) -> dict[str, str]:
        """Build authentication headers for the product API."""
        headers = {"Content-Type": "application/json"}
        key = self._decrypt_key()

        if self.auth_type == "bearer" and key:
            headers["Authorization"] = f"Bearer {key}"
        elif self.auth_type == "api_key" and key:
            headers["X-API-Key"] = key
        elif self.auth_type == "basic":
            import base64

            secret = self._decrypt_secret()
            creds = base64.b64encode(f"{key}:{secret}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

        return headers

    def health_check(self) -> dict[str, Any]:
        """Check product health."""
        url = f"{self.base_url}{self.health_endpoint}"
        try:
            resp = requests.get(url, headers=self.get_headers(), timeout=10)
            if resp.status_code < 300:
                status = "healthy"
            elif resp.status_code < 500:
                status = "degraded"
            else:
                status = "unhealthy"
            return {
                "status": status,
                "status_code": resp.status_code,
                "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
            }
        except requests.RequestException as e:
            return {
                "status": "unhealthy",
                "status_code": 0,
                "error": str(e),
                "response_time_ms": 0,
            }

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Get summary data for the dashboard overview."""
        health = self.health_check()
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "category": self.CATEGORY,
            "health": health,
        }

    async def proxy_request(
        self, method: str, path: str, **kwargs: Any
    ) -> Response | WerkzeugResponse:
        """Forward a request to the product API.

        Async because quart.make_response is a coroutine; the sync Flask
        spelling returned an un-awaited coroutine instead of a Response.
        """
        url = f"{self.base_url}/api/{self.api_version}/{path.lstrip('/')}"
        headers = self.get_headers()

        # Merge any extra headers
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            # requests is blocking — keep it off the event loop. (The whole
            # adapter layer moves to an async client in Task 3.)
            resp = await asyncio.to_thread(
                partial(
                    requests.request,
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=30,
                    **kwargs,
                )
            )
            proxied = await make_response(resp.content, resp.status_code)
            for key, value in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    proxied.headers[key] = value
            return proxied
        except requests.RequestException as e:
            return await make_response(
                {"error": f"Proxy request failed: {str(e)}"}, 502
            )

    def get_capabilities(self) -> list[str]:
        """Return list of supported capabilities."""
        return ["health_check", "proxy"]

    def get_management_schema(self) -> dict[str, Any]:
        """Describe available management actions/endpoints for the WebUI."""
        return {
            "product_type": self.PRODUCT_TYPE,
            "display_name": self.DISPLAY_NAME,
            "sections": [],
        }
