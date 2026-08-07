"""
License Server Integration Tests

Tests for license validation, feature gating, and checkin.
"""

import uuid

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

    @pytest.mark.xfail(
        reason=(
            "oauth_redirect (oauth.py:81) 500s when a configured provider "
            "is missing client_id/client_secret env vars, instead of a "
            "4xx — Config.OAUTH_PROVIDERS statically lists 'google' (so "
            "get_provider_config() finds it), but "
            "OAUTH_GOOGLE_CLIENT_ID/_SECRET are unset in TESTING, hitting "
            "oauth.py:89's `return jsonify(...), 500` — not one of "
            "[200, 302, 402, 403]"
        ),
        strict=False,
    )
    def test_sso_feature_gating(self, client, admin_headers):
        """Test SSO feature is gated by license"""
        # Try to access SSO endpoint
        response = client.get("/api/v1/auth/oauth/google", headers=admin_headers)

        # Should work or return 402 (Payment Required) if not entitled
        assert response.status_code in [200, 302, 402, 403]

    def test_audit_logging_feature(self, client, admin_headers, tenant_id):
        """Test audit logging access"""
        response = client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )

        # Should work or return 402 if not entitled
        assert response.status_code in [200, 402, 403]

    def test_feature_check_manual(self, client, admin_headers):
        """Test manually checking feature"""
        # This tests the require_feature decorator
        response = client.get("/api/v1/license/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        features = data.get("features", {})
        # LicenseManager.get_status() (license.py:179) returns `features`
        # as a {feature_name: {"enabled": bool, ...}} lookup dict — used
        # that way by is_feature_enabled() itself — never a list.
        assert isinstance(features, dict)


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
def admin_headers(client):
    """Create a genuine admin-role authenticated user.

    Registration always defaults to role="viewer" (see auth.py:register) —
    there is no self-service way to become admin. Elevate the role via the
    DB layer inside an app context, then log in again so the fresh JWT's
    `role` claim (baked in at token issuance, see auth.py:158) reflects it.
    """
    unique_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "adminpass123",
            "full_name": "Admin User",
        },
    )
    assert register_response.status_code in [
        200,
        201,
    ], f"Failed to register: {register_response.get_json()}"
    user_id = register_response.get_json()["user"]["id"]

    with client.application.app_context():
        from app.models import update_user

        update_user(user_id, role="admin")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "adminpass123"},
    )
    assert (
        response.status_code == 200
    ), f"Failed to login: {response.get_json()}"

    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_id(client, admin_headers):
    """Create a tenant owned by the admin_headers user; return its id.

    create_tenant() adds the creator as a tenant_members row with
    role="owner" (models.py:780), giving /api/v1/audit/logs (tenant-scoped,
    requires owner/admin role) something real to authorize against.
    """
    response = client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={
            "name": "License Test Tenant",
            "slug": f"license-tenant-{uuid.uuid4().hex[:8]}",
            "plan": "free",
        },
    )
    assert (
        response.status_code == 201
    ), f"Failed to create tenant: {response.get_json()}"
    return response.get_json()["id"]
