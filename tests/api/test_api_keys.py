"""
API Keys Tests

Tests for API key creation, usage, and revocation.
"""

from typing import Any

import pytest

# Skip all tests - API key endpoints not implemented on v0.1.x
pytestmark = pytest.mark.skip(
    reason="API key endpoints not implemented on v0.1.x — Phase 1B"
)


class TestAPIKeyCreation:
    """Test API key creation"""

    @pytest.mark.asyncio
    async def test_create_api_key(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test creating API key"""
        response = await client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Test Key", "scopes": ["read:teams", "write:resources"]},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert "key" in data
        assert data["name"] == "Test Key"
        assert data["key"].startswith("pk_")

    @pytest.mark.asyncio
    async def test_api_key_format(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test API key format"""
        response = await client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Format Test"}
        )

        assert response.status_code == 201
        data = await response.get_json()
        key = data["key"]
        # Should start with pk_test_ or pk_live_
        assert key.startswith("pk_test_") or key.startswith("pk_live_")

    @pytest.mark.asyncio
    async def test_create_key_with_expiration(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test creating API key with expiration"""
        response = await client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Expiring Key", "expires_in_days": 30},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert "expires_at" in data


class TestAPIKeyListing:
    """Test listing API keys"""

    @pytest.mark.asyncio
    async def test_list_api_keys(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test listing user's API keys"""
        # Create a key first
        await client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Key 1"}
        )

        response = await client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert "keys" in data
        assert len(data["keys"]) >= 1

    @pytest.mark.asyncio
    async def test_list_keys_no_secret(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test that list doesn't return full key secret"""
        await client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Secret Key"}
        )

        response = await client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        # Should only have prefix, not full key
        for key in data["keys"]:
            assert "prefix" in key
            assert "key" not in key or len(key.get("key", "")) < 10


class TestAPIKeyUsage:
    """Test using API keys for authentication"""

    @pytest.mark.asyncio
    async def test_request_with_api_key(self, client: Any) -> None:
        """Test making request with API key"""
        # This would need actual valid API key
        response = await client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_invalid"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_not_found(self, client: Any) -> None:
        """Test request with non-existent key"""
        response = await client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_nonexistent123"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_expired(self, client: Any) -> None:
        """Test request with expired API key"""
        response = await client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_expired"}
        )

        assert response.status_code == 401


class TestAPIKeyRevocation:
    """Test revoking API keys"""

    @pytest.mark.asyncio
    async def test_revoke_api_key(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test revoking API key"""
        # Create key
        create_response = await client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Revoke Me"}
        )
        key_id = (await create_response.get_json())["id"]

        # Revoke it
        response = await client.delete(
            f"/api/v1/api-keys/{key_id}", headers=auth_headers
        )  # noqa: E501

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_use_revoked_key(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test that revoked key no longer works"""
        # Create and revoke key
        create_response = await client.post(
            "/api/v1/api-keys", headers=auth_headers, json={"name": "Revoke Test"}
        )
        key = (await create_response.get_json())["key"]
        key_id = (await create_response.get_json())["id"]

        await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)

        # Try to use revoked key
        response = await client.get("/api/v1/users/me", headers={"X-API-Key": key})

        assert response.status_code == 401


class TestAPIKeyScopes:
    """Test API key scopes"""

    @pytest.mark.asyncio
    async def test_key_with_limited_scopes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test creating key with limited scopes"""
        response = await client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Limited Key", "scopes": ["read:users"]},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert "read:users" in data["scopes"]

    @pytest.mark.asyncio
    async def test_key_permission_enforcement(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Test that key scopes are enforced"""
        # Would need actual key with limited scopes
        response = await client.get(
            "/api/v1/users/me", headers={"X-API-Key": "pk_test_limited"}
        )

        # Should fail or succeed based on scopes
        assert response.status_code in [200, 403]
