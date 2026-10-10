"""End-to-end: the real HTTP routes refuse once over limit, not just `check()`.

test_ratelimit.py proves app.ratelimit's counter logic in isolation;
test_credential_routes_are_rate_limited.py proves every credential-
accepting route CARRIES the decorator. Neither drives an actual request
through the wired route, which is the gap a decorator with a typo'd bucket
name or a swallowed exception could hide behind. These tests do.

Windows are tightened via monkeypatch (not the production defaults) so
each test stays fast and self-contained; `_clear_ratelimit_state` in
conftest.py resets the module's counters before AND after every test, so
this file cannot leak attempts into -- or inherit them from -- any other
test in the suite.
"""

from __future__ import annotations

import uuid
from typing import Any

import pyotp
import pytest
from app import ratelimit

PASSWORD = "testpass123"


def _set_account_window(
    monkeypatch: pytest.MonkeyPatch, bucket: str, attempts: int, seconds: int
) -> None:
    """Shorthand for overriding one bucket's account-scoped window for a test."""
    monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


def _set_ip_window(
    monkeypatch: pytest.MonkeyPatch, bucket: str, attempts: int, seconds: int
) -> None:
    """Shorthand for overriding one bucket's IP-scoped window for a test."""
    monkeypatch.setitem(ratelimit._IP_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


async def _register_and_login(client: Any) -> tuple[str, dict[str, str]]:
    email = f"ratelimit-e2e-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Rate Limit E2E"},
    )
    assert register.status_code == 201, await register.get_json()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_login_refuses_with_429_once_the_account_window_is_exhausted(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated wrong-password attempts against ONE account trip the account window."""
    _set_account_window(monkeypatch, "login", attempts=3, seconds=300)
    email, _ = await _register_and_login(client)
    # _register_and_login's own successful login already consumed one slot
    # of the "login" account window for this address -- clear it so the
    # loop below starts from a known-fresh budget for what THIS test
    # actually exercises.
    ratelimit.clear_local_state()

    for _ in range(3):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert blocked.status_code == 429
    body = await blocked.get_json()
    assert body["error"] == "rate_limited"

    # The account is locked even with the CORRECT password -- the limiter
    # gates on attempt count, not correctness, exactly as it must to stop
    # a TOTP/password brute force.
    still_blocked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert still_blocked.status_code == 429


@pytest.mark.asyncio
async def test_login_account_lockout_does_not_affect_a_different_account(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locked-out account never throttles a bystander sharing the same test-client IP."""
    _set_account_window(monkeypatch, "login", attempts=1, seconds=300)
    victim_email, _ = await _register_and_login(client)
    bystander_email, _ = await _register_and_login(client)
    # Both setup logins already consumed their own account's one-attempt
    # budget -- see the sibling test above for why this is cleared here.
    ratelimit.clear_local_state()

    await client.post("/api/v1/auth/login", json={"email": victim_email, "password": "wrong"})
    locked = await client.post(
        "/api/v1/auth/login", json={"email": victim_email, "password": "wrong"}
    )
    assert locked.status_code == 429

    bystander = await client.post(
        "/api/v1/auth/login", json={"email": bystander_email, "password": PASSWORD}
    )
    assert bystander.status_code == 200


async def _enable_mfa(client: Any, headers: dict[str, str]) -> str:
    """Drive the real setup -> verify flow; return the TOTP secret."""
    setup = await client.post("/api/v1/mfa/setup", headers=headers)
    assert setup.status_code == 200, await setup.get_json()
    secret: str = (await setup.get_json())["secret"]

    totp = pyotp.TOTP(secret)
    verify = await client.post("/api/v1/mfa/verify", headers=headers, json={"code": totp.now()})
    assert verify.status_code == 200, await verify.get_json()
    return secret


@pytest.mark.asyncio
async def test_mfa_disable_refuses_with_429_once_the_account_window_is_exhausted(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact threat named in the brief: guessing a 6-digit TOTP code.

    ``mfa/disable`` re-verifies both password AND TOTP -- wrong TOTP with
    the RIGHT password, repeated, is the brute-force this bucket exists to
    stop regardless of which secret an attacker already holds.
    """
    _set_account_window(monkeypatch, "mfa_disable", attempts=3, seconds=300)
    _, headers = await _register_and_login(client)
    await _enable_mfa(client, headers)

    for _ in range(3):
        response = await client.post(
            "/api/v1/mfa/disable",
            headers=headers,
            json={"password": PASSWORD, "code": "000000"},
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/mfa/disable",
        headers=headers,
        json={"password": PASSWORD, "code": "000000"},
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_registration_ip_window_refuses_once_exhausted(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1's server-side open door is still F2's rate-limited target."""
    _set_ip_window(monkeypatch, "register", attempts=2, seconds=3600)

    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"reg-flood-{uuid.uuid4().hex[:8]}@example.com",
                "password": PASSWORD,
                "full_name": "Flood",
            },
        )
        assert response.status_code == 201

    blocked = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"reg-flood-{uuid.uuid4().hex[:8]}@example.com",
            "password": PASSWORD,
            "full_name": "Flood",
        },
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_change_password_refuses_with_429_once_the_account_window_is_exhausted(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PUT /users/me/password -- found by the derived guard, not the brief."""
    _set_account_window(monkeypatch, "change_password", attempts=2, seconds=300)
    _, headers = await _register_and_login(client)

    for _ in range(2):
        response = await client.put(
            "/api/v1/users/me/password",
            headers=headers,
            json={"current_password": "wrong", "new_password": "irrelevant123"},
        )
        assert response.status_code == 401

    blocked = await client.put(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "irrelevant123"},
    )
    assert blocked.status_code == 429
