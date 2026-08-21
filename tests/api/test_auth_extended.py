"""Extended Authentication Tests.

Tests for password reset, email confirmation, profile management, and
session management. Includes regression tests for security fix.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.models import (
    create_user,
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)
from quart import Quart


@pytest.mark.usefixtures("app_context")
class TestRefreshTokenSecurity:
    """Regression tests for security fix: refresh token expiration + revocation.

    Security fix (commit 6e739dda):
    - is_refresh_token_valid() now checks expires_at > datetime.utcnow()
    - is_refresh_token_valid() uses '== False' instead of 'is False' (E712)
    """

    @pytest.mark.asyncio
    async def test_expired_refresh_token_rejected(self) -> None:
        """Regression: expired-but-unrevoked token must be rejected.

        Previously: is_refresh_token_valid() lacked expiration check,
        allowing expired tokens to pass validation.
        """
        user = await create_user(
            email="expired@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
        assert user is not None
        assert user is not None
        user_id: int = user["id"]

        refresh_token = "test-refresh-token-expired"
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        now = datetime.now(UTC)
        expired_at = now - timedelta(hours=1)

        await store_refresh_token(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expired_at,
        )

        is_valid = await is_refresh_token_valid(user_id, token_hash)
        assert not is_valid

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_rejected(self) -> None:
        """Regression: revoked token must be rejected (E712 fix)."""
        user = await create_user(
            email="revoked@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
        assert user is not None
        user_id: int = user["id"]

        refresh_token = "test-refresh-token-revoked"
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        now = datetime.now(UTC)
        future_at = now + timedelta(hours=24)

        await store_refresh_token(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=future_at,
        )

        is_valid_before = await is_refresh_token_valid(user_id, token_hash)
        assert is_valid_before

        await revoke_refresh_token(token_hash)

        is_valid_after = await is_refresh_token_valid(user_id, token_hash)
        assert not is_valid_after

    @pytest.mark.asyncio
    async def test_valid_refresh_token_accepted(self) -> None:
        """Valid token should be accepted."""
        user = await create_user(
            email="valid@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
        assert user is not None
        user_id: int = user["id"]

        refresh_token = "test-refresh-token-valid"
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        now = datetime.now(UTC)
        future_at = now + timedelta(hours=24)

        await store_refresh_token(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=future_at,
        )

        is_valid = await is_refresh_token_valid(user_id, token_hash)
        assert is_valid


class TestForgotPasswordTokenLeak:
    """Regression: /forgot-password must leak neither the token nor user existence.

    Vulnerability: the endpoint returned
    ``{"message": "Reset link sent", "token": ..., "expires_at": ...}`` for a
    registered address, so any unauthenticated caller could name a victim's
    email, receive their live reset token, and complete /reset-password —
    full account takeover. The not-found branch returned a *different*
    message, which additionally made the endpoint a user-enumeration oracle.

    An earlier attempt corrected only the response *shape* (unpacking the
    ``(token, expires_at)`` tuple instead of serialising it) and kept the
    leak, so these tests assert on the exact field set rather than on the
    body merely being well-formed.
    """

    #: Every key the response is permitted to carry. Asserted as an exact
    #: set, not with ``in``/``not in`` alone: an extra field — a re-added
    #: token, an ``expires_at``, a debug aid — must fail loudly here rather
    #: than slip past a check that only looks for the two known-bad names.
    ACK_FIELDS = {"message"}

    @pytest.mark.asyncio
    async def test_known_and_unknown_email_get_identical_response(self, client: Any) -> None:
        """A registered address is indistinguishable from an unregistered one.

        Covers both halves of the vulnerability at once: byte-identical
        bodies mean no enumeration oracle, and the exact-field-set assertion
        means no token or expiry rode along.
        """
        known_email = f"leak-known-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": known_email,
                "password": "testpass123",
                "full_name": "Leak Known",
            },
        )
        assert register.status_code in (200, 201), await register.get_json()

        known = await client.post("/api/v1/auth/forgot-password", json={"email": known_email})
        unknown = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": f"leak-unknown-{uuid.uuid4().hex[:8]}@example.com"},
        )

        assert known.status_code == 200
        assert unknown.status_code == known.status_code
        assert await known.get_data() == await unknown.get_data()

        body = await known.get_json()
        assert set(body) == self.ACK_FIELDS, f"unexpected fields in body: {body}"
        assert "token" not in body
        assert "expires_at" not in body

    @pytest.mark.asyncio
    async def test_reset_token_still_persisted_and_usable(self, client: Any, app: Quart) -> None:
        """The token still reaches the DB, so a legitimately-obtained one works.

        Paired with the rejection test above: suppressing the token from the
        response would also "fix" the leak by breaking password reset
        entirely. This proves the flow still completes end to end for a
        holder who obtained the token out of band.
        """
        email = f"leak-usable-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "testpass123",
                "full_name": "Leak Usable",
            },
        )
        assert register.status_code in (200, 201), await register.get_json()
        user_id = (await register.get_json())["user"]["id"]

        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 200

        async with app.app_context():
            from penguin_dal.quart_ext import get_db

            db = get_db()
            rows = await db(db.password_reset_tokens.user_id == user_id).select()

        assert len(rows) == 1, "forgot-password must still create a reset token"
        token = rows[0]["token"]
        assert token not in (await response.get_data()).decode()

        reset = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "resetpass123"},
        )
        assert reset.status_code == 200, await reset.get_json()

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "resetpass123"},
        )
        assert login.status_code == 200, await login.get_json()


class TestPasswordReset:
    """Test password reset flow."""

    @pytest.mark.asyncio
    async def test_forgot_password_success(self, client: Any) -> None:
        """Test forgot password request."""
        response = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "user@example.com"}
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_user(self, client: Any) -> None:
        """Test forgot password for non-existent user."""
        response = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"}
        )

        # Should not reveal if user exists
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_success(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Test password reset with a genuinely valid token.

        Un-xfailed: POST /auth/reset-password IS implemented (auth.py:801) —
        the original xfail's "not fully implemented" reason was stale. What
        the two literal-string-token variants below actually proved is that
        an invalid token 401s, never that reset itself doesn't work. This
        exercises the real success path with a token minted the same way
        forgot-password mints one.
        """
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])
        email = (await profile.get_json())["email"]

        async with app.app_context():
            from app.auth_features import create_password_reset_token

            token, _expires_at = await create_password_reset_token(user_id)

        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "newpassword123"},
        )
        assert response.status_code == 200

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "newpassword123"},
        )
        assert login.status_code == 200, "new password does not work after reset"

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, client: Any) -> None:
        """An invalid/unknown token is refused -- 401, not 400/404.

        Un-xfailed: reset-password validates the token via
        validate_password_reset_token and answers 401 "Invalid or expired
        token" for anything it cannot find, never 400/404 as the original
        assertion assumed.
        """
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "password": "newpassword123"},
        )

        assert response.status_code == 401
        assert "Invalid or expired token" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_reset_password_weak(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A genuinely valid token still rejects a weak new password.

        Un-xfailed: needs a REAL token to reach the strength check at all —
        the original test's literal "valid-token" string 401'd on token
        validation before ever reaching the password-length branch it meant
        to exercise.
        """
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])

        async with app.app_context():
            from app.auth_features import create_password_reset_token

            token, _expires_at = await create_password_reset_token(user_id)

        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "weak"},
        )

        assert response.status_code == 400
        assert "8" in (await response.get_json())["error"]


class TestEmailConfirmation:
    """Test email confirmation flow."""

    @pytest.mark.asyncio
    async def test_confirm_email_success(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A genuinely valid confirmation token confirms the account.

        Un-xfailed: POST /auth/confirm-email/<token> IS implemented
        (auth.py:826) -- the original xfail's "not fully implemented"
        reason was stale. The literal "invalid-token" string it posted
        could only ever probe the invalid-token branch (below), never the
        success path its name claimed to test.
        """
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])

        async with app.app_context():
            from app.auth_features import create_email_confirmation_token

            token, _expires_at = await create_email_confirmation_token(user_id)

        response = await client.post(f"/api/v1/auth/confirm-email/{token}")
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Email confirmed"

    @pytest.mark.asyncio
    async def test_confirm_email_invalid_token(self, client: Any) -> None:
        """An unknown token is refused -- 401, not 400/404.

        Un-xfailed: validate_email_token finds no row for a token that was
        never issued and confirm_email_endpoint answers 401 "Invalid or
        expired token", never 400/404 as the original assertion assumed.
        """
        response = await client.post("/api/v1/auth/confirm-email/invalid-token")

        assert response.status_code == 401
        assert "Invalid or expired token" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_confirm_email_expired_token(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A token past its expires_at is refused the same as an unknown one.

        Un-xfailed: needs a REAL, expired row -- the original literal
        "expired-token" string was indistinguishable from any other unknown
        token and never actually reached the expiry comparison.
        """
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])

        async with app.app_context():
            from app.models import get_db

            db = get_db()
            token = "already-expired-token"
            await db.email_confirmation_tokens.async_insert(
                user_id=user_id,
                token=token,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )

        response = await client.post(f"/api/v1/auth/confirm-email/{token}")

        assert response.status_code == 401
        assert "Invalid or expired token" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_email_confirmation_required(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test features requiring email confirmation."""
        # Try to use feature before confirming email
        response = await client.get("/api/v1/users/me", headers=auth_headers)

        # Should allow access or restrict based on config
        assert response.status_code in [200, 403]


class TestProfileManagement:
    """Test user profile management."""

    @pytest.mark.asyncio
    async def test_get_own_profile(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test getting own profile."""
        response = await client.get("/api/v1/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert "id" in data
        assert "email" in data
        # users.py get_profile()/update_user() use `full_name`, not `name`
        assert "full_name" in data

    @pytest.mark.asyncio
    async def test_update_profile(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test updating own profile."""
        response = await client.put(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"full_name": "Updated Name", "email": "newemail@example.com"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_change_password_success(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test changing password successfully."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "newpassword123"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test changing password with wrong current password."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={
                "current_password": "wrongpassword",
                "new_password": "newpassword123",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_weak_new(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test changing password with weak new password."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "weak"},
        )

        assert response.status_code == 400


class TestSessionManagement:
    """Test session management endpoints."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test listing active sessions."""
        response = await client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    @pytest.mark.asyncio
    async def test_revoke_session(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test revoking a session."""
        response = await client.delete("/api/v1/auth/sessions/session-id", headers=auth_headers)

        assert response.status_code in [204, 404]

    @pytest.mark.xfail(
        reason="Session endpoints not implemented — Phase 1B",
        strict=False,
    )
    @pytest.mark.asyncio
    async def test_revoke_all_sessions(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test revoking all sessions."""
        response = await client.post(
            "/api/v1/auth/sessions/revoke-all",
            headers=auth_headers,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_session_info_captures_device(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test that session info captures device information."""
        response = await client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        if data["sessions"]:
            session = data["sessions"][0]
            # Should have device/IP info
            assert "device_info" in session or "ip_address" in session
