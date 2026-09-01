"""RFC 8628 OAuth 2.0 Device Authorization Grant -- the CLIENT half.

The server half landed in `app.device_auth`
(`services/portal-api/app/device_auth.py`) alongside this feature; this
module is its counterpart:

1. `authorize()` -- POST `/api/v1/auth/device/authorize`, unauthenticated,
   mints a `device_code`/`user_code` pair.
2. The caller shows `user_code`/`verification_uri_complete` to the human.
3. `poll_for_token()` -- POST `/api/v1/auth/device/token` on a loop,
   honoring the SERVER's own `interval` and its RFC 8628 SS3.5 error
   vocabulary (`authorization_pending`, `slow_down`, `expired_token`,
   `access_denied`) -- never a client-invented polling cadence, and never
   retried past `expires_in`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

import httpx

from ..errors import DeviceFlowDeniedError, DeviceFlowError, DeviceFlowExpiredError
from .tokens import TokenSet

#: RFC 8628 SS3.5: "the interval MUST be increased by 5 seconds for this
#: and all subsequent requests" on slow_down.
_SLOW_DOWN_INCREMENT_SECONDS: Final[int] = 5

_ERROR_AUTHORIZATION_PENDING: Final[str] = "authorization_pending"
_ERROR_SLOW_DOWN: Final[str] = "slow_down"
_ERROR_EXPIRED_TOKEN: Final[str] = "expired_token"  # noqa: S105 -- RFC 8628 error code, not a credential
_ERROR_ACCESS_DENIED: Final[str] = "access_denied"

#: Async sleep signature, injected so tests can run the poll loop without
#: real wall-clock delay.
_SleepFn = Callable[[float], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class DeviceAuthorization:
    """The `device/authorize` response -- see `app.device_auth.DeviceAuthorizationResponse`."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> DeviceAuthorization:
        """Parse the JSON body of a `POST /api/v1/auth/device/authorize` response."""
        return cls(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            verification_uri_complete=body["verification_uri_complete"],
            expires_in=int(body["expires_in"]),
            interval=int(body["interval"]),
        )


class DeviceFlowClient:
    """Drives the `device/authorize` -> (human approves) -> `device/token` loop."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        """Wrap an already-configured `httpx.AsyncClient` (base_url = portal URL)."""
        self._http = http_client

    async def authorize(self) -> DeviceAuthorization:
        """POST /api/v1/auth/device/authorize. Unauthenticated. RFC 8628 SS3.1/3.2."""
        response = await self._http.post("/api/v1/auth/device/authorize")
        response.raise_for_status()
        return DeviceAuthorization.from_wire(response.json())

    async def poll_for_token(
        self,
        authorization: DeviceAuthorization,
        *,
        sleep: _SleepFn | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> TokenSet:
        """Poll `/api/v1/auth/device/token` until approved, denied, or expired.

        `sleep`/`clock` are injectable so tests exercise every branch
        (pending -> slow_down -> approved, and the expiry path) without
        real wall-clock waiting.
        """
        sleep_fn: _SleepFn = sleep if sleep is not None else _real_sleep
        interval = authorization.interval
        deadline = clock() + authorization.expires_in

        while True:
            if clock() >= deadline:
                raise DeviceFlowExpiredError("Device code expired before the login was approved.")
            await sleep_fn(interval)
            response = await self._http.post(
                "/api/v1/auth/device/token",
                json={"device_code": authorization.device_code},
            )
            if response.status_code == 200:
                return TokenSet.from_login_response(response.json())

            error = _extract_error(response)
            if error == _ERROR_SLOW_DOWN:
                interval += _SLOW_DOWN_INCREMENT_SECONDS
                continue
            if error == _ERROR_AUTHORIZATION_PENDING:
                continue
            if error == _ERROR_EXPIRED_TOKEN:
                raise DeviceFlowExpiredError("Device code expired.")
            if error == _ERROR_ACCESS_DENIED:
                raise DeviceFlowDeniedError("Login was denied.")
            raise DeviceFlowError(
                f"Unexpected response from device/token: "
                f"HTTP {response.status_code} ({error or 'no error code'})"
            )


async def _real_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _extract_error(response: httpx.Response) -> str | None:
    """Best-effort read of RFC 6749 SS5.2's `{"error": "<code>"}` body shape."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        error = body.get("error")
        return error if isinstance(error, str) else None
    return None
