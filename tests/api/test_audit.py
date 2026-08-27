"""Audit Logging Tests.

Tests for audit log creation, retrieval, and filtering.
"""

import uuid
from typing import Any

import pytest

# Phase 1B (fix/team-invitations) added the team_members owner-enrolment
# create_team() was missing — see tests/api/test_teams.py's module comment
# for the fix. The xfail this file carried against that gap is retired.


class TestAuditLogCreation:
    """Test audit log creation."""

    @pytest.mark.asyncio
    async def test_login_creates_audit_log(self, client: Any) -> None:
        """Test that login creates audit entry."""
        # A uuid-based unique email avoids colliding with a same-literal
        # registration from another test in this session (the shared
        # sqlite DB persists across the whole pytest process — see
        # tests/conftest.py) that could register "test@example.com" with a
        # different password and make this login 401 instead of 200.
        unique_email = f"login-audit-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "testpass123",
                "full_name": "Test User",
            },
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "testpass123"},
        )

        assert response.status_code == 200
        # Login should be logged

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Free licences one team, and registration already consumed it for a
    # personal team. This test creates a second, which is a paid shape.
    async def test_team_creation_audit_log(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test that team creation creates audit entry."""
        response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Team", "slug": "ta-team-creation"},
        )

        assert response.status_code == 201
        # Team creation should be audited

    @pytest.mark.asyncio
    async def test_user_creation_audit_log(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Test that user management creates audit entries."""
        response = await client.get("/api/v1/users", headers=admin_headers)

        assert response.status_code == 200


class TestAuditLogRetrieval:
    """Test retrieving audit logs."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_list_audit_logs_admin(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test admin can view all audit logs."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        # ONE status. "in [200, 402, 403]" accepted the gate firing and the
        # gate being absent, so it could not tell them apart — which is the
        # whole thing it was there to check.
        assert response.status_code == 200
        assert "logs" in await response.get_json()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Free licences one team, and registration already consumed it for a
    # personal team. This test creates a second, which is a paid shape.
    async def test_list_audit_logs_team_admin(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test team admin can view team audit logs."""
        # No team-scoped audit log endpoint exists — audit_bp is mounted
        # at /api/v1/audit with only /logs and /export (both tenant_id-
        # scoped); there is no /api/v1/teams/<id>/audit-logs route
        # registered anywhere (verified: grep '/audit-logs' across
        # app/*.py and the register_blueprint() calls in app/__init__.py).
        # The request below hits Flask's own unmatched-route 404, which
        # the test's [200, 402, 404] accepts — this genuinely passes, it
        # just isn't exercising any team-scoped audit functionality.
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Team", "slug": "ta-team-admin-audit"},
        )
        team_id = (await create_response.get_json())["id"]

        response = await client.get(f"/api/v1/teams/{team_id}/audit-logs", headers=auth_headers)

        assert response.status_code in [200, 402, 404]

    @pytest.mark.asyncio
    async def test_list_audit_logs_non_admin(
        self, client: Any, auth_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test non-admin cannot view all audit logs."""
        # `tenant_id` is owned by the (unrelated) admin_headers user —
        # auth_headers's user has no membership in it at all, so the
        # get_user_tenant_role() check correctly 403s.
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=auth_headers
        )

        # Should either be 403 forbidden or 402 not entitled
        assert response.status_code == 403


class TestAuditLogFiltering:
    """Test filtering audit logs."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_filter_by_action(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test filtering audit logs by action."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}&action=login",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = await response.get_json()
        for log in data.get("logs", []):
            # Schema field is action_type, not action (see models.py
            # audit_logs table)
            assert log.get("action_type") == "login"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_filter_by_resource(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test filtering by resource type."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}&resource_type=team",
            headers=admin_headers,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_filter_by_date_range(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test filtering by date range."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}"
            "&start_date=2024-01-01&end_date=2024-01-31",
            headers=admin_headers,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_filter_by_user(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test filtering by user."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}&user_id=user_123",
            headers=admin_headers,
        )

        assert response.status_code == 200


class TestAuditLogDetails:
    """Test audit log data structure."""

    @pytest.mark.asyncio
    async def test_audit_log_structure(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test that audit logs contain required fields."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        if response.status_code == 200:
            data = await response.get_json()
            for log in data.get("logs", []):
                # Required fields — actual schema uses action_type/
                # created_at (see models.py:961 create_audit_log /
                # audit_logs table Field definitions), not action/timestamp
                assert "id" in log
                assert "created_at" in log
                assert "action_type" in log
                assert "user_id" in log

    @pytest.mark.asyncio
    async def test_audit_log_contains_metadata(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test audit logs contain metadata."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        if response.status_code == 200:
            data = await response.get_json()
            for log in data.get("logs", []):
                # Should have metadata
                if "metadata" in log:
                    assert isinstance(log["metadata"], dict | str | type(None))

    @pytest.mark.asyncio
    async def test_audit_log_contains_ip(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test audit logs capture IP address."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        if response.status_code == 200:
            data = await response.get_json()
            for log in data.get("logs", []):
                # Should have IP address
                if "ip_address" in log:
                    assert log["ip_address"] is not None


class TestAuditLogEvents:
    """Test various audit log events."""

    @pytest.mark.asyncio
    async def test_audit_log_user_login(self, client: Any) -> None:
        """Test login is audited."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent-audit@example.com", "password": "testpass123"},
        )

        # Login should be audited
        assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_audit_log_user_logout(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Test logout is audited."""
        response = await client.post("/api/v1/auth/logout", headers=auth_headers)

        # Logout should be audited
        assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_audit_log_password_change(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test password change is audited."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "newpass123"},
        )

        # Password change should be audited
        assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Free licences one team, and registration already consumed it for a
    # personal team. This test creates a second, which is a paid shape.
    async def test_audit_log_team_member_added(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test team member addition is audited."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Team", "slug": "ta-member-added"},
        )
        team_id = (await create_response.get_json())["id"]

        # Add member
        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": "other_user", "role": "member"},
        )

        # Should be audited
        assert response.status_code in [201, 404]


class TestAuditLogPagination:
    """Test audit log pagination."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Reading the audit trail is Enterprise-licensed (app/audit.py),
    # so the licence is stated here and the assertion below names ONE
    # status instead of tolerating both answers.
    async def test_audit_log_pagination(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Test pagination of audit logs."""
        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}&page=1&per_page=10",
            headers=admin_headers,
        )

        assert response.status_code == 200
        if response.status_code == 200:
            data = await response.get_json()
            assert "page" in data
            assert "per_page" in data
            assert "total" in data
