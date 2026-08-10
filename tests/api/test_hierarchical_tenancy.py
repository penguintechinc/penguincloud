"""Tests for hierarchical tenancy and delegated admin access control."""

import jwt
from typing import Any

import pytest
from quart import Quart

#: Every test in this file builds a multi-tenant / delegated-admin
#: structure, which the tier model sells at Enterprise (tenants 1/1/∞,
#: tenant admins 0/10/∞). Under the default Community licence the quota
#: walls refuse the second tenant and the first delegated admin, so these
#: tests licence themselves for what they exercise rather than the suite
#: silently lifting every wall for every file.
pytestmark = pytest.mark.usefixtures("enterprise_license")


@pytest.mark.usefixtures("app_context")
class TestHierarchicalTenancyMatrix:
    """Matrix tests for hierarchical tenancy access control.

    Covers:
    - Direct member can switch (existing tenant, no hierarchy)
    - Provider admin can switch to descendant
    - Sibling member CANNOT switch to sibling (no hierarchy bridge)
    - Outsider 403
    - Token carries correct tenant/home_tenant/scope claims
    """

    async def _create_tenant_as_user(
        self, client: Any, auth_headers: dict[str, str], name: str, slug: str
    ) -> int:
        """Helper: create a tenant, return tenant_id."""
        import uuid

        # Ensure unique slug
        unique_slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        response = await client.post(
            "/api/v1/tenants",
            headers=auth_headers,
            json={"name": name, "slug": unique_slug, "plan": "free"},
        )
        response_data = await response.get_json()
        msg = f"Failed to create {name}: {response_data}"
        assert response.status_code == 201, msg
        return int(response_data["id"])

    async def _add_member_to_tenant(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        role: str = "member",
    ) -> None:
        """Helper: add a user to a tenant."""
        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": role},
        )
        response_data = await response.get_json()
        msg = f"Failed to add member: {response_data}"
        assert response.status_code == 201, msg

    @pytest.mark.asyncio
    async def test_direct_member_can_switch_to_own_tenant(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Direct member of a tenant can switch to it (existing behavior)."""
        # Create a tenant (user is owner)
        tenant_id = await self._create_tenant_as_user(
            client, auth_headers, "Direct Tenant", "direct-tenant"
        )

        # Switch to it (should work)
        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert "access_token" in data
        assert data["tenant_role"] == "owner"

        # Verify token has tenant claim
        token = data["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["tenant"] == str(tenant_id)

    @pytest.mark.asyncio
    async def test_provider_admin_can_switch_to_descendant(
        self, client: Any, app: Quart
    ) -> None:
        """Provider admin can switch to descendant tenant via delegated admin."""
        # Create two users: provider admin and descendant member
        import uuid

        admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        member_email = f"member-{uuid.uuid4().hex[:8]}@example.com"

        # Register and login admin
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": admin_email,
                "password": "testpass123",
                "full_name": "Admin User",
            },
        )
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": "testpass123"},
        )
        admin_body = await admin_login.get_json()
        admin_headers = {"Authorization": f"Bearer {admin_body['access_token']}"}

        # Register and login member
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": member_email,
                "password": "testpass123",
                "full_name": "Member User",
            },
        )
        member_login = await client.post(
            "/api/v1/auth/login",
            json={"email": member_email, "password": "testpass123"},
        )
        member_body = await member_login.get_json()
        # Extract user_id from the JWT payload
        member_token = member_body["access_token"]
        member_payload = jwt.decode(member_token, options={"verify_signature": False})
        member_id = int(member_payload["sub"])

        # Admin creates provider tenant
        provider_id = await self._create_tenant_as_user(
            client, admin_headers, "Provider", "provider"
        )

        # Admin creates customer tenant (child of provider)
        customer_id = await self._create_tenant_as_user(
            client, admin_headers, "Customer", "customer"
        )

        # Set parent relationship manually (would normally be in schema/API)
        from app.models import get_db

        db = get_db()
        update_result = await db(db.tenants.id == customer_id).update(
            parent_tenant_id=provider_id
        )
        assert update_result is not None

        # Add member to customer (not provider)
        await self._add_member_to_tenant(
            client, admin_headers, customer_id, member_id, role="member"
        )

        # Member registers and gets their token
        member_headers = {"Authorization": f"Bearer {member_body['access_token']}"}

        # Member CANNOT switch to provider (not a member)
        response = await client.post(
            f"/api/v1/tenants/{provider_id}/switch", headers=member_headers
        )
        assert response.status_code == 403

        # Admin can switch to customer (delegated admin)
        response = await client.post(
            f"/api/v1/tenants/{customer_id}/switch", headers=admin_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        token = data["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["tenant"] == str(customer_id)

    @pytest.mark.asyncio
    async def test_sibling_member_cannot_switch_to_sibling(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Sibling tenant members cannot switch to each other (no bridge)."""
        import uuid

        # Create another user
        other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": other_email,
                "password": "testpass123",
                "full_name": "Other User",
            },
        )
        other_login = await client.post(
            "/api/v1/auth/login",
            json={"email": other_email, "password": "testpass123"},
        )
        other_body = await other_login.get_json()
        other_headers = {"Authorization": f"Bearer {other_body['access_token']}"}

        # User 1 creates tenant A
        tenant_a = await self._create_tenant_as_user(
            client, auth_headers, "Tenant A", "tenant-a"
        )

        # User 2 creates tenant B
        tenant_b = await self._create_tenant_as_user(
            client, other_headers, "Tenant B", "tenant-b"
        )

        # User 1 tries to switch to B (not a member, no ancestor bridge)
        response = await client.post(
            f"/api/v1/tenants/{tenant_b}/switch", headers=auth_headers
        )
        assert response.status_code == 403

        # User 2 tries to switch to A
        response = await client.post(
            f"/api/v1/tenants/{tenant_a}/switch", headers=other_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_switch_token_carries_home_tenant_claim(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Switch token carries home_tenant claim for context preservation."""
        # Create tenant and switch to it
        tenant_id = await self._create_tenant_as_user(
            client, auth_headers, "Home Tenant", "home-tenant"
        )

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=auth_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        token = data["access_token"]

        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["tenant"] == str(tenant_id)
        # home_tenant is in ext claims
        assert "ext" in payload
        assert payload["ext"].get("home_tenant") == str(tenant_id)

    @pytest.mark.asyncio
    async def test_list_tenants_include_children_requires_admin(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """include_children parameter lists subtree only for admin/owner."""
        import uuid

        # Create another user (plain member)
        member_email = f"member-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": member_email,
                "password": "testpass123",
                "full_name": "Member User",
            },
        )
        member_login = await client.post(
            "/api/v1/auth/login",
            json={"email": member_email, "password": "testpass123"},
        )
        member_body = await member_login.get_json()
        # Extract user_id from the JWT payload
        member_token = member_body["access_token"]
        member_payload = jwt.decode(member_token, options={"verify_signature": False})
        member_id = int(member_payload["sub"])
        member_headers = {"Authorization": f"Bearer {member_body['access_token']}"}

        # Admin creates provider and customer tenant
        provider_id = await self._create_tenant_as_user(
            client, auth_headers, "Provider", "provider"
        )
        customer_id = await self._create_tenant_as_user(
            client, auth_headers, "Customer", "customer"
        )

        # Set hierarchy
        from app.models import get_db

        db = get_db()
        update_result = await db(db.tenants.id == customer_id).update(
            parent_tenant_id=provider_id
        )
        assert update_result is not None

        # Add member to customer only (not provider)
        await self._add_member_to_tenant(
            client, auth_headers, customer_id, member_id, role="member"
        )

        # Member's basic list shows only customer
        response = await client.get("/api/v1/tenants", headers=member_headers)
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["tenants"]) == 1
        assert data["tenants"][0]["id"] == customer_id

        # Member's include_children shows nothing extra (not admin anywhere)
        response = await client.get(
            "/api/v1/tenants?include_children=true", headers=member_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["tenants"]) == 1

        # Admin's include_children shows provider + customer
        response = await client.get(
            "/api/v1/tenants?include_children=true", headers=auth_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data["tenants"]) == 2
        tenant_ids = {t["id"] for t in data["tenants"]}
        assert tenant_ids == {provider_id, customer_id}

    @pytest.mark.asyncio
    async def test_dashboard_rollup_requires_admin(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Dashboard rollup endpoint is admin-only."""
        tenant_id = await self._create_tenant_as_user(
            client, auth_headers, "Test Tenant", "test-tenant"
        )

        # Owner can access
        response = await client.get(
            f"/api/v1/tenants/{tenant_id}/dashboard/rollup", headers=auth_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert "rollup" in data

        # Non-member cannot
        import uuid

        other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": other_email,
                "password": "testpass123",
                "full_name": "Other User",
            },
        )
        other_login = await client.post(
            "/api/v1/auth/login",
            json={"email": other_email, "password": "testpass123"},
        )
        other_body = await other_login.get_json()
        other_headers = {"Authorization": f"Bearer {other_body['access_token']}"}

        response = await client.get(
            f"/api/v1/tenants/{tenant_id}/dashboard/rollup", headers=other_headers
        )
        assert response.status_code == 403
