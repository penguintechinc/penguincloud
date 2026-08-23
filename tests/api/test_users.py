"""Functional coverage for /api/v1/users/* CRUD, roles, and self-service.

Before this file, users.py's admin-facing CRUD (POST/PUT/DELETE /users/<id>,
GET /users/roles) and the self-service password change had no dedicated
HTTP-level tests -- only the API-key and audit-log sub-resources
(test_user_api_keys.py) and the global-admin quota interactions
(test_quotas.py) exercised this blueprint. Quota/dev-mode refusal branches
on create/promote are deliberately NOT re-tested here -- test_quotas.py and
test_devmode.py already cover them with real assertions; duplicating them
would just re-execute the same lines under a different file name.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.users import _isoformat, _resolve_tenant_id


class TestCreateUserValidation:
    """POST /api/v1/users field-validation branches."""

    @pytest.mark.asyncio
    async def test_missing_email_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """An empty email 400s before any DB lookup."""
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={"email": "", "password": "a-sufficiently-long-password"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Email is required"

    @pytest.mark.asyncio
    async def test_short_password_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A password under 8 chars is rejected, distinct from a missing one."""
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={"email": "short-pw@example.com", "password": "short"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Password must be at least 8 characters"

    @pytest.mark.asyncio
    async def test_invalid_role_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A role outside VALID_ROLES is rejected before any insert."""
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "bad-role@example.com",
                "password": "a-sufficiently-long-password",
                "role": "superuser",
            },
        )
        assert response.status_code == 400
        assert "Invalid role" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_duplicate_email_is_a_conflict(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Creating a second user with an already-registered email 409s."""
        first = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "dupe-target@example.com",
                "password": "a-sufficiently-long-password",
                "role": "viewer",
            },
        )
        assert first.status_code == 201, await first.get_json()

        second = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "dupe-target@example.com",
                "password": "another-sufficiently-long-pw",
                "role": "viewer",
            },
        )
        assert second.status_code == 409
        assert (await second.get_json())["error"] == "Email already registered"

    @pytest.mark.asyncio
    async def test_success_never_leaks_the_password_hash(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A successful create returns the user without password_hash."""
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "clean-create@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Clean Create",
                "role": "viewer",
            },
        )
        assert response.status_code == 201
        body = await response.get_json()
        assert body["user"]["email"] == "clean-create@example.com"
        assert "password_hash" not in body["user"]


class TestGetUser:
    """GET /api/v1/users/<id>."""

    @pytest.mark.asyncio
    async def test_nonexistent_user_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """An id nobody holds 404s."""
        response = await client.get("/api/v1/users/999999999", headers=admin_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "User not found"

    @pytest.mark.asyncio
    async def test_existing_user_never_leaks_the_password_hash(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A real user's row is returned without password_hash."""
        created = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "gettable@example.com",
                "password": "a-sufficiently-long-password",
                "role": "viewer",
            },
        )
        user_id = (await created.get_json())["user"]["id"]

        response = await client.get(f"/api/v1/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert body["email"] == "gettable@example.com"
        assert "password_hash" not in body


class TestUpdateUserValidation:
    """PUT /api/v1/users/<id> field-validation and update-data branches."""

    @staticmethod
    async def _create_viewer(client: Any, admin_headers: dict[str, str], email: str) -> int:
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": email,
                "password": "a-sufficiently-long-password",
                "full_name": "Update Target",
                "role": "viewer",
            },
        )
        assert response.status_code == 201, await response.get_json()
        return int((await response.get_json())["user"]["id"])

    @pytest.mark.asyncio
    async def test_nonexistent_user_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Update on a nonexistent id 404s before any body parsing."""
        response = await client.put(
            "/api/v1/users/999999999", headers=admin_headers, json={"full_name": "Nobody"}
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "User not found"

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A real target with no JSON body 400s."""
        user_id = await self._create_viewer(client, admin_headers, "update-nobody@example.com")
        response = await client.put(f"/api/v1/users/{user_id}", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"

    @pytest.mark.asyncio
    async def test_email_change_to_an_in_use_address_is_a_conflict(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Renaming to an email another user already holds 409s."""
        await self._create_viewer(client, admin_headers, "taken@example.com")
        movable_id = await self._create_viewer(client, admin_headers, "movable@example.com")

        response = await client.put(
            f"/api/v1/users/{movable_id}",
            headers=admin_headers,
            json={"email": "taken@example.com"},
        )
        assert response.status_code == 409
        assert (await response.get_json())["error"] == "Email already in use"

    @pytest.mark.asyncio
    async def test_email_change_to_the_same_value_is_a_noop_success(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Setting email to its own current value skips the uniqueness lookup."""
        user_id = await self._create_viewer(client, admin_headers, "unchanged@example.com")

        response = await client.put(
            f"/api/v1/users/{user_id}",
            headers=admin_headers,
            json={"email": "unchanged@example.com", "full_name": "Renamed"},
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["user"]["email"] == "unchanged@example.com"
        assert body["user"]["full_name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_invalid_role_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """An unrecognized role 400s the update wholesale."""
        user_id = await self._create_viewer(client, admin_headers, "bad-role-update@example.com")

        response = await client.put(
            f"/api/v1/users/{user_id}", headers=admin_headers, json={"role": "superuser"}
        )
        assert response.status_code == 400
        assert "Invalid role" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_short_password_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A too-short replacement password 400s."""
        user_id = await self._create_viewer(client, admin_headers, "short-pw-update@example.com")

        response = await client.put(
            f"/api/v1/users/{user_id}", headers=admin_headers, json={"password": "short"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Password must be at least 8 characters"

    @pytest.mark.asyncio
    async def test_no_recognized_fields_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A body present but empty of recognized fields 400s."""
        user_id = await self._create_viewer(client, admin_headers, "no-fields@example.com")

        response = await client.put(
            f"/api/v1/users/{user_id}", headers=admin_headers, json={"unknown_field": "value"}
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "No valid fields to update"

    @pytest.mark.asyncio
    async def test_is_active_and_password_update_together(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """is_active and password can update in the same call; hash is stripped."""
        user_id = await self._create_viewer(client, admin_headers, "deactivate-me@example.com")

        response = await client.put(
            f"/api/v1/users/{user_id}",
            headers=admin_headers,
            json={"is_active": False, "password": "a-brand-new-long-password"},
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["user"]["is_active"] is False
        assert "password_hash" not in body["user"]

    @pytest.mark.asyncio
    async def test_repromoting_an_existing_admin_is_a_metering_noop(
        self,
        app: Any,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setting role=admin on someone ALREADY admin must not hit the quota.

        admin_headers is itself one global admin. With the limit pinned to
        exactly that current count, promoting a NEW user would 402 (see
        test_quotas.py's test_global_admin_promotion_is_metered_like_creation)
        -- but re-asserting "admin" on admin_headers' own account must
        succeed, because no NEW admin seat is being consumed.
        """
        from app import licensing, quotas

        profile = await client.get("/api/v1/users/me", headers=admin_headers)
        own_id = (await profile.get_json())["id"]

        async with app.app_context():
            current = await quotas.count_global_admins()

        async def _resolve() -> quotas.TierLimits:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY]
            return quotas.TierLimits(
                global_admins=current,
                tenant_admins=base.tenant_admins,
                tenants=base.tenants,
                teams=base.teams,
                objects=base.objects,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _resolve)

        response = await client.put(
            f"/api/v1/users/{own_id}", headers=admin_headers, json={"role": "admin"}
        )
        assert response.status_code == 200
        assert (await response.get_json())["user"]["role"] == "admin"


class TestDeleteUser:
    """DELETE /api/v1/users/<id>."""

    @pytest.mark.asyncio
    async def test_self_delete_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """An admin cannot delete their own account through this route."""
        profile = await client.get("/api/v1/users/me", headers=admin_headers)
        own_id = (await profile.get_json())["id"]

        response = await client.delete(f"/api/v1/users/{own_id}", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Cannot delete your own account"

    @pytest.mark.asyncio
    async def test_nonexistent_user_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Deleting an id nobody holds 404s."""
        response = await client.delete("/api/v1/users/999999999", headers=admin_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "User not found"

    @pytest.mark.asyncio
    async def test_existing_user_is_actually_deleted(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A genuine delete removes the row -- a follow-up GET 404s."""
        created = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "delete-me@example.com",
                "password": "a-sufficiently-long-password",
                "role": "viewer",
            },
        )
        user_id = (await created.get_json())["user"]["id"]

        response = await client.delete(f"/api/v1/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "User deleted successfully"

        follow_up = await client.get(f"/api/v1/users/{user_id}", headers=admin_headers)
        assert follow_up.status_code == 404


class TestGetRoles:
    """GET /api/v1/users/roles."""

    @pytest.mark.asyncio
    async def test_returns_the_three_platform_roles(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """The published role list matches VALID_ROLES exactly."""
        response = await client.get("/api/v1/users/roles", headers=admin_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert body["roles"] == ["admin", "maintainer", "viewer"]
        assert set(body["descriptions"]) == {"admin", "maintainer", "viewer"}


class TestChangeOwnPassword:
    """PUT /api/v1/users/me/password."""

    @pytest.mark.asyncio
    async def test_missing_fields_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Missing current_password or new_password 400s."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Current and new password required"

    @pytest.mark.asyncio
    async def test_wrong_current_password_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A wrong current password 401s without changing anything."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "not-the-real-password", "new_password": "new-long-password"},
        )
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Current password incorrect"

    @pytest.mark.asyncio
    async def test_short_new_password_is_rejected(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A correct current password but too-short new one still 400s."""
        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "short"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "New password must be 8+ characters"

    @pytest.mark.asyncio
    async def test_successful_change_actually_rotates_the_password(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The old password stops authenticating; the new one starts.

        Asserted through a real login, not the DB layer -- the 200 alone
        was exactly what a no-op change would also return.
        """
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        email = (await profile.get_json())["email"]

        response = await client.put(
            "/api/v1/users/me/password",
            headers=auth_headers,
            json={"current_password": "testpass123", "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Password changed"

        old_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
        )
        assert old_login.status_code == 401

        new_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "a-brand-new-password"}
        )
        assert new_login.status_code == 200


class TestIsoformat:
    """Pure-function coverage for users.py's own _isoformat.

    Mirrors the identical helper in app.tenants, tested separately there.
    """

    def test_none_returns_none(self) -> None:
        """A NULL column value passes through as None."""
        assert _isoformat(None) is None

    def test_string_passes_through_unchanged(self) -> None:
        """An already-string value is returned as-is."""
        assert _isoformat("2026-01-01T00:00:00") == "2026-01-01T00:00:00"


class TestResolveTenantId:
    """_resolve_tenant_id's claim-vs-param resolution, tested directly."""

    @pytest.mark.asyncio
    async def test_numeric_claim_is_used(self, app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A well-formed numeric tenant claim resolves to that int."""
        from app import users

        monkeypatch.setattr(users, "get_current_tenant_id", lambda: "42")
        async with app.test_request_context("/"):
            assert _resolve_tenant_id() == 42

    @pytest.mark.asyncio
    async def test_non_numeric_claim_falls_back_to_query_param(
        self, app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unscoped/non-numeric claim falls through to ?tenant_id=."""
        from app import users

        monkeypatch.setattr(users, "get_current_tenant_id", lambda: "unscoped")
        async with app.test_request_context("/?tenant_id=7"):
            assert _resolve_tenant_id() == 7


class TestCreateUserMissingBody:
    """The one create_new_user validation branch missing from the other class.

    No JSON body at all (distinct from an empty email).
    """

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """No JSON body 400s before the email/password checks run."""
        response = await client.post("/api/v1/users", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Request body required"


class TestQuotaAdmittedPaths:
    """The FALSE side of the admin-quota checks on create/promote.

    Genuinely succeeding while already at 1 admin, because the licence
    admits more. test_quotas.py covers the REFUSAL side of both; without
    this, "quota admits it" never executes at all.
    """

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_creating_a_second_admin_succeeds_under_enterprise(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """admin_headers is already one global admin; Enterprise has no cap."""
        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "second-admin-ok@example.com",
                "password": "a-sufficiently-long-password",
                "role": "admin",
            },
        )
        assert response.status_code == 201
        assert (await response.get_json())["user"]["role"] == "admin"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    async def test_promoting_a_new_admin_succeeds_under_enterprise(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A genuinely NEW admin promotion (not a re-promote no-op)."""
        created = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "promote-ok@example.com",
                "password": "a-sufficiently-long-password",
                "role": "viewer",
            },
        )
        assert created.status_code == 201
        user_id = (await created.get_json())["user"]["id"]

        response = await client.put(
            f"/api/v1/users/{user_id}", headers=admin_headers, json={"role": "admin"}
        )
        assert response.status_code == 200
        assert (await response.get_json())["user"]["role"] == "admin"


class TestUpdateUserEmailToAGenuinelyNewAddress:
    """The success side of the email-uniqueness check.

    Distinct from 'same value' (skips the lookup) and 'already in use' (409).
    """

    @pytest.mark.asyncio
    async def test_email_change_to_an_unused_address_succeeds(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A genuinely free email is accepted and actually applied."""
        created = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "before-rename@example.com",
                "password": "a-sufficiently-long-password",
                "role": "viewer",
            },
        )
        user_id = (await created.get_json())["user"]["id"]

        response = await client.put(
            f"/api/v1/users/{user_id}",
            headers=admin_headers,
            json={"email": "after-rename@example.com"},
        )
        assert response.status_code == 200
        assert (await response.get_json())["user"]["email"] == "after-rename@example.com"
