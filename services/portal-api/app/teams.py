"""Team Management APIs (async Quart)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from quart import Blueprint, request

from .authz import SCOPE_TEAMS_MANAGE, SCOPE_TEAMS_READ, require_team_scope
from .middleware import auth_required, get_current_user
from .models import (
    add_team_member,
    create_team,
    get_db,
    get_team_by_id,
    get_team_members,
    get_user_by_id,
    get_user_teams,
)

teams_bp = Blueprint("teams", __name__)


def validate_team_slug(slug: str) -> bool:
    """Validate team slug format (lowercase alphanumeric + hyphens)."""
    if not slug or len(slug) < 3 or len(slug) > 63:
        return False
    return all(c.isalnum() or c == "-" for c in slug) and slug[0].isalnum()


def generate_invitation_token() -> str:
    """Generate secure random invitation token."""
    return secrets.token_urlsafe(32)


@teams_bp.route("", methods=["POST"])
@auth_required
async def create_team_endpoint() -> tuple[dict[str, Any], int]:
    """Create new team (authenticated users)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()

    if not name or len(name) > 255:
        return {"error": "Team name required (1-255 chars)"}, 400

    if not slug or not validate_team_slug(slug):
        return (
            {"error": "Invalid slug (3-63 chars, lowercase alphanumeric + hyphens)"},
            400,
        )

    # Check slug uniqueness
    db = get_db()
    existing = await db(db.teams.slug == slug).select()
    if existing:
        return {"error": "Team slug already exists"}, 409

    # NOTE: the `teams` table has no `description` column (see models.py
    # SQLATeam / db.define_table("teams", ...)) — any "description" sent in
    # the request body is accepted but not persisted. Team descriptions are
    # not yet part of the schema.
    team = await create_team(name, slug, user["id"])
    if team is None:
        return {"error": "Failed to create team"}, 500
    return team, 201


@teams_bp.route("", methods=["GET"])
@auth_required
async def list_user_teams() -> tuple[dict[str, Any], int]:
    """List user's teams."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    teams = await get_user_teams(user["id"])
    return {"teams": teams, "count": len(teams)}, 200


@teams_bp.route("/<int:team_id>", methods=["GET"])
@auth_required
async def get_team_endpoint(team_id: int) -> tuple[dict[str, Any], int]:
    """Get team details (team members only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    team = await get_team_by_id(team_id)

    if not team:
        return {"error": "Team not found"}, 404

    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_READ)
    if denied:
        return denied

    return team, 200


