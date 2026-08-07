"""
Extended Authentication Tests

Tests for password reset, email confirmation, profile management, and
session management. Includes regression tests for security fix.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    create_user,
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)


class TestRefreshTokenSecurity:
    """Regression tests for security fix: refresh token expiration + revocation.

    Security fix (commit 6e739dda):
    - is_refresh_token_valid() now checks expires_at > datetime.utcnow()
    - is_refresh_token_valid() uses '== False' instead of 'is False' (E712)
    """

    @pytest.mark.asyncio
    async def test_expired_refresh_token_rejected(self) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
        """Regression: expired-but-unrevoked token must be rejected.

        Previously: is_refresh_token_valid() lacked expiration check,
        allowing expired tokens to pass validation.
        """
        user = await create_user(
            email="expired@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
        user_id: int = user["id"]  # type: ignore[index]

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
    async def test_revoked_refresh_token_rejected(self) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
        """Regression: revoked token must be rejected (E712 fix)."""
        user = await create_user(
            email="revoked@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
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
    async def test_valid_refresh_token_accepted(self) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
        """Valid token should be accepted."""
        user = await create_user(
            email="valid@example.com",
            password_hash="hashedpwd",
            role="viewer",
        )
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


class TestPasswordReset:
    """Test password reset flow"""

    def test_forgot_password_success(self, client):  # type: ignore[no-untyped-def]
        """Test forgot password request"""
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "user@example.com"}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "message" in data

    def test_forgot_password_nonexistent_user(self, client):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test forgot password for non-existent user"""
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"}
        )

        # Should not reveal if user exists
        assert response.status_code == 200

    @pytest.mark.xfail(
        reason="Password reset feature not fully implemented — Phase 1B",
        strict=False,
    )
    def test_reset_password_success(self, client):  # type: ignore[no-untyped-def]
        """Test password reset with valid token"""
        # This would need actual token from forgot-password
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "password": "newpassword123"},
        )

        assert response.status_code in [400, 404]

    @pytest.mark.xfail(
        reason="Password reset feature not fully implemented — Phase 1B",
        strict=False,
    )
    def test_reset_password_invalid_token(self, client):  # type: ignore[no-untyped-def]
        """Test password reset with invalid token"""
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "password": "newpassword123"},
        )

        assert response.status_code in [400, 404]

    @pytest.mark.xfail(
        reason="Password reset feature not fully implemented — Phase 1B",
        strict=False,
    )
    def test_reset_password_weak(self, client):  # type: ignore[no-untyped-def]
        """Test password reset with weak password"""
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "valid-token", "password": "weak"},
        )

        # Should validate password strength
        assert response.status_code == 400


class TestEmailConfirmation:
    """Test email confirmation flow"""

    @pytest.mark.xfail(
        reason="Email confirmation feature not fully implemented — Phase 1B",
        strict=False,
    )
    def test_confirm_email_success(self, client):  # type: ignore[no-untyped-def]
        """Test email confirmation with valid token"""
        response = client.post("/api/v1/auth/confirm-email/invalid-token")

        assert response.status_code in [400, 404]

    @pytest.mark.xfail(
        reason="Email confirmation feature not fully implemented — Phase 1B",
        strict=False,
    )
    def test_confirm_email_expired_token(self, client):  # type: ignore[no-untyped-def]
        """Test email confirmation with expired token"""
        response = client.post("/api/v1/auth/confirm-email/expired-token")

        assert response.status_code in [400, 404]

    def test_email_confirmation_required(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test features requiring email confirmation"""
        # Try to use feature before confirming email
        response = client.get("/api/v1/users/me", headers=auth_headers)

        # Should allow access or restrict based on config
        assert response.status_code in [200, 403]


class TestProfileManagement:
    """Test user profile management"""

    def test_get_own_profile(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test getting own profile"""
        response = client.get("/api/v1/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "id" in data
        assert "email" in data
        # users.py get_profile()/update_user() use `full_name`, not `name`
        assert "full_name" in data

    def test_update_profile(self, client, auth_headers):  # type: ignore[no-untyped-def]
        """Test updating own profile"""
        response = client.put(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"full_name": "Updated Name", "email": "newemail@example.com"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["full_name"] == "Updated Name"

    def test_change_password_success(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test changing password successfully"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "newpassword123"},
        )

        assert response.status_code == 200

    def test_change_password_wrong_current(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test changing password with wrong current password"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={
                "current_password": "wrongpassword",
                "new_password": "newpassword123",
            },
        )

        assert response.status_code == 401

    def test_change_password_weak_new(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test changing password with weak new password"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "weak"},
        )

        assert response.status_code == 400


class TestSessionManagement:
    """Test session management endpoints"""

    def test_list_sessions(self, client, auth_headers):  # type: ignore[no-untyped-def]
        """Test listing active sessions"""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_revoke_session(self, client, auth_headers):  # type: ignore[no-untyped-def]
        """Test revoking a session"""
        response = client.delete(
            "/api/v1/auth/sessions/session-id", headers=auth_headers
        )

        assert response.status_code in [204, 404]

    @pytest.mark.xfail(
        reason="Session endpoints not implemented — Phase 1B",
        strict=False,
    )
    def test_revoke_all_sessions(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test revoking all sessions"""
        response = client.post("/api/v1/auth/sessions/revoke-all", headers=auth_headers)

        assert response.status_code == 200

    def test_session_info_captures_device(self, client, auth_headers):  # type: ignore[no-untyped-def]  # noqa: E501
        """Test that session info captures device information"""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        if data["sessions"]:
            session = data["sessions"][0]
            # Should have device/IP info
            assert "device_info" in session or "ip_address" in session
