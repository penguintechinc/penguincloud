"""HTTP-layer tests for the RFC 8628 device authorization grant.

The end-to-end flow this module proves: POST .../device/authorize (no
auth) mints device_code/user_code -> polling before approval gets
authorization_pending -> POST .../device/approve (authenticated) resolves
it -> polling now returns a real token set, claim-shaped exactly like
app.auth.login's -> polling AGAIN after that fails, because device_code is
single-use. The deny path (.../device/deny -> access_denied on the next
poll) is the mirror case. See tests/api/test_device_auth_security.py for
slow_down, rate-limiting, never-log and scope-containment proofs -- this
file is the state machine, that one is the attacker's-eye view.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt
import pytest

DEVICE_PASSWORD = "devicepass123"


async def _register_and_login(client: Any) -> tuple[int, dict[str, str], str]:
    """Register a fresh user, log in, return (user_id, auth headers, email)."""
    email = f"device-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": DEVICE_PASSWORD, "full_name": "Device User"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEVICE_PASSWORD}
    )
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}, email


async def _authorize(client: Any) -> dict[str, Any]:
    """Call .../device/authorize; return the parsed body."""
    response = await client.post("/api/v1/auth/device/authorize", json={})
    assert response.status_code == 200, await response.get_json()
    body: dict[str, Any] = await response.get_json()
    return body


@pytest.mark.asyncio
class TestDeviceAuthorize:
    """POST .../device/authorize -- unauthenticated, mints the pair."""

    async def test_returns_the_full_rfc_8628_envelope(self, client: Any) -> None:
        """Every SS3.2 field is present: device_code, user_code, URIs, expires_in, interval."""
        body = await _authorize(client)
        assert body["device_code"]
        assert body["user_code"]
        assert body["verification_uri"]
        assert body["verification_uri_complete"]
        assert body["expires_in"] == 600
        assert body["interval"] == 5

    async def test_user_code_is_human_typeable_and_grouped(self, client: Any) -> None:
        """RFC 8628 SS5.1 shape: 8 alphanumeric chars, displayed as two dash-joined groups."""
        body = await _authorize(client)
        # RFC 8628 SS5.1 shape: 8 chars from a fixed alphabet, displayed
        # grouped for readability -- "WDGT-BKRP", not a raw 8-char blob.
        code = body["user_code"]
        assert len(code) == 9
        assert code[4] == "-"
        assert code.replace("-", "").isalnum()

    async def test_device_code_and_user_code_are_never_equal(self, client: Any) -> None:
        """Sanity: two independently generated secrets, not one value twice."""
        body = await _authorize(client)
        assert body["device_code"] != body["user_code"]

    async def test_verification_uri_complete_embeds_the_user_code(self, client: Any) -> None:
        """verification_uri_complete lets a CLI print one clickable, pre-filled link."""
        body = await _authorize(client)
        assert body["user_code"] in body["verification_uri_complete"]

    async def test_two_calls_mint_two_distinct_pairs(self, client: Any) -> None:
        """No accidental reuse: each authorize call gets its own secret pair."""
        first = await _authorize(client)
        second = await _authorize(client)
        assert first["device_code"] != second["device_code"]
        assert first["user_code"] != second["user_code"]


@pytest.mark.asyncio
class TestDevicePollBeforeResolution:
    """POST .../device/token before the human has acted."""

    async def test_unresolved_code_is_authorization_pending(self, client: Any) -> None:
        """A fresh device_code with no human action yet is `authorization_pending`."""
        auth = await _authorize(client)
        response = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "authorization_pending"

    async def test_unknown_device_code_is_expired_token(self, client: Any) -> None:
        """A device_code that was never issued gets the same refusal as an expired one."""
        response = await client.post(
            "/api/v1/auth/device/token", json={"device_code": "this-was-never-issued"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "expired_token"

    async def test_empty_device_code_is_invalid_request(self, client: Any) -> None:
        """A blank device_code is a malformed request, not a lookup miss."""
        response = await client.post("/api/v1/auth/device/token", json={"device_code": ""})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "invalid_request"


@pytest.mark.asyncio
class TestDeviceApprove:
    """POST .../device/approve -- authenticated human action."""

    async def test_requires_authentication(self, client: Any) -> None:
        """Approving without a JWT is refused -- there is no identity to bind to."""
        auth = await _authorize(client)
        response = await client.post(
            "/api/v1/auth/device/approve", json={"user_code": auth["user_code"]}
        )
        assert response.status_code == 401

    async def test_approve_with_correct_user_code_succeeds(self, client: Any, app: Any) -> None:
        """The happy path: a logged-in human enters the code the CLI displayed."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        response = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["status"] == "approved"
        assert body["user_code"] == auth["user_code"]

    async def test_unknown_user_code_is_refused(self, client: Any) -> None:
        """A guessed/mistyped user_code with no matching row is refused."""
        _, headers, _ = await _register_and_login(client)
        response = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": "ZZZZ-ZZZZ"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "invalid_user_code"

    async def test_user_code_is_case_and_dash_insensitive(self, client: Any, app: Any) -> None:
        """A human retyping the code with different case/spacing still matches."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        loose = auth["user_code"].lower().replace("-", " ")

        response = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": loose}
        )
        assert response.status_code == 200, await response.get_json()

    async def test_approving_twice_the_second_call_is_refused(self, client: Any, app: Any) -> None:
        """user_code is single-use for approval too -- not just device_code for polling."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        first = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert first.status_code == 200

        second = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert second.status_code == 400
        assert (await second.get_json())["error"] == "invalid_user_code"


