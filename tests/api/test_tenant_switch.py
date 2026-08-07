"""Tests for tenant switching and extra_claims handling."""

import uuid

import jwt
import pytest
from quart import Quart

from app.config import TestingConfig


@pytest.mark.usefixtures("app_context")
class TestTenantSwitch:
    """Test tenant switching functionality."""

    @pytest.mark.asyncio
    async def test_create_access_token_with_extra_claims(self, app: Quart) -> None:
        """Test that extra_claims are merged into the token payload."""
        from app.auth import create_access_token

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

    @pytest.mark.asyncio
    async def test_extra_claims_cannot_override_reserved_claims(self, app: Quart) -> None:  # noqa: E501
        """Test that reserved claims (sub, exp, iat, type) cannot be overridden."""
        from app.auth import create_access_token

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

    @pytest.mark.asyncio
    async def test_tenant_switch_endpoint_no_longer_crashes(
        self, client, auth_headers: dict[str, str]
    ) -> None:
        """Test tenant switch endpoint doesn't crash with extra_claims."""

        # Create a tenant for this user
        response = await client.post(
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
        switch_response = await client.post(
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

    @pytest.mark.asyncio
    async def test_tenant_required_decorator_uses_correct_claim(self, app: Quart) -> None:  # noqa: E501
        """Test tenant_required decorator reads the current_tenant_id claim.

        No production endpoint is currently wrapped with @tenant_required —
        grep confirms zero usages in services/flask-backend/app/*.py outside
        the decorator's own definition in middleware.py. Attach it to an
        ad-hoc route on this test's app instance so the decorator's actual
        claim-reading behavior is exercised directly, instead of merely
        asserting a JWT payload shape that no gated endpoint in the app
        actually consumes.

        Takes only the `app` fixture (not `client`/`auth_headers`) and
        builds its own client/user locally: Quart forbids adding routes
        once the app has handled its first request, and the shared
        `auth_headers` fixture already fires a register+login request
        before this test body would even start — the route below must be
        registered before ANY request is dispatched against this app.
        """
        from app.middleware import tenant_required

        @app.route("/api/v1/_test/tenant-gated")
        @tenant_required
        async def _tenant_gated_route():  # type: ignore[no-untyped-def]
            from quart import g, jsonify

            return await jsonify({"tenant_id": g.current_tenant_id}), 200

        client = app.test_client()

        unique_email = f"tenant-gate-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "testpass123",
                "full_name": "Test User",
            },
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "testpass123"},
        )
        auth_headers = {
            "Authorization": f"Bearer {login_response.get_json()['access_token']}"
        }

        # A token with no current_tenant_id claim must be rejected
        no_tenant_response = await client.get(
            "/api/v1/_test/tenant-gated", headers=auth_headers
        )
        assert no_tenant_response.status_code == 400

        # Create a tenant and switch to it to mint a token that carries
        # current_tenant_id
        response = await client.post(
            "/api/v1/tenants",
            headers=auth_headers,
            json={
                "name": "Test Tenant 2",
                "slug": "test-tenant-2",
                "plan": "free",
            },
        )
        tenant_id = response.get_json()["id"]

        switch_response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )
        new_token = switch_response.get_json()["access_token"]

        # The decorator should now grant access, reading current_tenant_id
        gated_response = await client.get(
            "/api/v1/_test/tenant-gated",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert gated_response.status_code == 200
        assert gated_response.get_json()["tenant_id"] == tenant_id
