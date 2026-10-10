"""Remaining validation-chain branches in app/auth.py.

Not reached by test_auth.py / test_auth_extended.py / test_auth_refresh.py --
login, register, forgot-password, reset-password, and revoke-session's plain
missing-field/not-found checks. None of these needed a real body in any
existing test, so the "field absent" side of each check had never run.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


class TestLoginValidation:
    """POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(self, client: Any) -> None:
        """No JSON body at all -> 400."""
        response = await client.post("/api/v1/auth/login")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_password_is_rejected(self, client: Any) -> None:
        """A body present but missing password 400s, distinct from a wrong one."""
        response = await client.post("/api/v1/auth/login", json={"email": "someone@example.com"})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Email and password required"

    @pytest.mark.asyncio
    async def test_deactivated_account_cannot_login(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A correct password on a deactivated account is refused.

        Not treated as a bad-credentials 401 with the SAME message -- this
        route deliberately DOES disclose deactivation (unlike a generic
        "invalid credentials"), so pin the exact wording.
        """
        email = f"deactivate-login-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "testpass123", "full_name": "Soon Deactivated"},
        )
        assert register.status_code in (200, 201)
        user_id = (await register.get_json())["user"]["id"]

        deactivate = await client.put(
            f"/api/v1/users/{user_id}", headers=admin_headers, json={"is_active": False}
        )
        assert deactivate.status_code == 200

        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Account is deactivated"


class TestRegisterValidation:
    """POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(self, client: Any) -> None:
        """No JSON body at all -> 400."""
        response = await client.post("/api/v1/auth/register")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_email_is_rejected(self, client: Any) -> None:
        """A body present but with no email 400s."""
        response = await client.post(
            "/api/v1/auth/register", json={"password": "a-sufficiently-long-password"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Email is required"


class TestForgotPasswordValidation:
    """POST /api/v1/auth/forgot-password."""

    @pytest.mark.asyncio
    async def test_missing_email_is_rejected(self, client: Any) -> None:
        """No email in the body 400s before any lookup or email send."""
        response = await client.post("/api/v1/auth/forgot-password", json={})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Email required"


class TestResetPasswordValidation:
    """POST /api/v1/auth/reset-password."""

    @pytest.mark.asyncio
    async def test_missing_token_or_password_is_rejected(self, client: Any) -> None:
        """A body missing either field 400s before any token lookup."""
        response = await client.post("/api/v1/auth/reset-password", json={"token": "some-token"})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Token and password required"


class TestRevokeSessionValidation:
    """DELETE /api/v1/auth/sessions/<id>."""

    @pytest.mark.asyncio
    async def test_nonexistent_session_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A session that isn't the caller's (or doesn't exist) 404s.

        Reports not-found rather than a false success.
        """
        response = await client.delete("/api/v1/auth/sessions/999999999", headers=auth_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Session not found"