@pytest.mark.asyncio
class TestDeviceDeny:
    """POST .../device/deny -- the human rejects the CLI's login attempt."""

    async def test_requires_authentication(self, client: Any) -> None:
        """Denying without a JWT is refused, same as approving without one."""
        auth = await _authorize(client)
        response = await client.post(
            "/api/v1/auth/device/deny", json={"user_code": auth["user_code"]}
        )
        assert response.status_code == 401

    async def test_deny_then_poll_returns_access_denied(self, client: Any, app: Any) -> None:
        """The CLI's very next poll after a denial gets access_denied, never a token."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        deny = await client.post(
            "/api/v1/auth/device/deny", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert deny.status_code == 200
        assert (await deny.get_json())["status"] == "denied"

        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert poll.status_code == 400
        assert (await poll.get_json())["error"] == "access_denied"

    async def test_a_denied_code_cannot_later_be_approved(self, client: Any, app: Any) -> None:
        """Denied is terminal -- a second call cannot flip it to approved."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        await client.post(
            "/api/v1/auth/device/deny", headers=headers, json={"user_code": auth["user_code"]}
        )
        approve = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert approve.status_code == 400
        assert (await approve.get_json())["error"] == "invalid_user_code"


@pytest.mark.asyncio
class TestDeviceTokenIssuance:
    """POST .../device/token after approval -- the actual grant."""

    async def test_approved_poll_returns_a_full_login_shaped_token_set(
        self, client: Any, app: Any
    ) -> None:
        """The token envelope's field set is IDENTICAL to LoginResponse's -- no more, no less."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        user_id, headers, email = await _register_and_login(client)
        auth = await _authorize(client)

        approve = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert approve.status_code == 200

        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert poll.status_code == 200, await poll.get_json()
        body = await poll.get_json()

        # Same envelope shape as app.auth.LoginResponse: access_token,
        # refresh_token, token_type, expires_in, user -- and NOTHING else
        # (no id_token -- see app.auth.LoginResponse's own docstring).
        assert set(body.keys()) == {
            "access_token",
            "refresh_token",
            "token_type",
            "expires_in",
            "user",
        }
        assert body["token_type"] == "Bearer"
        assert body["user"]["id"] == user_id
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "viewer"

    async def test_minted_access_token_authenticates_a_real_route(
        self, client: Any, app: Any
    ) -> None:
        """The device-issued access token is a genuine, usable bearer credential."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        access_token = (await poll.get_json())["access_token"]

        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me.status_code == 200

    async def test_minted_refresh_token_is_usable(self, client: Any, app: Any) -> None:
        """The device-issued refresh token rotates through /auth/refresh like any other."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        refresh_token = (await poll.get_json())["refresh_token"]

        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refreshed.status_code == 200, await refreshed.get_json()

    async def test_token_carries_the_expected_access_token_use_claim(
        self, client: Any, app: Any
    ) -> None:
        """Decoded shape sanity -- device/token mints an ACCESS token, not an id token."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        access_token = (await poll.get_json())["access_token"]
        payload = jwt.decode(access_token, options={"verify_signature": False})
        assert payload["token_use"] == "access"

    async def test_device_code_is_single_use_second_poll_fails(self, client: Any, app: Any) -> None:
        """The core RFC 8628 replay guarantee: one approval, one token, ever."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )

        first_poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert first_poll.status_code == 200
        first_token = (await first_poll.get_json())["access_token"]

        second_poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert second_poll.status_code == 400
        assert (await second_poll.get_json())["error"] == "expired_token"
        # And the replay attempt never even reused the same token value.
        assert "access_token" not in (await second_poll.get_json())
        assert first_token  # the original grant is unaffected by the replay
