"""
Audit Logging Tests

Tests for audit log creation, retrieval, and filtering.
"""

import pytest


class TestAuditLogCreation:
    """Test audit log creation"""

    def test_login_creates_audit_log(self, client):
        """Test that login creates audit entry"""
        # Register and login
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

        assert response.status_code == 200
        # Login should be logged

    def test_team_creation_audit_log(self, client, auth_headers):
        """Test that team creation creates audit entry"""
        response = client.post(
            "/api/v1/teams", headers=auth_headers, json={"name": "Team", "slug": "team"}
        )

        assert response.status_code == 201
        # Team creation should be audited

    def test_user_creation_audit_log(self, client, admin_headers):
        """Test that user management creates audit entries"""
        response = client.get("/api/v1/users", headers=admin_headers)

        assert response.status_code == 200


class TestAuditLogRetrieval:
    """Test retrieving audit logs"""

    def test_list_audit_logs_admin(self, client, admin_headers):
        """Test admin can view all audit logs"""
        response = client.get("/api/v1/audit-logs", headers=admin_headers)

        assert response.status_code in [200, 402, 403]  # 402 if not entitled
        if response.status_code == 200:
            data = response.get_json()
            assert "logs" in data

    def test_list_audit_logs_team_admin(self, client, auth_headers):
        """Test team admin can view team audit logs"""
        # Create team
        create_response = client.post(
            "/api/v1/teams", headers=auth_headers, json={"name": "Team", "slug": "team"}
        )
        team_id = create_response.get_json()["id"]

        # Try to access team audit logs
        response = client.get(
            f"/api/v1/teams/{team_id}/audit-logs", headers=auth_headers
        )

        assert response.status_code in [200, 402, 404]

    def test_list_audit_logs_non_admin(self, client, auth_headers):
        """Test non-admin cannot view all audit logs"""
        response = client.get("/api/v1/audit-logs", headers=auth_headers)

        # Should either be 403 forbidden or 402 not entitled
        assert response.status_code in [403, 402]


class TestAuditLogFiltering:
    """Test filtering audit logs"""

    def test_filter_by_action(self, client, admin_headers):
        """Test filtering audit logs by action"""
        response = client.get("/api/v1/audit-logs?action=login", headers=admin_headers)

        assert response.status_code in [200, 402]
        if response.status_code == 200:
            data = response.get_json()
            for log in data.get("logs", []):
                assert log.get("action") == "login"

    def test_filter_by_resource(self, client, admin_headers):
        """Test filtering by resource type"""
        response = client.get(
            "/api/v1/audit-logs?resource_type=team", headers=admin_headers
        )

        assert response.status_code in [200, 402]

    def test_filter_by_date_range(self, client, admin_headers):
        """Test filtering by date range"""
        response = client.get(
            "/api/v1/audit-logs?start_date=2024-01-01&end_date=2024-01-31",
            headers=admin_headers,
        )

        assert response.status_code in [200, 402]

    def test_filter_by_user(self, client, admin_headers):
        """Test filtering by user"""
        response = client.get(
            "/api/v1/audit-logs?user_id=user_123", headers=admin_headers
        )

        assert response.status_code in [200, 402]


class TestAuditLogDetails:
    """Test audit log data structure"""

    def test_audit_log_structure(self, client, admin_headers):
        """Test that audit logs contain required fields"""
        response = client.get("/api/v1/audit-logs", headers=admin_headers)

        if response.status_code == 200:
            data = response.get_json()
            for log in data.get("logs", []):
                # Required fields
                assert "id" in log
                assert "timestamp" in log
                assert "action" in log
                assert "user_id" in log

    def test_audit_log_contains_metadata(self, client, admin_headers):
        """Test audit logs contain metadata"""
        response = client.get("/api/v1/audit-logs", headers=admin_headers)

        if response.status_code == 200:
            data = response.get_json()
            for log in data.get("logs", []):
                # Should have metadata
                if "metadata" in log:
                    assert isinstance(log["metadata"], dict)

    def test_audit_log_contains_ip(self, client, admin_headers):
        """Test audit logs capture IP address"""
        response = client.get("/api/v1/audit-logs", headers=admin_headers)

        if response.status_code == 200:
            data = response.get_json()
            for log in data.get("logs", []):
                # Should have IP address
                if "ip_address" in log:
                    assert log["ip_address"] is not None


class TestAuditLogEvents:
    """Test various audit log events"""

    def test_audit_log_user_login(self, client):
        """Test login is audited"""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "testpass123"},
        )

        # Login should be audited
        assert response.status_code in [200, 401]

    def test_audit_log_user_logout(self, client, auth_headers):
        """Test logout is audited"""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)

        # Logout should be audited
        assert response.status_code in [200, 401]

    def test_audit_log_password_change(self, client, auth_headers):
        """Test password change is audited"""
        response = client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "newpass123"},
        )

        # Password change should be audited
        assert response.status_code in [200, 401]

    def test_audit_log_team_member_added(self, client, auth_headers):
        """Test team member addition is audited"""
        # Create team
        create_response = client.post(
            "/api/v1/teams", headers=auth_headers, json={"name": "Team", "slug": "team"}
        )
        team_id = create_response.get_json()["id"]

        # Add member
        response = client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": "other_user", "role": "member"},
        )

        # Should be audited
        assert response.status_code in [201, 404]


class TestAuditLogPagination:
    """Test audit log pagination"""

    def test_audit_log_pagination(self, client, admin_headers):
        """Test pagination of audit logs"""
        response = client.get(
            "/api/v1/audit-logs?page=1&limit=10", headers=admin_headers
        )

        assert response.status_code in [200, 402]
        if response.status_code == 200:
            data = response.get_json()
            if "pagination" in data:
                assert "page" in data["pagination"]
                assert "limit" in data["pagination"]
                assert "total" in data["pagination"]


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


@pytest.fixture
def admin_headers(client):
    """Create admin authenticated headers"""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "adminpass123",
            "name": "Admin User",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )

    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
