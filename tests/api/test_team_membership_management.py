"""Team membership, role and lifecycle coverage independent of Phase 1B.

test_teams.py documents (via REASON_OWNER_NOT_AUTO_MEMBER) that
create_team() never inserts a team_members row for its own creator, so
every membership-gated endpoint 403s a team's own creator today. This file
works around that gap the same way a real caller eventually will -- by
granting membership directly through app.models.add_team_member inside an
app context -- so the substantial, already-correct business logic in
teams.py (member listing/add/update/remove, team update/delete, and the
invitation endpoints' pre-checks that never touch the missing
team_invitations table) gets real, assertion-backed coverage instead of
sitting behind a bug in an unrelated code path.

Endpoints that actually touch `db.team_invitations` (send_invitation's
success path, accept_invitation, cancel_invitation's success path) are
deliberately NOT exercised here -- models.py has no team_invitations table
defined, so those calls raise AttributeError, which is exactly what
test_teams.py's xfail tests for that gap already document.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from quart import Quart


async def _make_owned_team(
    client: Any, app: Quart, owner_headers: dict[str, str], *, slug: str
) -> tuple[int, int]:
    """Create a team and grant its creator genuine 'owner' membership.

    Mirrors what Phase 1B's auto-membership will eventually do at creation
    time -- done here explicitly so tests exercise the real membership-gated
    logic rather than a permanently-403 endpoint.

    Returns (team_id, owner_user_id). The owner id is read back from
    ``/api/v1/users/me`` rather than taken from a separately-registered
    fixture -- conftest's ``user_id`` and ``auth_headers`` fixtures each
    register their OWN distinct user, so they never name the same account.
    """
    response = await client.post(
        "/api/v1/teams",
        headers=owner_headers,
        json={"name": "Membership Test Team", "slug": slug},
    )
    assert response.status_code == 201, await response.get_json()
    team_id = int((await response.get_json())["id"])

    profile = await client.get("/api/v1/users/me", headers=owner_headers)
    assert profile.status_code == 200
    owner_id = int((await profile.get_json())["id"])

    async with app.app_context():
        from app.models import add_team_member

        member_id = await add_team_member(team_id, owner_id, "owner")
        assert member_id is not None

    return team_id, owner_id


async def _new_member(client: Any) -> tuple[dict[str, str], int]:
    """Register a second, distinct user (not yet part of any team)."""
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "memberpass123", "full_name": "Member User"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "memberpass123"}
    )
    assert login.status_code == 200
    token = (await login.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest.mark.usefixtures("enterprise_license")
class TestListTeamMembersWithRealOwnership:
    """Free licences one team via registration; these tests build a second."""

    @pytest.mark.asyncio
    async def test_owner_sees_themselves_in_the_member_list(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner sees themselves in the member list."""
        team_id, owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-owner-list")

        response = await client.get(f"/api/v1/teams/{team_id}/members", headers=auth_headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["count"] == 1
        assert data["members"][0]["user_id"] == owner_id
        assert data["members"][0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_non_member_is_denied(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Non member is denied."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-outsider-list"
        )
        outsider_headers, _ = await _new_member(client)

        response = await client.get(f"/api/v1/teams/{team_id}/members", headers=outsider_headers)

        assert response.status_code == 403
        data = await response.get_json()
        assert data["error"] == "insufficient_scope"


@pytest.mark.usefixtures("enterprise_license")
class TestAddTeamMember:
    """Add Team Member."""

    @pytest.mark.asyncio
    async def test_owner_adds_a_member(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner adds a member."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-add-ok")
        _, new_member_id = await _new_member(client)

        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": new_member_id, "role": "member"},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["user_id"] == new_member_id
        assert data["role"] == "member"

    @pytest.mark.asyncio
    async def test_missing_user_id_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Missing user id is rejected."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-add-nouid")

        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"role": "member"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_role_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Invalid role is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-add-badrole"
        )
        _, new_member_id = await _new_member(client)

        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": new_member_id, "role": "superadmin"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Missing body is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-add-nobody"
        )

        response = await client.post(f"/api/v1/teams/{team_id}/members", headers=auth_headers)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_user_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Nonexistent user is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-add-nouser"
        )

        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": 9_999_999, "role": "member"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_already_member_is_a_conflict(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Already member is a conflict."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-add-dupe")
        _, new_member_id = await _new_member(client)
        await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": new_member_id, "role": "member"},
        )

        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
            json={"user_id": new_member_id, "role": "member"},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_plain_member_cannot_add_members(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Plain member cannot add members."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-add-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "member")

        _, target_id = await _new_member(client)
        response = await client.post(
            f"/api/v1/teams/{team_id}/members",
            headers=member_headers,
            json={"user_id": target_id, "role": "member"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, client: Any) -> None:
        """Unauthenticated is rejected."""
        response = await client.post("/api/v1/teams/1/members", json={"user_id": 1})
        assert response.status_code == 401


@pytest.mark.usefixtures("enterprise_license")
class TestUpdateMemberRole:
    """Update Member Role."""

    @pytest.mark.asyncio
    async def test_owner_promotes_a_member_to_admin(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner promotes a member to admin."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-role-up")
        _, new_member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, new_member_id, "member")

        response = await client.put(
            f"/api/v1/teams/{team_id}/members/{new_member_id}",
            headers=auth_headers,
            json={"role": "admin"},
        )

        assert response.status_code == 200
        data = await response.get_json()
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_invalid_role_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Invalid role is rejected."""
        team_id, owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-role-invalid"
        )

        response = await client.put(
            f"/api/v1/teams/{team_id}/members/{owner_id}",
            headers=auth_headers,
            json={"role": "superadmin"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Missing body is rejected."""
        team_id, owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-role-nobody"
        )

        response = await client.put(
            f"/api/v1/teams/{team_id}/members/{owner_id}", headers=auth_headers
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_plain_member_cannot_change_roles(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Plain member cannot change roles."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-role-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "member")

        response = await client.put(
            f"/api/v1/teams/{team_id}/members/{member_id}",
            headers=member_headers,
            json={"role": "admin"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, client: Any) -> None:
        """Unauthenticated is rejected."""
        response = await client.put("/api/v1/teams/1/members/1", json={"role": "admin"})
        assert response.status_code == 401


@pytest.mark.usefixtures("enterprise_license")
class TestRemoveTeamMember:
    """Remove Team Member."""

    @pytest.mark.asyncio
    async def test_owner_removes_a_member(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner removes a member."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-remove-ok")
        _, new_member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, new_member_id, "member")

        response = await client.delete(
            f"/api/v1/teams/{team_id}/members/{new_member_id}", headers=auth_headers
        )

        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Member removed"

        listing = await client.get(f"/api/v1/teams/{team_id}/members", headers=auth_headers)
        assert (await listing.get_json())["count"] == 1

    @pytest.mark.asyncio
    async def test_removing_a_non_member_is_not_found(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Removing a non member is not found."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-remove-404"
        )

        response = await client.delete(
            f"/api/v1/teams/{team_id}/members/9999999", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_plain_member_cannot_remove_members(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Plain member cannot remove members."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-remove-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "member")

        response = await client.delete(
            f"/api/v1/teams/{team_id}/members/{member_id}", headers=member_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, client: Any) -> None:
        """Unauthenticated is rejected."""
        response = await client.delete("/api/v1/teams/1/members/1")
        assert response.status_code == 401


@pytest.mark.usefixtures("enterprise_license")
class TestGetUpdateDeleteTeamWithRealOwnership:
    """Get Update Delete Team With Real Ownership."""

    @pytest.mark.asyncio
    async def test_owner_can_read_team_details(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner can read team details."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-get-ok")

        response = await client.get(f"/api/v1/teams/{team_id}", headers=auth_headers)

        assert response.status_code == 200
        assert (await response.get_json())["id"] == team_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_numeric_team_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Get nonexistent numeric team is not found."""
        response = await client.get("/api/v1/teams/9999999", headers=auth_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Team not found"

    @pytest.mark.asyncio
    async def test_owner_updates_team_name(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner updates team name."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-update-name"
        )

        response = await client.put(
            f"/api/v1/teams/{team_id}", headers=auth_headers, json={"name": "Renamed Team"}
        )

        assert response.status_code == 200
        assert (await response.get_json())["name"] == "Renamed Team"

    @pytest.mark.asyncio
    async def test_update_with_no_recognized_fields_leaves_team_unchanged(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """An overlong name is accepted but silently not applied (no error)."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-update-noop"
        )

        response = await client.put(
            f"/api/v1/teams/{team_id}", headers=auth_headers, json={"name": "x" * 300}
        )

        assert response.status_code == 200
        assert (await response.get_json())["name"] == "Membership Test Team"

    @pytest.mark.asyncio
    async def test_update_missing_body_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Update missing body is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-update-nobody"
        )

        response = await client.put(f"/api/v1/teams/{team_id}", headers=auth_headers)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_on_nonexistent_team_is_denied_by_scope_before_404(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """update_team_endpoint checks scope BEFORE existence.

        A caller with no membership row for an unowned/nonexistent team id
        is refused by the 403 authz gate, never reaching the 404 branch.
        This pins that ordering so a future refactor that flips it is a
        visible behaviour change, not a silent one.
        """
        response = await client.put(
            "/api/v1/teams/9999999", headers=auth_headers, json={"name": "x"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_deletes_team_returns_200_with_message(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner deletes team returns 200 with message."""
        team_id, _owner_id = await _make_owned_team(client, app, auth_headers, slug="tmm-delete-ok")

        response = await client.delete(f"/api/v1/teams/{team_id}", headers=auth_headers)

        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Team deleted"

        followup = await client.get(f"/api/v1/teams/{team_id}", headers=auth_headers)
        assert followup.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_team_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Delete nonexistent team is not found."""
        response = await client.delete("/api/v1/teams/9999999", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_owner_cannot_delete(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Non owner cannot delete."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-delete-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "admin")

        response = await client.delete(f"/api/v1/teams/{team_id}", headers=member_headers)

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "Only owner can delete team"

    @pytest.mark.asyncio
    async def test_unauthenticated_get_is_rejected(self, client: Any) -> None:
        """Unauthenticated get is rejected."""
        response = await client.get("/api/v1/teams/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_update_is_rejected(self, client: Any) -> None:
        """Unauthenticated update is rejected."""
        response = await client.put("/api/v1/teams/1", json={"name": "x"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_delete_is_rejected(self, client: Any) -> None:
        """Unauthenticated delete is rejected."""
        response = await client.delete("/api/v1/teams/1")
        assert response.status_code == 401


@pytest.mark.usefixtures("enterprise_license")
class TestInvitationValidationPreChecks:
    """Only the branches that return BEFORE touching db.team_invitations.

    models.py defines no team_invitations table (see this file's module
    docstring and test_teams.py's xfails) -- any path that reaches the
    table raises AttributeError. These pre-checks are real, working
    validation logic that happens to sit in front of that gap.
    """

    @pytest.mark.asyncio
    async def test_send_invitation_missing_body_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Send invitation missing body is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-invite-nobody"
        )

        response = await client.post(f"/api/v1/teams/{team_id}/invitations", headers=auth_headers)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_send_invitation_missing_email_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Send invitation missing email is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-invite-noemail"
        )

        response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"role": "member"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_send_invitation_invalid_role_is_rejected(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Send invitation invalid role is rejected."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-invite-badrole"
        )

        response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"email": "x@example.com", "role": "superadmin"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_send_invitation_denied_for_plain_member_before_table_access(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Send invitation denied for plain member before table access."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-invite-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "member")

        response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=member_headers,
            json={"email": "x@example.com", "role": "member"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_send_invitation_unauthenticated_is_rejected(self, client: Any) -> None:
        """Send invitation unauthenticated is rejected."""
        response = await client.post("/api/v1/teams/1/invitations", json={"email": "x@example.com"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_invitation_denied_for_plain_member_before_table_access(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Cancel invitation denied for plain member before table access."""
        team_id, _owner_id = await _make_owned_team(
            client, app, auth_headers, slug="tmm-cancel-forbidden"
        )
        member_headers, member_id = await _new_member(client)
        async with app.app_context():
            from app.models import add_team_member

            await add_team_member(team_id, member_id, "member")

        response = await client.delete(
            f"/api/v1/teams/{team_id}/invitations/1", headers=member_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cancel_invitation_unauthenticated_is_rejected(self, client: Any) -> None:
        """Cancel invitation unauthenticated is rejected."""
        response = await client.delete("/api/v1/teams/1/invitations/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_accept_invitation_unauthenticated_is_rejected(self, client: Any) -> None:
        """Accept invitation unauthenticated is rejected."""
        response = await client.post(
            "/api/v1/teams/invitations/some-token/accept", json={"email": "x@example.com"}
        )
        assert response.status_code == 401


class TestTeamModelHelpersDirect:
    """models.py team helper functions exercised directly (app context only).

    get_user_team_role and get_team_members back every endpoint above; this
    covers their own not-found/empty-result branches, which the HTTP-level
    tests don't reach directly.
    """

    @pytest.mark.asyncio
    async def test_get_user_team_role_returns_none_for_non_member(self, app: Quart) -> None:
        """Get user team role returns none for non member."""
        async with app.app_context():
            from app.models import get_user_team_role

            role = await get_user_team_role(999999, 999999)
        assert role is None

    @pytest.mark.asyncio
    async def test_get_team_members_empty_for_unknown_team(self, app: Quart) -> None:
        """Get team members empty for unknown team."""
        async with app.app_context():
            from app.models import get_team_members

            members = await get_team_members(999999)
        assert members == []

    @pytest.mark.asyncio
    async def test_get_team_by_id_returns_none_for_unknown_team(self, app: Quart) -> None:
        """Get team by id returns none for unknown team."""
        async with app.app_context():
            from app.models import get_team_by_id

            team = await get_team_by_id(999999)
        assert team is None
