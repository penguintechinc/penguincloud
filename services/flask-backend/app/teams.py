"""Team Management APIs."""

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from .middleware import auth_required, get_current_user
from .models import (
    add_team_member,
    create_team,
    get_db,
    get_team_by_id,
    get_team_members,
    get_user_by_id,
    get_user_team_role,
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
def create_team_endpoint():
    """Create new team (authenticated users)."""
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()
    description = data.get("description", "").strip()

    if not name or len(name) > 255:
        return jsonify({"error": "Team name required (1-255 chars)"}), 400

    if not slug or not validate_team_slug(slug):
        return (
            jsonify(
                {"error": "Invalid slug (3-63 chars, lowercase alphanumeric + hyphens)"}
            ),
            400,
        )

    # Check slug uniqueness
    db = get_db()
    existing = db(db.teams.slug == slug).select().first()
    if existing:
        return jsonify({"error": "Team slug already exists"}), 409

    team = create_team(name, slug, user["id"], description)
    return jsonify(team), 201


@teams_bp.route("", methods=["GET"])
@auth_required
def list_user_teams():
    """List user's teams."""
    user = get_current_user()
    teams = get_user_teams(user["id"])
    return jsonify({"teams": teams, "count": len(teams)}), 200


@teams_bp.route("/<int:team_id>", methods=["GET"])
@auth_required
def get_team_endpoint(team_id: int):
    """Get team details (team members only)."""
    user = get_current_user()
    team = get_team_by_id(team_id)

    if not team:
        return jsonify({"error": "Team not found"}), 404

    role = get_user_team_role(user["id"], team_id)
    if not role:
        return jsonify({"error": "Not a member of this team"}), 403

    return jsonify(team), 200


@teams_bp.route("/<int:team_id>", methods=["PUT"])
@auth_required
def update_team_endpoint(team_id: int):
    """Update team (team admin only)."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    team = get_team_by_id(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    db = get_db()
    update_data = {}

    if "name" in data:
        name = data.get("name", "").strip()
        if name and len(name) <= 255:
            update_data["name"] = name

    if "description" in data:
        update_data["description"] = data.get("description", "").strip()

    if update_data:
        db(db.teams.id == team_id).update(**update_data)
        db.commit()

    return jsonify(get_team_by_id(team_id)), 200


@teams_bp.route("/<int:team_id>", methods=["DELETE"])
@auth_required
def delete_team_endpoint(team_id: int):
    """Delete team (owner only)."""
    user = get_current_user()
    team = get_team_by_id(team_id)

    if not team:
        return jsonify({"error": "Team not found"}), 404

    if team.get("owner_id") != user["id"]:
        return jsonify({"error": "Only owner can delete team"}), 403

    db = get_db()
    db(db.teams.id == team_id).delete()
    db.commit()

    return jsonify({"message": "Team deleted"}), 200


@teams_bp.route("/<int:team_id>/members", methods=["GET"])
@auth_required
def list_team_members(team_id: int):
    """List team members."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if not role:
        return jsonify({"error": "Not a member of this team"}), 403

    members = get_team_members(team_id)
    return jsonify({"members": members, "count": len(members)}), 200


@teams_bp.route("/<int:team_id>/members", methods=["POST"])
@auth_required
def add_team_member_endpoint(team_id: int):
    """Add member to team (team admin only)."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    user_id = data.get("user_id")
    member_role = data.get("role", "member")

    if not user_id or member_role not in ["member", "admin"]:
        return jsonify({"error": "user_id and valid role required"}), 400

    target_user = get_user_by_id(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    db = get_db()
    existing = (
        db((db.team_members.team_id == team_id) & (db.team_members.user_id == user_id))
        .select()
        .first()
    )
    if existing:
        return jsonify({"error": "User already member"}), 409

    member = add_team_member(team_id, user_id, member_role)
    return jsonify(member), 201


@teams_bp.route("/<int:team_id>/members/<int:member_user_id>", methods=["PUT"])
@auth_required
def update_member_role(team_id: int, member_user_id: int):
    """Update member role (team admin only)."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    new_role = data.get("role")

    if not new_role or new_role not in ["member", "admin"]:
        return jsonify({"error": "Valid role required"}), 400

    db = get_db()
    db(
        (db.team_members.team_id == team_id)
        & (db.team_members.user_id == member_user_id)
    ).update(role=new_role)
    db.commit()

    member = (
        db(
            (db.team_members.team_id == team_id)
            & (db.team_members.user_id == member_user_id)
        )
        .select()
        .first()
    )

    return jsonify(member.as_dict() if member else {}), 200


@teams_bp.route("/<int:team_id>/members/<int:member_user_id>", methods=["DELETE"])
@auth_required
def remove_team_member(team_id: int, member_user_id: int):
    """Remove member from team (team admin only)."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    db = get_db()
    deleted = db(
        (db.team_members.team_id == team_id)
        & (db.team_members.user_id == member_user_id)
    ).delete()
    db.commit()

    if not deleted:
        return jsonify({"error": "Member not found"}), 404

    return jsonify({"message": "Member removed"}), 200


@teams_bp.route("/<int:team_id>/invitations", methods=["POST"])
@auth_required
def send_invitation(team_id: int):
    """Send team invitation via email."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    invite_role = data.get("role", "member")

    if not email or invite_role not in ["member", "admin"]:
        return jsonify({"error": "Email and valid role required"}), 400

    db = get_db()
    # Check if user with email exists
    target = db(db.users.email == email).select().first()
    if target:
        # Check if already member
        existing = (
            db(
                (db.team_members.team_id == team_id)
                & (db.team_members.user_id == target.id)
            )
            .select()
            .first()
        )
        if existing:
            return jsonify({"error": "User already member"}), 409

    token = generate_invitation_token()
    expires_at = datetime.utcnow() + timedelta(days=7)

    invite_id = db.team_invitations.insert(
        team_id=team_id,
        email=email,
        role=invite_role,
        token=token,
        invited_by_id=user["id"],
        expires_at=expires_at,
    )
    db.commit()

    return (
        jsonify(
            {
                "id": invite_id,
                "email": email,
                "role": invite_role,
                "token": token,
                "expires_at": expires_at.isoformat(),
            }
        ),
        201,
    )


@teams_bp.route("/invitations/<token>/accept", methods=["POST"])
@auth_required
def accept_invitation(token: str):
    """Accept team invitation."""
    user = get_current_user()
    db = get_db()

    invite = db(db.team_invitations.token == token).select().first()
    if not invite:
        return jsonify({"error": "Invitation not found"}), 404

    if invite.accepted_at:
        return jsonify({"error": "Invitation already accepted"}), 409

    if datetime.utcnow() > invite.expires_at:
        return jsonify({"error": "Invitation expired"}), 410

    if invite.email != user["email"]:
        return jsonify({"error": "Invitation not for this email"}), 403

    # Check if already member
    existing = (
        db(
            (db.team_members.team_id == invite.team_id)
            & (db.team_members.user_id == user["id"])
        )
        .select()
        .first()
    )
    if existing:
        return jsonify({"error": "User already member"}), 409

    # Add as member
    add_team_member(invite.team_id, user["id"], invite.role)
    db(db.team_invitations.id == invite.id).update(accepted_at=datetime.utcnow())
    db.commit()

    return jsonify({"message": "Invitation accepted"}), 200


@teams_bp.route("/<int:team_id>/invitations/<int:invite_id>", methods=["DELETE"])
@auth_required
def cancel_invitation(team_id: int, invite_id: int):
    """Cancel team invitation (team admin only)."""
    user = get_current_user()
    role = get_user_team_role(user["id"], team_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    db = get_db()
    invite = db(db.team_invitations.id == invite_id).select().first()

    if not invite or invite.team_id != team_id:
        return jsonify({"error": "Invitation not found"}), 404

    db(db.team_invitations.id == invite_id).delete()
    db.commit()

    return jsonify({"message": "Invitation cancelled"}), 200
