"""Tests for tenant switching and the issued JWT claim structure."""

import uuid

import jwt
from typing import Any

import pytest
from quart import Quart


@pytest.mark.usefixtures("app_context")
class TestTenantSwitch:
    """Test tenant switching functionality."""

    @pytest.mark.asyncio
    async def test_token_carries_house_standard_claims(self, app: Quart) -> None:
        """Minted access tokens carry the full house-standard claim set.

        Replaces two tests written against the pre-migration contract
        (`app.auth.create_access_token(..., extra_claims=...)`, a hand-rolled
        HS256 token signed with JWT_SECRET_KEY, carrying `role`/`team_ids`/
        `type`/`current_tenant_id`). That function no longer exists: tokens
        are now issued by penguin-aaa's OIDCProvider, signed RS256 with a
        keystore key, and the arbitrary `extra_claims` merge is gone by
        design — Claims is a fixed, validated model, so the "reserved claims
        cannot be overridden" case it guarded is now unrepresentable.
        """
        from app.auth import create_token_set_async

        async with app.test_request_context("/", method="GET"):
            token_set = await create_token_set_async(
                user_id=123,
                tenant_id="456",
                role="admin",
                teams=["1", "2", "3"],
            )

        payload = jwt.decode(
            token_set["access_token"], options={"verify_signature": False}
        )

        assert payload["sub"] == "123"
        assert payload["iss"] == app.config["JWT_ISSUER"]
        assert payload["aud"] == list(app.config["JWT_AUDIENCES"])
        assert payload["tenant"] == "456"
        assert payload["roles"] == ["admin"]
        assert payload["teams"] == ["1", "2", "3"]
        # `scope` is now a RESOLVED authorization list, not the placeholder
        # ["read", "write"] pair. Omitting `scopes=` means "no resolved
        # authority", which yields the unscoped bundle: enumerate your
        # tenants and switch into one, nothing further. The full bundle for
        # an active tenant is asserted in test_hierarchical_tenancy.py.
        from app.tenancy import UNSCOPED_SCOPES

        assert payload["scope"] == list(UNSCOPED_SCOPES)
        assert "iat" in payload and "exp" in payload

        # The superseded claim names must not reappear.
        for removed in ("role", "team_ids", "type", "current_tenant_id"):
            assert removed not in payload

    @pytest.mark.asyncio
    async def test_unscoped_token_uses_sentinel_tenant(self, app: Quart) -> None:
        """A user with no active tenant still gets a non-empty tenant claim.

        penguin-aaa's Claims model rejects an empty tenant and the house
        standard requires the claim on every token, so an unscoped token
        carries UNSCOPED_TENANT rather than "".
        """
        from app.auth import create_token_set_async
        from app.config import UNSCOPED_TENANT

        async with app.test_request_context("/", method="GET"):
            token_set = await create_token_set_async(
                user_id=123, tenant_id="", role="viewer", teams=[]
            )

        payload = jwt.decode(
            token_set["access_token"], options={"verify_signature": False}
        )
        assert payload["tenant"] == UNSCOPED_TENANT

    @pytest.mark.asyncio
    async def test_tenant_switch_endpoint_no_longer_crashes(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Tenant switch returns a new token scoped to the target tenant."""

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
        ), f"Failed to create tenant: {(await response.get_json())}"
        tenant_data = await response.get_json()
        tenant_id = tenant_data["id"]

        # Now try to switch to that tenant
        switch_response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )

        # Should not crash (was getting TypeError before fix)
        assert (
            switch_response.status_code == 200
        ), f"Tenant switch failed: {(await switch_response.get_json())}"

        # Verify the response
        switch_data = await switch_response.get_json()
        assert "access_token" in switch_data
        assert "tenant" in switch_data
        assert "tenant_role" in switch_data

        # Verify the new token has the tenant claim
        new_token = switch_data["access_token"]
        # Post-migration the active tenant rides in the standard `tenant`
        # claim (RS256/penguin-aaa), not the old `current_tenant_id` extra.
        new_payload = jwt.decode(new_token, options={"verify_signature": False})
        assert new_payload["tenant"] == str(tenant_id)
        assert switch_data["tenant_role"] == "owner"

    @pytest.mark.asyncio
    async def test_tenant_required_decorator_uses_correct_claim(
        self, app: Quart
    ) -> None:
        """tenant_required gates on the verified `tenant` claim.

        No production endpoint is currently wrapped with @tenant_required —
        grep confirms zero usages in services/portal-api/app/*.py outside
        the decorator's own definition in middleware.py. Attach it to an
        ad-hoc route on this test's app instance so the decorator's actual
        claim-reading behavior is exercised directly, instead of merely
        asserting a JWT payload shape that no gated endpoint in the app
        actually consumes.

        Stacked under @auth_required, which is a contract change from the
        pre-migration version of this test: get_current_tenant_id() used to
        decode the bearer token itself, so tenant_required worked standalone.
        Verification now happens exactly once, in auth_required, and
        tenant_required composes on top by reading the already-verified
        claims off `g` — one verification path instead of two.

        Takes only the `app` fixture (not `client`/`auth_headers`) and
        builds its own client/user locally: Quart forbids adding routes
        once the app has handled its first request, and the shared
        `auth_headers` fixture already fires a register+login request
        before this test body would even start — the route below must be
        registered before ANY request is dispatched against this app.
        """
        from app.middleware import auth_required, tenant_required

        @app.route("/api/v1/_test/tenant-gated")
        @auth_required
        @tenant_required
        async def _tenant_gated_route() -> tuple[dict[str, Any], int]:
            from quart import g

            return {"tenant_id": g.current_tenant_id}, 200

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
        login_body = await login_response.get_json()
        auth_headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        # A token with only the unscoped sentinel tenant must be rejected
        no_tenant_response = await client.get(
            "/api/v1/_test/tenant-gated", headers=auth_headers
        )
        assert no_tenant_response.status_code == 400

        # Create a tenant and switch to it to mint a token carrying a real
        # tenant claim
        response = await client.post(
            "/api/v1/tenants",
            headers=auth_headers,
            json={
                "name": "Test Tenant 2",
                "slug": "test-tenant-2",
                "plan": "free",
            },
        )
        tenant_id = (await response.get_json())["id"]

        switch_response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )
        new_token = (await switch_response.get_json())["access_token"]

        # The decorator should now grant access, reading current_tenant_id
        gated_response = await client.get(
            "/api/v1/_test/tenant-gated",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert gated_response.status_code == 200
        assert (await gated_response.get_json())["tenant_id"] == str(tenant_id)
