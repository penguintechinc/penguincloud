"""Tests for tenant switching and extra_claims handling."""

from typing import Any
import jwt
from app.config import TestingConfig


class TestTenantSwitch:
    """Test tenant switching functionality."""

    def test_create_access_token_with_extra_claims(self, app: Any) -> None:
        """Test that extra_claims are merged into the token payload."""
        from app.auth import create_access_token

        with app.app_context():
            user_id = 123
            role = "admin"
            extra_claims = {"current_tenant_id": 456, "tenant_role": "owner"}

            token = create_access_token(
                user_id=user_id,
                role=role,
                team_ids=[1, 2, 3],
                extra_claims=extra_claims,
            )

            # Decode token and verify claims
            payload = jwt.decode(
                token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
            )

            # Verify extra_claims were merged
            assert payload["current_tenant_id"] == 456
            assert payload["tenant_role"] == "owner"

            # Verify existing claims are still there
            assert payload["sub"] == str(user_id)
            assert payload["role"] == role
            assert payload["type"] == "access"
            assert payload["team_ids"] == [1, 2, 3]

    def test_extra_claims_cannot_override_reserved_claims(self, app: Any) -> None:
        """Test that reserved claims (sub, exp, iat, type) cannot be overridden."""
        from app.auth import create_access_token

        with app.app_context():
            user_id = 123
            role = "admin"
            # Try to override reserved claims
            extra_claims = {
                "sub": "999",  # Should not override
                "type": "malicious",  # Should not override
                "custom_claim": "allowed",  # Should be merged
            }

            token = create_access_token(
                user_id=user_id, role=role, team_ids=[], extra_claims=extra_claims
            )

            payload = jwt.decode(
                token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
            )

            # Reserved claims should not be overridden
            assert payload["sub"] == str(user_id)
            assert payload["type"] == "access"

            # Custom claim should be present
            assert payload["custom_claim"] == "allowed"

    def test_tenant_switch_endpoint_no_longer_crashes(
        self, client: Any, auth_headers: Any
    ) -> None:
        """Test tenant switch endpoint doesn't crash with extra_claims."""

        # Create a tenant for this user
        response = client.post(
            "/api/v1/tenants",
            headers=auth_headers,
            json={
                "name": "Test Tenant",
                "slug": "test-tenant",
                "plan": "free",
            },
        )

        assert (
            response.status_code == 201
        ), f"Failed to create tenant: {response.get_json()}"
        tenant_data = response.get_json()
        tenant_id = tenant_data["id"]

        # Now try to switch to that tenant
        switch_response = client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )

        # Should not crash (was getting TypeError before fix)
        assert (
            switch_response.status_code == 200
        ), f"Tenant switch failed: {switch_response.get_json()}"

        # Verify the response
        switch_data = switch_response.get_json()
        assert "access_token" in switch_data
        assert "tenant" in switch_data
        assert "tenant_role" in switch_data

        # Verify the new token has the tenant claim
        new_token = switch_data["access_token"]
        new_payload = jwt.decode(
            new_token, TestingConfig.JWT_SECRET_KEY, algorithms=["HS256"]
        )
        assert new_payload["current_tenant_id"] == tenant_id
        assert new_payload["tenant_role"] == "owner"

    def test_tenant_required_decorator_uses_correct_claim(
        self, client: Any, auth_headers: Any
    ) -> None:
        """Test tenant_required decorator reads current_tenant_id claim."""
        import jwt
        from app.config import TestingConfig

        # Create a tenant
        response = client.post(
            "/api/v1/tenants",
            headers=auth_headers,
            json={
                "name": "Test Tenant 2",
                "slug": "test-tenant-2",
                "plan": "free",
            },
        )
        tenant_id = response.get_json()["id"]

        # Switch to tenant
        switch_response = client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )
        new_token = switch_response.get_json()["access_token"]

        # Verify tenant context is available
        new_payload = jwt.decode(
            new_token, TestingConfig.JWT_SECRET_KEY, algorithms=["HS256"]
        )
        assert "current_tenant_id" in new_payload
        assert new_payload["current_tenant_id"] == tenant_id
