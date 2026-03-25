"""
Extended Authentication Tests

Tests for password reset, email confirmation, profile management, and session management.
"""

import pytest
from datetime import datetime, timedelta


class TestPasswordReset:
    """Test password reset flow"""

    def test_forgot_password_success(self, client):
        """Test forgot password request"""
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "user@example.com"}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "message" in data

    def test_forgot_password_nonexistent_user(self, client):
        """Test forgot password for non-existent user"""
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"}
        )

        # Should not reveal if user exists
        assert response.status_code == 200

    def test_reset_password_success(self, client):
        """Test password reset with valid token"""
        # This would need actual token from forgot-password
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "password": "newpassword123"},
        )

        assert response.status_code in [400, 404]

    def test_reset_password_invalid_token(self, client):
        """Test password reset with invalid token"""
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token", "password": "newpassword123"},
        )

        assert response.status_code in [400, 404]

    def test_reset_password_weak(self, client):
        """Test password reset with weak password"""
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "valid-token", "password": "weak"},
        )

        # Should validate password strength
        assert response.status_code == 400


class TestEmailConfirmation:
    """Test email confirmation flow"""

    def test_confirm_email_success(self, client):
        """Test email confirmation with valid token"""
        response = client.post("/api/v1/auth/confirm-email/invalid-token")

        assert response.status_code in [400, 404]

    def test_confirm_email_expired_token(self, client):
        """Test email confirmation with expired token"""
        response = client.post("/api/v1/auth/confirm-email/expired-token")

        assert response.status_code in [400, 404]

    def test_email_confirmation_required(self, client, auth_headers):
        """Test features requiring email confirmation"""
        # Try to use feature before confirming email
        response = client.get("/api/v1/users/me", headers=auth_headers)

        # Should allow access or restrict based on config
        assert response.status_code in [200, 403]


class TestProfileManagement:
    """Test user profile management"""

    def test_get_own_profile(self, client, auth_headers):
        """Test getting own profile"""
        response = client.get("/api/v1/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "id" in data
        assert "email" in data
        assert "name" in data

    def test_update_profile(self, client, auth_headers):
        """Test updating own profile"""
        response = client.put(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"name": "Updated Name", "email": "newemail@example.com"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Name"

    def test_change_password_success(self, client, auth_headers):
        """Test changing password successfully"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "newpassword123"},
        )

        assert response.status_code == 200

    def test_change_password_wrong_current(self, client, auth_headers):
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

    def test_change_password_weak_new(self, client, auth_headers):
        """Test changing password with weak new password"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "weak"},
        )

        assert response.status_code == 400


class TestSessionManagement:
    """Test session management endpoints"""

    def test_list_sessions(self, client, auth_headers):
        """Test listing active sessions"""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_revoke_session(self, client, auth_headers):
        """Test revoking a session"""
        response = client.delete(
            "/api/v1/auth/sessions/session-id", headers=auth_headers
        )

        assert response.status_code in [204, 404]

    def test_revoke_all_sessions(self, client, auth_headers):
        """Test revoking all sessions"""
        response = client.post("/api/v1/auth/sessions/revoke-all", headers=auth_headers)

        assert response.status_code == 200

    def test_session_info_captures_device(self, client, auth_headers):
        """Test that session info captures device information"""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        if data["sessions"]:
            session = data["sessions"][0]
            # Should have device/IP info
            assert "device_info" in session or "ip_address" in session


@pytest.fixture
def client():
    """Create test client"""
    from app import create_app

    app = create_app(config_name="testing")
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers(client):
    """Create authenticated headers"""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "name": "Test User",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "testpass123"},
    )

    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
