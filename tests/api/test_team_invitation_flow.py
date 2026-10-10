"""Team invitation flow tests: send -> accept -> membership, expiry, cancel.

Exercises the paths app/teams.py's send_invitation/accept_invitation/
cancel_invitation always had but could never reach until fix/team-
invitations closed two linked gaps: the missing team_invitations table
(see alembic/versions/f4358cd0f8de_add_team_invitations.py and
app.models_sqlalchemy.TeamInvitation) and create_team() not enrolling its
own creator as a team_members row (app.models.create_team). Complements
tests/api/test_teams.py's un-xfailed TestTeamInvitations (shape/pre-check
assertions) and tests/api/test_team_membership_management.py's
TestInvitationValidationPreChecks (denial-before-table-access branches) by
covering the success paths, real membership side effects, expiry
enforcement and token-vs-account email matching those two files
deliberately left unexercised while the table didn't exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from quart import Quart


async def _register(client: Any, *, prefix: str) -> tuple[dict[str, str], int, str]:
    """Register a distinct user; return (auth headers, user id, email)."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "invitepass123", "full_name": prefix.title()},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "invitepass123"}
    )
    assert login.status_code == 200
    token = (await login.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id, email


@pytest.mark.usefixtures("enterprise_license")
class TestInvitationSendAcceptFlow:
    """The real send -> accept -> membership path, end to end.

    ``enterprise_license`` on every class here: ``auth_headers``' owner
    already consumed the Free tier's one team via registration's personal
    team (see app/auth.py's ``create_team`` call), so every test creating
    an additional team for the invitation flow needs the paid tier's
    unlimited team quota — the same reasoning test_teams.py documents for
    its own multi-team tests.
    """

    @pytest.mark.asyncio
    async def test_send_then_accept_creates_membership(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Owner sends an invitation; invitee accepts; membership appears."""
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Invite Flow Team", "slug": "tif-send-accept"},
        )
        assert create_response.status_code == 201, await create_response.get_json()
        team_id = int((await create_response.get_json())["id"])

        invitee_headers, invitee_id, invitee_email = await _register(client, prefix="invitee")

        send_response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"email": invitee_email, "role": "admin"},
        )
        assert send_response.status_code == 201, await send_response.get_json()
        token = (await send_response.get_json())["token"]
        assert token

        accept_response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=invitee_headers,
        )
        assert accept_response.status_code == 200, await accept_response.get_json()

        members_response = await client.get(
            f"/api/v1/teams/{team_id}/members", headers=auth_headers
        )
        assert members_response.status_code == 200
        members = (await members_response.get_json())["members"]
        invitee_rows = [m for m in members if m["user_id"] == invitee_id]
        assert len(invitee_rows) == 1
        assert invitee_rows[0]["role"] == "admin"

        # Accepting a second time is refused -- the invite is now resolved.
        replay_response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=invitee_headers,
        )
        assert replay_response.status_code == 409

    @pytest.mark.asyncio
    async def test_accept_rejects_expired_invitation(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """An invitation past its expires_at is refused, not silently honoured."""
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Invite Flow Team", "slug": "tif-expired"},
        )
        assert create_response.status_code == 201
        team_id = int((await create_response.get_json())["id"])

        invitee_headers, _invitee_id, invitee_email = await _register(client, prefix="expiree")

        send_response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"email": invitee_email, "role": "member"},
        )
        assert send_response.status_code == 201
        token = (await send_response.get_json())["token"]

        # Force the stored expiry into the past -- the 7-day default isn't
        # something a test can wait out. This is the equivalent of
        # accept_invitation reading an invitation that has already expired,
        # which is exactly what it must reject.
        async with app.app_context():
            from app.models import get_db

            db = get_db()
            await db(db.team_invitations.token == token).update(
                expires_at=datetime.now(UTC) - timedelta(days=1)
            )
            await db.commit()

        accept_response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=invitee_headers,
        )
        assert accept_response.status_code == 410
        data = await accept_response.get_json()
        assert "expired" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_accept_rejects_mismatched_email(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A token minted for one email cannot be accepted by another account."""
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Invite Flow Team", "slug": "tif-wrong-email"},
        )
        assert create_response.status_code == 201
        team_id = int((await create_response.get_json())["id"])

        invitee_headers, _invitee_id, invitee_email = await _register(client, prefix="intended")
        bystander_headers, _bystander_id, _bystander_email = await _register(
            client, prefix="bystander"
        )

        send_response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"email": invitee_email, "role": "member"},
        )
        assert send_response.status_code == 201
        token = (await send_response.get_json())["token"]

        # The bystander is logged in, but the token was minted for a
        # different email -- accept_invitation must not let account
        # identity substitute for the invited address.
        response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=bystander_headers,
        )
        assert response.status_code == 403

        # The intended invitee can still accept it afterwards.
        response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=invitee_headers,
        )
        assert response.status_code == 200


