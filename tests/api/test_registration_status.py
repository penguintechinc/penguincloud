"""``GET /api/v1/registration-status`` — the sign-up button's data source.

``Login.tsx`` hardcoded ``showSignUp={false}`` regardless of
``Config.ALLOW_SELF_REGISTRATION``, so an operator who turned self-service
signup ON saw no change in the UI — the only way to register was calling
``POST /api/v1/auth/register`` directly. The server-side default (closed) was
always correct; this endpoint is what lets the client-side control agree
with it in both directions.

Unauthenticated on purpose: a visitor deciding whether to look for a
sign-up button has no token by definition. The tests below prove both halves
of that design — reachable with NO Authorization header, AND narrowly
scoped to the one boolean (never widening into a second unauthenticated
``/features``).
"""

from __future__ import annotations

from typing import Any

import pytest
from quart import Quart


@pytest.mark.asyncio
async def test_reachable_with_no_authorization_header(client: Any) -> None:
    """The whole point: a visitor with no token can still call this."""
    response = await client.get("/api/v1/registration-status")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reports_true_when_registration_is_open(
    client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag flips on when ALLOW_SELF_REGISTRATION is on."""
    monkeypatch.setitem(app.config, "ALLOW_SELF_REGISTRATION", True)

    response = await client.get("/api/v1/registration-status")

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"self_registration_enabled": True}


@pytest.mark.asyncio
async def test_reports_false_when_registration_is_closed(
    client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag stays off when ALLOW_SELF_REGISTRATION is off (the default)."""
    monkeypatch.setitem(app.config, "ALLOW_SELF_REGISTRATION", False)

    response = await client.get("/api/v1/registration-status")

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"self_registration_enabled": False}


@pytest.mark.asyncio
async def test_the_answer_matches_what_register_actually_does(
    client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-vacuity: the flag genuinely drives both the button AND the API.

    The two halves of the original defect (the button and the server) had
    drifted apart. This proves they now describe the SAME deployment state
    rather than two independently-plausible ``True``/``False`` values —
    when the status endpoint says open, registration actually succeeds;
    when it says closed, the server actually refuses.
    """
    monkeypatch.setitem(app.config, "ALLOW_SELF_REGISTRATION", False)
    status_response = await client.get("/api/v1/registration-status")
    assert (await status_response.get_json())["self_registration_enabled"] is False

    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": "closed-deploy@example.com", "password": "a-long-enough-password"},
    )
    assert register_response.status_code == 403
    assert (await register_response.get_json())["error"] == "registration_disabled"

    monkeypatch.setitem(app.config, "ALLOW_SELF_REGISTRATION", True)
    status_response = await client.get("/api/v1/registration-status")
    assert (await status_response.get_json())["self_registration_enabled"] is True

    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": "open-deploy@example.com", "password": "a-long-enough-password"},
    )
    assert register_response.status_code in (200, 201)


@pytest.mark.asyncio
async def test_exposes_exactly_this_one_boolean(client: Any) -> None:
    """No general unauthenticated config dump.

    The scope-creep risk this route's docstring names. Pins the response
    shape to a single key so a future edit that starts smuggling
    flags/tier/licensing data onto this route (rather than keeping that
    behind the authenticated ``/features``) fails here first.
    """
    response = await client.get("/api/v1/registration-status")

    body = await response.get_json()
    assert set(body) == {"self_registration_enabled"}
