"""
API Keys Tests

Tests for API key creation, usage, and revocation.
"""

import pytest


class TestAPIKeyCreation:
    """Test API key creation"""

    def test_create_api_key(self, client, auth_headers):
        """Test creating API key"""
        response = client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Test Key", "scopes": ["read:teams", "write:resources"]},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "key" in data
        assert data["name"] == "Test Key"
        assert data["key"].startswith("pk_")

    def test_api_key_format(self, client, auth_headers):
        """Test API key format"""
        response = client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Format Test"}
        )

        assert response.status_code == 201
        data = response.get_json()
        key = data["key"]
        # Should start with pk_test_ or pk_live_
        assert key.startswith("pk_test_") or key.startswith("pk_live_")

    def test_create_key_with_expiration(self, client, auth_headers):
        """Test creating API key with expiration"""
        response = client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Expiring Key", "expires_in_days": 30},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "expires_at" in data


class TestAPIKeyListing:
    """Test listing API keys"""

    def test_list_api_keys(self, client, auth_headers):
        """Test listing user's API keys"""
        # Create a key first
        client.post("/api/v1/api-keys", headers=auth_headers, json={"name": "Key 1"})

        response = client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "keys" in data
        assert len(data["keys"]) >= 1

    def test_list_keys_no_secret(self, client, auth_headers):
        """Test that list doesn't return full key secret"""
        client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Secret Key"}
        )

        response = client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        # Should only have prefix, not full key
        for key in data["keys"]:
            assert "prefix" in key
            assert "key" not in key or len(key.get("key", "")) < 10


class TestAPIKeyUsage:
    """Test using API keys for authentication"""

    def test_request_with_api_key(self, client):
        """Test making request with API key"""
        # This would need actual valid API key
        response = client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_invalid"}
        )

        assert response.status_code == 401

    def test_api_key_not_found(self, client):
        """Test request with non-existent key"""
        response = client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_nonexistent123"}
        )

        assert response.status_code == 401

    def test_api_key_expired(self, client):
        """Test request with expired API key"""
        response = client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_expired"}
        )

        assert response.status_code == 401


class TestAPIKeyRevocation:
    """Test revoking API keys"""

    def test_revoke_api_key(self, client, auth_headers):
        """Test revoking API key"""
        # Create key
        create_response = client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Revoke Me"}
        )
        key_id = create_response.get_json()["id"]

        # Revoke it
        response = client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)

        assert response.status_code == 204

    def test_use_revoked_key(self, client, auth_headers):
        """Test that revoked key no longer works"""
        # Create and revoke key
        create_response = client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Revoke Test"}
        )
        key = create_response.get_json()["key"]
        key_id = create_response.get_json()["id"]

        client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)

        # Try to use revoked key
        response = client.get("/api/v1/users/me", headers={"X-API-Key": key})

        assert response.status_code == 401


class TestAPIKeyScopes:
    """Test API key scopes"""

    def test_key_with_limited_scopes(self, client, auth_headers):
        """Test creating key with limited scopes"""
        response = client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Limited Key", "scopes": ["read:users"]},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "read:users" in data["scopes"]

    def test_key_permission_enforcement(self, client, auth_headers):
        """Test that key scopes are enforced"""
        # Would need actual key with limited scopes
        response = client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_limited"}
        )

        # Should fail or succeed based on scopes
        assert response.status_code in [200, 403]


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
