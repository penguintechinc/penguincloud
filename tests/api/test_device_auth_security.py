"""Security properties of the RFC 8628 device authorization grant.

Five claims, each with its own class:

* **slow_down is enforced from a column this service writes, not from
  anything the client claims** -- proven by directly rewinding the stored
  ``last_polled_at`` timestamp rather than sleeping, and confirming a poll
  that arrives "too fast" by the WALL CLOCK still succeeds once the STORED
  timestamp says enough time has passed.
* **expiry wins even over a successful approval** -- an approved-but-
  expired device_code must never yield a token.
* **every credential-accepting route in this module is genuinely rate
  limited**, end-to-end through the real route (not just the decorator's
  presence -- see tests/api/test_credential_routes_are_rate_limited.py for
  that half), and approve/deny share ONE budget.
* **nothing here is ever logged** -- device_code, user_code, access_token
  and refresh_token, across authorize/approve/token, using the same
  recording-logger technique as tests/api/test_password_reset_delivery.py
  (see that module's docstring for why caplog would pass vacuously here).
* **the minted grant is scope/tenant-identical to a normal login for the
  SAME user, resolved FRESH at poll time** -- a device grant is never
  broader than what the approving account could get by logging in itself,
  and a user deactivated between approval and polling gets refused rather
  than replaying a stale grant.

tests/api/test_device_auth_flow.py covers the state machine itself
(authorize/approve/deny/token, single-use). This file is the attacker's-
eye view of the same four routes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from app import device_auth, ratelimit
from quart import Quart

PASSWORD = "devicesecuritytest123"


def _set_account_window(
    monkeypatch: pytest.MonkeyPatch, bucket: str, attempts: int, seconds: int
) -> None:
    monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


def _set_ip_window(
    monkeypatch: pytest.MonkeyPatch, bucket: str, attempts: int, seconds: int
) -> None:
    monkeypatch.setitem(ratelimit._IP_WINDOWS, bucket, ratelimit._Window(attempts, seconds))


class _RecordingLogger:
    """Fake structlog BoundLogger: records event name + kwargs per call.

    Identical technique to tests/api/test_password_reset_delivery.py's own
    -- see that module's docstring for why this, not caplog: app.device_
    auth's `log` is built the same way app.auth's is (structlog with no
    configure_logging() call site anywhere in this service), so caplog's
    stdlib handler chain never sees these calls at all.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("info", event, kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("warning", event, kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        self.calls.append(("error", event, kwargs))

    def blob(self) -> str:
        return str(self.calls)


async def _register_and_login(client: Any, **overrides: Any) -> tuple[int, dict[str, str], str]:
    email = overrides.get("email") or f"device-sec-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Device Security"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}, email


async def _authorize(client: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/auth/device/authorize", json={})
    assert response.status_code == 200
    body: dict[str, Any] = await response.get_json()
    return body


async def _row_by_device_code(app: Quart, device_code: str) -> dict[str, Any]:
    """Reach into the DB directly for the stored row -- test-only shortcut."""
    async with app.app_context():
        from app.models import get_db

        db = get_db()
        digest = hashlib.sha256(device_code.encode("utf-8")).hexdigest()
        rows = await db(db.device_authorizations.device_code_hash == digest).select()
        assert rows, "device authorization row not found"
        return dict(rows[0])


async def _rewind_last_polled_at(app: Quart, row_id: int, seconds_ago: int) -> None:
    """Directly set last_polled_at into the past -- avoids a real sleep()."""
    async with app.app_context():
        from app.models import get_db

        db = get_db()
        await db(db.device_authorizations.id == row_id).update(
            last_polled_at=datetime.now(UTC) - timedelta(seconds=seconds_ago)
        )


async def _rewind_expires_at(app: Quart, row_id: int, seconds_ago: int) -> None:
    """Directly set expires_at into the past -- avoids waiting out a 600s TTL."""
    async with app.app_context():
        from app.models import get_db

        db = get_db()
        await db(db.device_authorizations.id == row_id).update(
            expires_at=datetime.now(UTC) - timedelta(seconds=seconds_ago)
        )


@pytest.mark.asyncio
class TestSlowDownIsServerEnforced:
    """RFC 8628 SS3.5 slow_down -- from the STORED timestamp, never the client's clock."""

    async def test_immediate_repoll_is_slowed_down(self, client: Any, app: Quart) -> None:
        """A second poll before `interval` seconds have passed gets slow_down."""
        auth = await _authorize(client)
        first = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert first.status_code == 400
        assert (await first.get_json())["error"] == "authorization_pending"

        immediately_again = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert immediately_again.status_code == 400
        assert (await immediately_again.get_json())["error"] == "slow_down"

    async def test_a_poll_far_enough_after_the_stored_timestamp_is_not_slowed(
        self, client: Any, app: Quart
    ) -> None:
        """Rewinding the STORED timestamp (no sleep) proves the check reads it, not the clock."""
        auth = await _authorize(client)
        first = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert first.status_code == 400

        row = await _row_by_device_code(app, auth["device_code"])
        await _rewind_last_polled_at(app, row["id"], seconds_ago=999)

        second = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert second.status_code == 400
        assert (await second.get_json())["error"] == "authorization_pending"

    async def test_slow_down_also_applies_to_an_already_approved_code(
        self, client: Any, app: Quart
    ) -> None:
        """A client hammering an approved-but-unpolled code is still throttled."""
        app.config["DEVICE_POLL_INTERVAL"] = 5
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        # A pending poll first, so last_polled_at is set.
        await client.post("/api/v1/auth/device/token", json={"device_code": auth["device_code"]})

        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )

        immediately_again = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert immediately_again.status_code == 400
        assert (await immediately_again.get_json())["error"] == "slow_down"


@pytest.mark.asyncio
class TestExpiryWinsOverApproval:
    """An approved-but-expired device_code must never yield a token."""

    async def test_expired_pending_code_is_expired_token(self, client: Any, app: Quart) -> None:
        """A code past its TTL is expired_token, whether or not it was ever approved."""
        auth = await _authorize(client)
        row = await _row_by_device_code(app, auth["device_code"])
        await _rewind_expires_at(app, row["id"], seconds_ago=1)

        response = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "expired_token"

    async def test_expired_but_approved_code_never_yields_a_token(
        self, client: Any, app: Quart
    ) -> None:
        """Even a genuinely approved grant is refused once its TTL has elapsed."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        approve = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert approve.status_code == 200

        row = await _row_by_device_code(app, auth["device_code"])
        assert row["status"] == "approved"
        await _rewind_expires_at(app, row["id"], seconds_ago=1)

        response = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert response.status_code == 400
        body = await response.get_json()
        assert body["error"] == "expired_token"
        assert "access_token" not in body

    async def test_expired_user_code_cannot_be_approved(self, client: Any, app: Quart) -> None:
        """The human-facing approval step honors the same TTL as the poll step."""
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        row = await _row_by_device_code(app, auth["device_code"])
        await _rewind_expires_at(app, row["id"], seconds_ago=1)

        response = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "invalid_user_code"


@pytest.mark.asyncio
class TestRateLimiting:
    """End-to-end through the real routes -- not just the decorator's presence.

    See tests/api/test_credential_routes_are_rate_limited.py for the
    structural proof that every route here CARRIES the decorator; this
    class proves the decorator actually refuses once triggered, tightening
    windows via monkeypatch so each test stays fast (same technique as
    tests/api/test_credential_endpoints_enforce_rate_limits.py).
    """

    async def test_device_authorize_ip_window_refuses_with_429(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Minting device_code/user_code pairs is bounded per source IP."""
        _set_ip_window(monkeypatch, "device_authorize", attempts=2, seconds=300)

        for _ in range(2):
            response = await client.post("/api/v1/auth/device/authorize", json={})
            assert response.status_code == 200

        blocked = await client.post("/api/v1/auth/device/authorize", json={})
        assert blocked.status_code == 429
        assert (await blocked.get_json())["error"] == "rate_limited"

    async def test_device_token_ip_window_refuses_with_429(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Polling is bounded per source IP, independent of slow_down's per-device_code check."""
        _set_ip_window(monkeypatch, "device_token", attempts=2, seconds=300)
        auth = await _authorize(client)

        for _ in range(2):
            response = await client.post(
                "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
            )
            assert response.status_code == 400  # authorization_pending / slow_down

        blocked = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert blocked.status_code == 429

    async def test_device_approve_account_window_refuses_with_429(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """user_code guessing against ONE approving account is bounded."""
        _set_account_window(monkeypatch, "device_approve", attempts=3, seconds=300)
        _, headers, _ = await _register_and_login(client)
        ratelimit.clear_local_state()

        for _ in range(3):
            response = await client.post(
                "/api/v1/auth/device/approve",
                headers=headers,
                json={"user_code": "ZZZZ-ZZZZ"},
            )
            assert response.status_code == 400

        blocked = await client.post(
            "/api/v1/auth/device/approve",
            headers=headers,
            json={"user_code": "ZZZZ-ZZZZ"},
        )
        assert blocked.status_code == 429

    async def test_approve_and_deny_share_one_account_budget(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alternating approve/deny guesses must NOT double the attack budget."""
        _set_account_window(monkeypatch, "device_approve", attempts=4, seconds=300)
        _, headers, _ = await _register_and_login(client)
        ratelimit.clear_local_state()

        routes = [
            "/api/v1/auth/device/approve",
            "/api/v1/auth/device/deny",
            "/api/v1/auth/device/approve",
            "/api/v1/auth/device/deny",
        ]
        for route in routes:
            response = await client.post(route, headers=headers, json={"user_code": "ZZZZ-ZZZZ"})
            assert response.status_code == 400

        blocked = await client.post(
            "/api/v1/auth/device/approve",
            headers=headers,
            json={"user_code": "ZZZZ-ZZZZ"},
        )
        assert blocked.status_code == 429


@pytest.mark.asyncio
class TestNeverLogged:
    """device_code, user_code, and minted tokens must never reach a log call."""

    async def test_authorize_never_logs_the_minted_pair(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The authorize response's own device_code/user_code appear nowhere in a log call."""
        fake_log = _RecordingLogger()
        monkeypatch.setattr(device_auth, "log", fake_log)

        auth = await _authorize(client)

        blob = fake_log.blob()
        assert auth["device_code"] not in blob
        assert auth["user_code"] not in blob
        assert auth["user_code"].replace("-", "") not in blob

    async def test_full_flow_never_logs_any_secret(
        self, client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Across authorize/poll/approve/poll, no log call ever carries a raw secret."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        fake_log = _RecordingLogger()
        monkeypatch.setattr(device_auth, "log", fake_log)

        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post("/api/v1/auth/device/token", json={"device_code": auth["device_code"]})
        approve = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert approve.status_code == 200
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert poll.status_code == 200
        token_body = await poll.get_json()

        blob = fake_log.blob()
        assert auth["device_code"] not in blob
        assert auth["user_code"] not in blob
        assert token_body["access_token"] not in blob
        assert token_body["refresh_token"] not in blob


@pytest.mark.asyncio
class TestDeviceCodeStoredHashed:
    """A DB read must not recover a usable device_code -- same guarantee as refresh_tokens."""

    async def test_raw_device_code_is_not_in_the_stored_row(self, client: Any, app: Quart) -> None:
        """Only the SHA-256 digest is persisted; the raw device_code cannot be recovered."""
        auth = await _authorize(client)
        row = await _row_by_device_code(app, auth["device_code"])
        assert auth["device_code"] not in repr(row)

        expected_hash = hashlib.sha256(auth["device_code"].encode("utf-8")).hexdigest()
        assert row["device_code_hash"] == expected_hash


@pytest.mark.asyncio
class TestGrantIsNeverBroaderThanTheApprovingAccount:
    """The minted token mirrors login for the SAME user -- resolved fresh, never stale."""

    async def test_device_token_claims_match_a_fresh_login_for_the_same_user(
        self, client: Any, app: Quart
    ) -> None:
        """sub/scope/roles/tenant are identical between a device grant and a password login."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        user_id, headers, email = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        device_token = (await poll.get_json())["access_token"]

        fresh_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        login_token = (await fresh_login.get_json())["access_token"]

        device_claims = jwt.decode(device_token, options={"verify_signature": False})
        login_claims = jwt.decode(login_token, options={"verify_signature": False})

        assert device_claims["sub"] == login_claims["sub"] == str(user_id)
        assert sorted(device_claims["scope"]) == sorted(login_claims["scope"])
        assert device_claims["roles"] == login_claims["roles"]
        assert device_claims["tenant"] == login_claims["tenant"]

    async def test_admin_scopes_never_leak_into_a_viewer_approved_grant(
        self, client: Any, app: Quart
    ) -> None:
        """A viewer's own device flow yields viewer scopes -- never platform admin scopes."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        _, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)
        await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        token = (await poll.get_json())["access_token"]
        claims = jwt.decode(token, options={"verify_signature": False})

        assert claims["roles"] == ["viewer"]
        assert "users:manage" not in claims["scope"]
        assert "settings:write" not in claims["scope"]

    async def test_deactivated_user_cannot_claim_an_already_approved_grant(
        self, client: Any, app: Quart
    ) -> None:
        """Scopes/active-status are resolved FRESH at poll time, not cached from approval."""
        app.config["DEVICE_POLL_INTERVAL"] = 0
        user_id, headers, _ = await _register_and_login(client)
        auth = await _authorize(client)

        approve = await client.post(
            "/api/v1/auth/device/approve", headers=headers, json={"user_code": auth["user_code"]}
        )
        assert approve.status_code == 200

        async with app.app_context():
            from app.models import update_user

            await update_user(user_id, is_active=False)

        poll = await client.post(
            "/api/v1/auth/device/token", json={"device_code": auth["device_code"]}
        )
        assert poll.status_code == 400
        body = await poll.get_json()
        assert body["error"] == "access_denied"
        assert "access_token" not in body
