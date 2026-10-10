"""Remaining branch coverage in app/tenants.py.

Not reached by test_tenants_validation.py, test_tenancy_hierarchy.py,
test_hierarchical_tenancy.py or test_tenant_switch.py. Those files already
cover field validation on create/update, the owner-only
delete path, response-shape contracts, and the full delegated-admin
structure under ``enterprise_license``. Two classes of branch are left:

1. ``validate_tenant_slug``/``_isoformat`` -- pure helpers no test called
   directly with their edge inputs (empty/too-long slug, a leading hyphen,
   a None/string/raw datetime value).
2. The tenant-member CRUD's plain validation chain (missing body, missing
   user_id, invalid/owner role, unknown user, already-a-member, the
   per-tenant member-count wall, owner-removal-prevention, member-not-found
   on update/remove) at the COMMUNITY tier -- test_tenancy_hierarchy.py
   module-wide opts into ``enterprise_license``, which is exactly what
   keeps the tenant_admins quota/capability branches on the promotion
   paths from ever firing there.

Tenant/route "not found" branches gated by ``@require_scope(...,
tenant_arg=...)`` are deliberately NOT chased here, matching
test_tenants_validation.py's own documented decision: the scope check
denies a genuinely-absent id before the view body's own existence check
ever runs, so reaching that branch needs an orphaned tenant_members row,
not a merely-absent id.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.tenants import _isoformat, validate_tenant_slug
from quart import Quart


class TestValidateTenantSlug:
    """Pure-function coverage mirroring app.teams.validate_team_slug's."""

    def test_empty_string_is_invalid(self) -> None:
        """An empty slug fails the falsy check, not the length check."""
        assert validate_tenant_slug("") is False

    def test_too_short_is_invalid(self) -> None:
        """One below the 3-char floor is rejected."""
        assert validate_tenant_slug("ab") is False

    def test_too_long_is_invalid(self) -> None:
        """One above the 63-char ceiling is rejected."""
        assert validate_tenant_slug("a" * 64) is False

    def test_leading_hyphen_is_invalid(self) -> None:
        """Every char passes the charset check; slug[0] fails isalnum()."""
        assert validate_tenant_slug("-leading") is False

    def test_valid_slug_is_accepted(self) -> None:
        """A well-formed slug at both boundaries is accepted."""
        assert validate_tenant_slug("valid-tenant-123") is True
        assert validate_tenant_slug("a" * 63) is True


class TestIsoformat:
    """Pure-function coverage for every branch _isoformat can take."""

    def test_none_returns_none(self) -> None:
        """A NULL column value passes through as None, not '' or 'None'."""
        assert _isoformat(None) is None

    def test_string_passes_through_unchanged(self) -> None:
        """An already-string value (some DAL backends) is returned as-is."""
        assert _isoformat("2026-01-01T00:00:00") == "2026-01-01T00:00:00"

    def test_datetime_like_object_calls_isoformat(self) -> None:
        """A real datetime value is rendered via its own .isoformat()."""

        class _FakeDatetime:
            def isoformat(self) -> str:
                return "2026-06-01T12:00:00"

        assert _isoformat(_FakeDatetime()) == "2026-06-01T12:00:00"

    def test_object_without_isoformat_falls_back_to_str(self) -> None:
        """A value with neither None, str, nor .isoformat() still renders."""
        assert _isoformat(12345) == "12345"