@pytest.mark.usefixtures("enterprise_license")
class TestInvitationCancellation:
    """Cancelling a pending invitation."""

    @pytest.mark.asyncio
    async def test_cancel_invitation_prevents_later_acceptance(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A cancelled invitation's token no longer resolves."""
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Invite Flow Team", "slug": "tif-cancel"},
        )
        assert create_response.status_code == 201
        team_id = int((await create_response.get_json())["id"])

        invitee_headers, _invitee_id, invitee_email = await _register(client, prefix="cancelled")

        send_response = await client.post(
            f"/api/v1/teams/{team_id}/invitations",
            headers=auth_headers,
            json={"email": invitee_email, "role": "member"},
        )
        assert send_response.status_code == 201
        invite = await send_response.get_json()
        token = invite["token"]
        invite_id = invite["id"]

        cancel_response = await client.delete(
            f"/api/v1/teams/{team_id}/invitations/{invite_id}", headers=auth_headers
        )
        assert cancel_response.status_code == 200

        accept_response = await client.post(
            f"/api/v1/teams/invitations/{token}/accept",
            headers=invitee_headers,
        )
        assert accept_response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_invitation_for_wrong_team_is_not_found(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """A real invite id scoped to a different team cannot be cancelled."""
        team_a_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Team A", "slug": "tif-cancel-team-a"},
        )
        assert team_a_response.status_code == 201
        team_a_id = int((await team_a_response.get_json())["id"])

        team_b_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Team B", "slug": "tif-cancel-team-b"},
        )
        assert team_b_response.status_code == 201
        team_b_id = int((await team_b_response.get_json())["id"])

        send_response = await client.post(
            f"/api/v1/teams/{team_a_id}/invitations",
            headers=auth_headers,
            json={"email": "someone@example.com", "role": "member"},
        )
        assert send_response.status_code == 201
        invite_id = (await send_response.get_json())["id"]

        response = await client.delete(
            f"/api/v1/teams/{team_b_id}/invitations/{invite_id}", headers=auth_headers
        )
        assert response.status_code == 404


@pytest.mark.usefixtures("enterprise_license")
class TestCreateTeamOwnerEnrolment:
    """create_team() enrols its creator as an owner member (Phase 1B)."""

    @pytest.mark.asyncio
    async def test_creator_is_a_genuine_owner_member(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """The creator can immediately manage the team it just made."""
        create_response = await client.post(
            "/api/v1/teams",
            headers=auth_headers,
            json={"name": "Owner Enrolment Team", "slug": "tif-owner-enrolled"},
        )
        assert create_response.status_code == 201
        team_id = int((await create_response.get_json())["id"])

        owner_response = await client.get("/api/v1/users/me", headers=auth_headers)
        owner_id = int((await owner_response.get_json())["id"])

        async with app.app_context():
            from app.models import get_user_team_role

            role = await get_user_team_role(owner_id, team_id)
        assert role == "owner"

        # No 403: the creator already holds teams:manage on their own team.
        update_response = await client.put(
            f"/api/v1/teams/{team_id}",
            headers=auth_headers,
            json={"name": "Renamed"},
        )
        assert update_response.status_code == 200
