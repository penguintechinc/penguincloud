"""Tests for `pcli.auth.device_flow.DeviceFlowClient` (RFC 8628 client side).

Every test drives an `httpx.MockTransport` -- no real portal -- and injects
`sleep`/`clock` so the poll loop runs instantly rather than for real wall
time.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from pcli.auth.device_flow import DeviceAuthorization, DeviceFlowClient
from pcli.errors import DeviceFlowDeniedError, DeviceFlowError, DeviceFlowExpiredError


def _client(
    handler: Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://portal.example.com", transport=httpx.MockTransport(handler)
    )


def _authorization(*, expires_in: int = 600, interval: int = 5) -> DeviceAuthorization:
    return DeviceAuthorization(
        device_code="device-secret",  # noqa: S106
        user_code="ABCD-EFGH",
        verification_uri="https://portal.example.com/device",
        verification_uri_complete="https://portal.example.com/device?user_code=ABCD-EFGH",
        expires_in=expires_in,
        interval=interval,
    )


class _FakeClock:
    """Deterministic monotonic clock a test advances explicitly."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


async def _no_sleep(seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_authorize_parses_response() -> None:
    """Authorize parses response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/device/authorize"
        return httpx.Response(
            200,
            json={
                "device_code": "dc",
                "user_code": "AB12-CD34",
                "verification_uri": "https://portal.example.com/device",
                "verification_uri_complete": "https://portal.example.com/device?user_code=AB12-CD34",
                "expires_in": 600,
                "interval": 5,
            },
        )

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        authorization = await flow.authorize()
    assert authorization.device_code == "dc"
    assert authorization.interval == 5


@pytest.mark.asyncio
async def test_poll_pending_then_approved() -> None:
    """Poll pending then approved."""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(400, json={"error": "authorization_pending"})
        return httpx.Response(
            200,
            json={
                "access_token": "final-token",
                "refresh_token": "final-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        tokens = await flow.poll_for_token(_authorization(), sleep=_no_sleep, clock=_FakeClock())
    assert calls["n"] == 3
    assert tokens.access_token == "final-token"
    assert tokens.refresh_token == "final-refresh"


@pytest.mark.asyncio
async def test_poll_slow_down_increases_interval_and_eventually_succeeds() -> None:
    """Poll slow down increases interval and eventually succeeds."""
    responses = iter(
        [
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={
                    "access_token": "tok",
                    "refresh_token": "ref",
                    "token_type": "Bearer",
                    "expires_in": 60,
                },
            ),
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    sleep_calls: list[float] = []

    async def recording_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        tokens = await flow.poll_for_token(
            _authorization(interval=5), sleep=recording_sleep, clock=_FakeClock()
        )
    assert tokens.access_token == "tok"
    # First sleep uses the server's original interval (5); after slow_down
    # RFC 8628 SS3.5 requires increasing by >=5s for every subsequent poll.
    assert sleep_calls == [5, 10, 10]


@pytest.mark.asyncio
async def test_poll_expired_token_raises() -> None:
    """Poll expired token raises."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "expired_token"})

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        with pytest.raises(DeviceFlowExpiredError):
            await flow.poll_for_token(_authorization(), sleep=_no_sleep, clock=_FakeClock())


@pytest.mark.asyncio
async def test_poll_access_denied_raises() -> None:
    """Poll access denied raises."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "access_denied"})

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        with pytest.raises(DeviceFlowDeniedError):
            await flow.poll_for_token(_authorization(), sleep=_no_sleep, clock=_FakeClock())


@pytest.mark.asyncio
async def test_poll_local_deadline_expiry_without_a_server_round_trip() -> None:
    """The client-side deadline (`expires_in`) fires even if the server keeps saying pending.

    `expires_in=12`, `interval=5`: the deadline check runs at the TOP of
    each loop iteration (before the next sleep+poll), so it is checked
    against a clock that has already advanced by whole `interval` steps --
    it fires on the first check at/after the deadline, not mid-interval.
    """
    clock = _FakeClock()
    poll_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        poll_count["n"] += 1
        return httpx.Response(400, json={"error": "authorization_pending"})

    async def advancing_sleep(seconds: float) -> None:
        clock.now += seconds

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        with pytest.raises(DeviceFlowExpiredError):
            await flow.poll_for_token(
                _authorization(expires_in=12, interval=5), sleep=advancing_sleep, clock=clock
            )
    # Deadline checks run against the clock value from BEFORE that
    # iteration's own sleep, so polls fire at clock=5, 10, and 15 (all
    # checked as "< 12" at the top of their own iteration); only the 4th
    # iteration's check (clock=15 >= 12) raises -- the deadline is
    # enforced, not merely decorative, it just lags by one interval.
    assert poll_count["n"] == 3


@pytest.mark.asyncio
async def test_poll_unexpected_error_code_raises_device_flow_error() -> None:
    """Poll unexpected error code raises device flow error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "totally_unrecognised"})

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        with pytest.raises(DeviceFlowError):
            await flow.poll_for_token(_authorization(), sleep=_no_sleep, clock=_FakeClock())


@pytest.mark.asyncio
async def test_poll_non_json_error_body_still_raises_device_flow_error() -> None:
    """Poll non json error body still raises device flow error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream on fire")

    async with _client(handler) as http:
        flow = DeviceFlowClient(http)
        with pytest.raises(DeviceFlowError):
            await flow.poll_for_token(_authorization(), sleep=_no_sleep, clock=_FakeClock())