async def _register(client: Any, email: str) -> tuple[dict[str, str], int]:
    """Register and log in a fresh user; return (auth headers, user id)."""
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Edge User"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert login.status_code == 200
    token = (await login.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id


class TestAddTenantMemberValidation:
    """POST /api/v1/tenants/<id>/members, at the (default) COMMUNITY tier."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """No JSON body 400s, checked after the quota lookup succeeds."""
        response = await client.post(f"/api/v1/tenants/{tenant_id}/members", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_missing_user_id_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A body with no user_id 400s."""
        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"role": "member"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "user_id required"

    @pytest.mark.asyncio
    async def test_owner_role_is_rejected_even_though_it_is_valid_elsewhere(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The owner role is in VALID_TENANT_ROLES but refused here.

        Only create_tenant grants it, never this endpoint.
        """
        _, target_id = await _register(client, f"owner-role-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "owner"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Valid role required (admin, member, viewer)"

    @pytest.mark.asyncio
    async def test_nonexistent_user_is_not_found(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A user_id nobody holds 404s."""
        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": 999999999, "role": "member"},
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "User not found"

    @pytest.mark.asyncio
    async def test_already_a_member_is_a_conflict(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The tenant's own owner is already a member of it."""
        profile = await client.get("/api/v1/users/me", headers=admin_headers)
        own_id = (await profile.get_json())["id"]

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": own_id, "role": "member"},
        )
        assert response.status_code == 409
        assert (await response.get_json())["error"] == "User already a member"

    @pytest.mark.asyncio
    async def test_admin_role_is_refused_at_community_tier(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Community's tenant_admins limit is 0 -- adding one 402s."""
        _, target_id = await _register(client, f"admin-role-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "admin"},
        )
        assert response.status_code == 402
        assert (await response.get_json())["dimension"] == "tenant_admins"

    @pytest.mark.asyncio
    async def test_member_count_wall_refuses_the_next_add(
        self, app: Quart, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """max_users caps additions -- lowered to 1 so the owner alone fills it."""
        async with app.app_context():
            from app.models import get_db

            db = get_db()
            await db(db.tenants.id == tenant_id).update(max_users=1)
            await db.commit()

        _, target_id = await _register(client, f"over-quota-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "member"},
        )
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "Tenant member limit reached"

    @pytest.mark.asyncio
    async def test_valid_member_add_succeeds(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A genuine, valid add is 201.

        Confirms the wall above is real, not a permanently-refusing bug.
        """
        _, target_id = await _register(client, f"valid-add-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "member"},
        )
        assert response.status_code == 201


class TestUpdateTenantMemberRoleValidation:
    """PUT /api/v1/tenants/<id>/members/<user_id>."""

    @pytest.mark.asyncio
    async def test_invalid_role_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A role outside the allowed set 400s."""
        response = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/999999999",
            headers=admin_headers,
            json={"role": "superuser"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Valid role required (admin, member, viewer)"

    @pytest.mark.asyncio
    async def test_promoting_to_admin_is_refused_at_community_tier(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A plain member promoted to admin hits the same tenant_admins wall.

        Creation does too -- the OTHER entrance to the same structure.
        """
        _, target_id = await _register(client, f"promote-{uuid.uuid4().hex[:8]}@example.com")
        add = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "member"},
        )
        assert add.status_code == 201

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/{target_id}",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert response.status_code == 402
        assert (await response.get_json())["dimension"] == "tenant_admins"

    @pytest.mark.asyncio
    async def test_updating_a_non_member_is_not_found(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A valid role but a user with no membership row 404s.

        The UPDATE affects zero rows and the re-fetch finds nothing.
        """
        _, stranger_id = await _register(client, f"stranger-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/{stranger_id}",
            headers=admin_headers,
            json={"role": "viewer"},
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Member not found"


class TestRemoveTenantMemberValidation:
    """DELETE /api/v1/tenants/<id>/members/<user_id>."""

    @pytest.mark.asyncio
    async def test_owner_cannot_be_removed(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Removing the tenant's own owner is refused outright."""
        profile = await client.get("/api/v1/users/me", headers=admin_headers)
        own_id = (await profile.get_json())["id"]

        response = await client.delete(
            f"/api/v1/tenants/{tenant_id}/members/{own_id}", headers=admin_headers
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Cannot remove tenant owner"

    @pytest.mark.asyncio
    async def test_removing_a_non_member_is_not_found(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A user with no membership row 404s rather than reporting success."""
        response = await client.delete(
            f"/api/v1/tenants/{tenant_id}/members/999999999", headers=admin_headers
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Member not found"

    @pytest.mark.asyncio
    async def test_valid_removal_actually_removes_the_row(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A genuine member is truly gone afterward, not just reported so."""
        _, target_id = await _register(client, f"removable-{uuid.uuid4().hex[:8]}@example.com")
        add = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "member"},
        )
        assert add.status_code == 201

        response = await client.delete(
            f"/api/v1/tenants/{tenant_id}/members/{target_id}", headers=admin_headers
        )
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Member removed"

        # Removing again -- the row is genuinely gone, not merely re-reported.
        again = await client.delete(
            f"/api/v1/tenants/{tenant_id}/members/{target_id}", headers=admin_headers
        )
        assert again.status_code == 404


class TestSwitchTenantValidation:
    """POST /api/v1/tenants/<id>/switch."""

    @pytest.mark.asyncio
    async def test_unauthorized_switch_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A stranger with no membership is refused, before existence leaks."""
        outsider = await _register(client, f"switch-stranger-{uuid.uuid4().hex[:8]}@example.com")
        outsider_headers = outsider[0]

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=outsider_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_switch_to_a_deactivated_tenant_is_not_available(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """An authorized member cannot switch into a deactivated tenant."""
        deactivate = await client.put(
            f"/api/v1/tenants/{tenant_id}", headers=admin_headers, json={"is_active": False}
        )
        assert deactivate.status_code == 200

        response = await client.post(f"/api/v1/tenants/{tenant_id}/switch", headers=admin_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Tenant not available"


class TestMemberWithIdentityHelper:
    """_member_with_identity's own branches, via a real add-member call."""

    @pytest.mark.asyncio
    async def test_added_member_identity_is_joined_from_the_users_table(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A successful add resolves the new member's email/full_name.

        Exercises the "member_user found" branch inside
        _member_with_identity, which POST .../members' success path calls
        internally.
        """
        _, target_id = await _register(client, f"identity-join-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": target_id, "role": "member"},
        )
        assert response.status_code == 201
        body = await response.get_json()
        assert body["user_email"].endswith("@example.com")
        assert body["user_full_name"] == "Edge User"


class TestDeleteTenantOwnerRowDivergence:
    """delete_tenant_endpoint retains its own row-level owner check.

    Even though SCOPE_TENANTS_DELETE is owner-bundle-only -- the scope
    answers "an owner of this tenant", the row check answers "*the* owner"
    (see the function's own docstring). Normally these can't diverge (only
    the creator ever holds the owner role), so this test forces the
    divergence directly at the DB layer to prove the row check is a real
    second gate, not dead weight duplicating the scope check.
    """

    @pytest.mark.asyncio
    async def test_scope_alone_is_not_enough_to_delete(
        self, app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """admin_headers still holds the owner-role scope; the row disagrees.

        The row's owner_id has been reassigned elsewhere -- the row check
        must still refuse.
        """
        async with app.app_context():
            from app.models import get_db

            db = get_db()
            await db(db.tenants.id == tenant_id).update(owner_id=999999999)
            await db.commit()

        response = await client.delete(f"/api/v1/tenants/{tenant_id}", headers=admin_headers)
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "Only owner can delete tenant"
