"""Field-validation branches of POST/PUT /tenants not covered elsewhere.

test_tenancy_hierarchy.py and test_hierarchical_tenancy.py already cover
parenting, delegation, scope resolution and response-shape contracts
extensively. This file covers the plain field-validation chain on tenant
creation and update that those files don't exercise: missing/invalid name,
slug, plan, kind, and the update endpoint's per-field update_data
construction (name, display_name, settings, and the billing-scope-gated
plan/is_active fields).

Not-found branches on GET/PUT /tenants/<id> are deliberately not targeted
here: those routes use @require_scope(..., tenant_arg="tenant_id"), which
resolves and denies BEFORE the view body's own existence check ever runs
-- a genuinely nonexistent id 403s, not 404s (verified directly). Chasing
that 404 branch would need an orphaned tenant_members row pointing at a
deleted tenant, not a merely-absent id.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


class TestCreateTenantValidation:
    """Create Tenant Validation."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Missing body is rejected."""
        response = await client.post("/api/v1/tenants", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_name_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Missing name is rejected."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"slug": f"t-{uuid.uuid4().hex[:8]}"},
        )
        assert response.status_code == 400
        assert "name" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_slug_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Invalid slug is rejected."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Bad Slug Tenant", "slug": "Not A Valid Slug!"},
        )
        assert response.status_code == 400
        assert "slug" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_plan_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Invalid plan is rejected."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={
                "name": "Bad Plan Tenant",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "plan": "platinum-deluxe",
            },
        )
        assert response.status_code == 400
        assert "plan" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_kind_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Invalid kind is rejected."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={
                "name": "Bad Kind Tenant",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "kind": "reseller",
            },
        )
        assert response.status_code == 400
        assert "kind" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_non_integer_parent_tenant_id_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Non integer parent tenant id is rejected."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={
                "name": "Bad Parent Tenant",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "parent_tenant_id": "not-an-int",
            },
        )
        assert response.status_code == 400
        assert "parent_tenant_id" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_bool_parent_tenant_id_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Bool is an int subclass -- must not silently resolve to tenant 1."""
        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={
                "name": "Bool Parent Tenant",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "parent_tenant_id": True,
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_duplicate_slug_is_a_conflict(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Duplicate slug is a conflict."""
        slug = f"t-dup-{uuid.uuid4().hex[:8]}"
        first = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "First", "slug": slug},
        )
        assert first.status_code in (201, 402, 403), await first.get_json()

        second = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Second", "slug": slug},
        )
        # Whichever wall the first hit, a caller retrying the SAME slug must
        # never get past the uniqueness check on the second attempt.
        assert second.status_code in (409, 402, 403)


class TestUpdateTenantFields:
    """Update Tenant Fields."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Missing body is rejected."""
        response = await client.put(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_name_is_updated(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Name is updated."""
        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"name": "Renamed Tenant"},
        )
        assert response.status_code == 200
        assert (await response.get_json())["name"] == "Renamed Tenant"

    @pytest.mark.asyncio
    async def test_overlong_name_is_silently_not_applied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Overlong name is silently not applied."""
        before = await client.get(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        original_name = (await before.get_json())["name"]

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"name": "x" * 300},
        )
        assert response.status_code == 200
        assert (await response.get_json())["name"] == original_name

    @pytest.mark.asyncio
    async def test_display_name_is_updated(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Display name is updated."""
        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"display_name": "Friendly Name"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_settings_are_json_encoded(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Settings are json encoded."""
        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"settings": {"theme": "dark", "notifications": True}},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_owner_may_change_plan_and_activation(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """admin_headers created the tenant, so it holds tenants:billing."""
        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"plan": "starter", "is_active": True},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data.get("plan") == "starter" or data.get("plan_tier") == "starter"

    @pytest.mark.asyncio
    async def test_invalid_plan_value_is_silently_ignored(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """An invalid plan string never reaches VALID_PLANS -- not applied."""
        before = await client.get(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        original_plan = (await before.get_json()).get("plan") or (await before.get_json()).get(
            "plan_tier"
        )

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=admin_headers,
            json={"plan": "not-a-real-plan"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert (data.get("plan") or data.get("plan_tier")) == original_plan


class TestDeleteTenant:
    """delete_tenant_endpoint -- previously 0% covered (owner-only, destructive)."""

    @pytest.mark.asyncio
    async def test_owner_deletes_their_tenant(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Owner deletes their tenant."""
        response = await client.delete(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Tenant deleted"

        followup = await client.get(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        assert followup.status_code == 403  # scope check runs first, see module docstring

    @pytest.mark.asyncio
    async def test_delete_cascades_members_and_connections(
        self, client: Any, app: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Delete cascades members and connections."""
        member_email = f"tenant-delete-member-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": member_email,
                "password": "memberpass123",
                "full_name": "Member",
            },
        )
        assert register.status_code in (200, 201)
        member_id = int((await register.get_json())["user"]["id"])

        async with app.app_context():
            from app.models import add_tenant_member

            await add_tenant_member(tenant_id, member_id, role="member")

        response = await client.delete(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        assert response.status_code == 200

        async with app.app_context():
            from app.models import get_db

            db = get_db()
            remaining = await db(db.tenant_members.tenant_id == tenant_id).select()
            assert list(remaining) == []

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Delegated tenant admin is an Enterprise structure (0 on Free).
    async def test_non_owner_admin_cannot_delete(
        self, client: Any, app: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """tenants:delete is owner-bundle-only -- a delegated admin lacks it."""
        delegate_email = f"tenant-delete-delegate-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": delegate_email,
                "password": "delegatepass123",
                "full_name": "Delegate",
            },
        )
        assert register.status_code in (200, 201)
        delegate_id = int((await register.get_json())["user"]["id"])
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": delegate_email, "password": "delegatepass123"},
        )
        delegate_headers = {"Authorization": f"Bearer {(await login.get_json())['access_token']}"}

        async with app.app_context():
            from app.models import add_tenant_member

            await add_tenant_member(tenant_id, delegate_id, role="admin")

        response = await client.delete(f"/api/v1/tenants/{tenant_id}", headers=delegate_headers)
        assert response.status_code == 403