@teams_bp.route("/<int:team_id>", methods=["PUT"])
@auth_required
async def update_team_endpoint(team_id: int) -> tuple[dict[str, Any], int]:
    """Update team (team admin only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    team = await get_team_by_id(team_id)
    if not team:
        return {"error": "Team not found"}, 404

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    db = get_db()
    update_data = {}

    if "name" in data:
        name = data.get("name", "").strip()
        if name and len(name) <= 255:
            update_data["name"] = name

    # NOTE: no "description" column exists on the `teams` table (see
    # create_team_endpoint above) — a prior version of this handler wrote
    # `update_data["description"] = ...` here, which would raise at the
    # penguin-dal update() call for any request that included it. Removed rather
    # than reintroduced silently; add back only alongside a schema migration.

    if update_data:
        await db(db.teams.id == team_id).update(**update_data)
        await db.commit()

    updated_team = await get_team_by_id(team_id)
    if updated_team is None:
        return {"error": "Failed to retrieve updated team"}, 500
    return updated_team, 200


@teams_bp.route("/<int:team_id>", methods=["DELETE"])
@auth_required
async def delete_team_endpoint(team_id: int) -> tuple[dict[str, Any], int]:
    """Delete team (owner only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    team = await get_team_by_id(team_id)

    if not team:
        return {"error": "Team not found"}, 404

    if team.get("owner_id") != user["id"]:
        return {"error": "Only owner can delete team"}, 403

    db = get_db()
    await db(db.teams.id == team_id).delete()
    await db.commit()

    return {"message": "Team deleted"}, 200


@teams_bp.route("/<int:team_id>/members", methods=["GET"])
@auth_required
async def list_team_members(team_id: int) -> tuple[dict[str, Any], int]:
    """List team members."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_READ)
    if denied:
        return denied

    members = await get_team_members(team_id)
    return {"members": members, "count": len(members)}, 200


@teams_bp.route("/<int:team_id>/members", methods=["POST"])
@auth_required
async def add_team_member_endpoint(team_id: int) -> tuple[dict[str, Any], int]:
    """Add member to team (team admin only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    user_id = data.get("user_id")
    member_role = data.get("role", "member")

    if not user_id or member_role not in ["member", "admin"]:
        return {"error": "user_id and valid role required"}, 400

    target_user = await get_user_by_id(user_id)
    if not target_user:
        return {"error": "User not found"}, 404

    db = get_db()
    existing = await db(
        (db.team_members.team_id == team_id) & (db.team_members.user_id == user_id)
    ).select()
    if existing:
        return {"error": "User already member"}, 409

    member_id = await add_team_member(team_id, user_id, member_role)
    if member_id is None:
        return {"error": "Failed to add member"}, 500
    members = await db(db.team_members.id == member_id).select()
    member = dict(members[0]) if members else {}
    return member, 201


@teams_bp.route("/<int:team_id>/members/<int:member_user_id>", methods=["PUT"])
@auth_required
async def update_member_role(
    team_id: int, member_user_id: int
) -> tuple[dict[str, Any], int]:
    """Update member role (team admin only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400
    new_role = data.get("role")

    if not new_role or new_role not in ["member", "admin"]:
        return {"error": "Valid role required"}, 400

    db = get_db()
    await db(
        (db.team_members.team_id == team_id)
        & (db.team_members.user_id == member_user_id)
    ).update(role=new_role)
    await db.commit()

    members = await db(
        (db.team_members.team_id == team_id)
        & (db.team_members.user_id == member_user_id)
    ).select()
    member = dict(members[0]) if members else {}

    return member, 200


@teams_bp.route("/<int:team_id>/members/<int:member_user_id>", methods=["DELETE"])
@auth_required
async def remove_team_member(
    team_id: int, member_user_id: int
) -> tuple[dict[str, Any], int]:
    """Remove member from team (team admin only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    db = get_db()
    deleted = await db(
        (db.team_members.team_id == team_id)
        & (db.team_members.user_id == member_user_id)
    ).delete()
    await db.commit()

    if not deleted:
        return {"error": "Member not found"}, 404

    return {"message": "Member removed"}, 200


@teams_bp.route("/<int:team_id>/invitations", methods=["POST"])
@auth_required
async def send_invitation(team_id: int) -> tuple[dict[str, Any], int]:
    """Send team invitation via email."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    email = data.get("email", "").strip().lower()
    invite_role = data.get("role", "member")

    if not email or invite_role not in ["member", "admin"]:
        return {"error": "Email and valid role required"}, 400

    db = get_db()
    # Check if user with email exists
    target_users = await db(db.users.email == email).select()
    if target_users:
        target = target_users[0]
        # Check if already member
        existing = await db(
            (db.team_members.team_id == team_id)
            & (db.team_members.user_id == target["id"])
        ).select()
        if existing:
            return {"error": "User already member"}, 409

    token = generate_invitation_token()
    expires_at = datetime.now(UTC) + timedelta(days=7)

    # async_insert, not the sync insert (see auth_features.create_api_key).
    invite_id = await db.team_invitations.async_insert(
        team_id=team_id,
        email=email,
        role=invite_role,
        token=token,
        invited_by_id=user["id"],
        expires_at=expires_at,
    )
    if invite_id is None:
        return {"error": "Failed to create invitation"}, 500
    await db.commit()

    return (
        {
            "id": invite_id,
            "email": email,
            "role": invite_role,
            "token": token,
            "expires_at": expires_at.isoformat(),
        },
        201,
    )


@teams_bp.route("/invitations/<token>/accept", methods=["POST"])
@auth_required
async def accept_invitation(token: str) -> tuple[dict[str, Any], int]:
    """Accept team invitation."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    db = get_db()

    invites = await db(db.team_invitations.token == token).select()
    if not invites:
        return {"error": "Invitation not found"}, 404
    invite = invites[0]

    if invite.get("accepted_at"):
        return {"error": "Invitation already accepted"}, 409

    if datetime.now(UTC) > invite["expires_at"]:
        return {"error": "Invitation expired"}, 410

    if invite["email"] != user["email"]:
        return {"error": "Invitation not for this email"}, 403

    # Check if already member
    existing = await db(
        (db.team_members.team_id == invite["team_id"])
        & (db.team_members.user_id == user["id"])
    ).select()
    if existing:
        return {"error": "User already member"}, 409

    # Add as member
    await add_team_member(invite["team_id"], user["id"], invite["role"])
    await db(db.team_invitations.id == invite["id"]).update(
        accepted_at=datetime.now(UTC)
    )
    await db.commit()

    return {"message": "Invitation accepted"}, 200


@teams_bp.route("/<int:team_id>/invitations/<int:invite_id>", methods=["DELETE"])
@auth_required
async def cancel_invitation(team_id: int, invite_id: int) -> tuple[dict[str, Any], int]:
    """Cancel team invitation (team admin only)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    denied = await require_team_scope(user["id"], team_id, SCOPE_TEAMS_MANAGE)
    if denied:
        return denied

    db = get_db()
    invites = await db(db.team_invitations.id == invite_id).select()

    if not invites or invites[0]["team_id"] != team_id:
        return {"error": "Invitation not found"}, 404

    await db(db.team_invitations.id == invite_id).delete()
    await db.commit()

    return {"message": "Invitation cancelled"}, 200
