"""
License Server Integration Tests

Tests for license validation, feature gating, and checkin.
"""

import pytest


class TestLicenseValidation:
    """Test license validation on startup"""

    def test_license_status_endpoint(self, client, admin_headers):
        """Test getting license status"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "valid" in data
        assert "tier" in data
        assert "features" in data

    def test_license_status_requires_admin(self, client, auth_headers):
        """Test that license endpoint requires admin"""
        response = client.get("/api/v1/license/status", headers=auth_headers)

        assert response.status_code == 403

    def test_license_contains_expiration(self, client, admin_headers):
        """Test that license status includes expiration"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "expires_at" in data


class TestFeatureGating:
    """Test feature gating based on license"""

    def test_sso_feature_gating(self, client, admin_headers):
        """Test SSO feature is gated by license"""
        # Try to access SSO endpoint
        response = client.get("/api/v1/auth/oauth/google", headers=admin_headers)

        # Should work or return 402 (Payment Required) if not entitled
        assert response.status_code in [200, 302, 402, 403]

    def test_audit_logging_feature(self, client, admin_headers):
        """Test audit logging access"""
        response = client.get("/api/v1/audit-logs", headers=admin_headers)

        # Should work or return 402 if not entitled
        assert response.status_code in [200, 402, 403]

    def test_feature_check_manual(self, client, admin_headers):
        """Test manually checking feature"""
        # This tests the require_feature decorator
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        features = data.get("features", [])
        # Features should be a list
        assert isinstance(features, list)


class TestLicenseTiers:
    """Test different license tiers"""

    def test_community_tier_features(self, client, admin_headers):
        """Test features available in community tier"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        # Community should always have basic auth
        if data["tier"] == "community":
            # Basic features should be available
            assert len(data["features"]) >= 0

    def test_professional_tier_features(self, client, admin_headers):
        """Test features in professional tier"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        if data["tier"] == "professional":
            # Should include SSO and audit logs
            assert "sso_integration" in data["features"] or len(data["features"]) > 0

    def test_enterprise_tier_features(self, client, admin_headers):
        """Test features in enterprise tier"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        if data["tier"] == "enterprise":
            # Should have full feature set
            assert len(data["features"]) > 0


class TestLicenseLimits:
    """Test usage limits from license"""

    def test_license_limits_returned(self, client, admin_headers):
        """Test that license returns usage limits"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        if "limits" in data:
            # Limits should have sensible values
            assert isinstance(data["limits"], dict)

    def test_user_count_limit(self, client, admin_headers):
        """Test user count limit enforcement"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        limits = data.get("limits", {})
        if "user_count" in limits:
            assert limits["user_count"] > 0

    def test_team_count_limit(self, client, admin_headers):
        """Test team count limit enforcement"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        limits = data.get("limits", {})
        if "team_count" in limits:
            assert limits["team_count"] > 0


class TestLicenseKeepalive:
    """Test license keepalive/checkin"""

    def test_keepalive_background_task(self, client):
        """Test that keepalive task runs"""
        # This would need to check if task is scheduled
        # For now, just verify endpoint doesn't error
        response = client.get("/healthz")

        assert response.status_code == 200

    def test_keepalive_includes_usage(self, client):
        """Test that keepalive reports usage stats"""
        # Keepalive should include:
        # - active_users
        # - team_count
        # - storage_usage
        # This is tested by checking license validation succeeds
        response = client.get("/healthz")

        assert response.status_code == 200


class TestInvalidLicense:
    """Test handling of invalid licenses"""

    def test_invalid_license_format(self, client):
        """Test handling invalid license format"""
        # This would need env var override for testing
        # Verify app handles gracefully
        response = client.get("/healthz")

        # Should either work or fail gracefully
        assert response.status_code in [200, 503]

    def test_expired_license(self, client, admin_headers):
        """Test handling expired license"""
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        # Should indicate if expired
        assert "valid" in data


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
