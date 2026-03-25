"""Authentication Endpoints."""

import hashlib
from datetime import datetime

import bcrypt
import jwt
import pyotp
from flask import Blueprint, current_app, jsonify, request

from .middleware import auth_required, get_current_user
from .models import (
    create_user,
    get_mfa_secret,
    get_user_by_email,
    is_mfa_enabled,
    is_refresh_token_valid,
    revoke_all_user_tokens,
    revoke_refresh_token,
    store_refresh_token,
)

auth_bp = Blueprint("auth", __name__)


def get_limiter():
    """Get the rate limiter instance."""
    from . import limiter

    return limiter


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int, role: str, team_ids: list = None) -> str:
    """Create JWT access token with team context."""
    from .models import get_user_teams

    if team_ids is None:
        teams = get_user_teams(user_id)
        team_ids = [t["id"] for t in teams]

    expires = datetime.utcnow() + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    payload = {
        "sub": str(user_id),
        "role": role,
        "team_ids": team_ids,
        "current_team_id": team_ids[0] if team_ids else None,
        "type": "access",
        "exp": expires,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def create_refresh_token(user_id: int) -> tuple[str, datetime]:
    """Create JWT refresh token and store hash in database."""
    expires = datetime.utcnow() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expires,
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")

    # Store hash of token in database for revocation
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    store_refresh_token(user_id, token_hash, expires)

    return token, expires


@auth_bp.route("/login", methods=["POST"])
@get_limiter().limit("10 per minute")
def login():
    """Login endpoint - returns access and refresh tokens."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    totp_code = data.get("mfa_code", "")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    # Find user
    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    # Verify password
    if not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401

    # Check if user is active
    if not user.get("is_active"):
        return jsonify({"error": "Account is deactivated"}), 401

    # Check MFA requirement
    if is_mfa_enabled(user["id"]):
        if not totp_code:
            return jsonify({"error": "MFA code required", "mfa_required": True}), 401

        # Verify TOTP code
        mfa = get_mfa_secret(user["id"])
        if not mfa:
            return jsonify({"error": "MFA configuration error"}), 500

        totp = pyotp.TOTP(mfa["secret"])
        if not totp.verify(totp_code, valid_window=1):
            return jsonify({"error": "Invalid MFA code"}), 401

    # Generate tokens
    access_token = create_access_token(user["id"], user["role"])
    refresh_token, refresh_expires = create_refresh_token(user["id"])

    return (
        jsonify(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": int(
                    current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
                ),
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "full_name": user.get("full_name", ""),
                    "role": user["role"],
                },
            }
        ),
        200,
    )


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """Refresh access token using refresh token."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    refresh_token = data.get("refresh_token", "")

    if not refresh_token:
        return jsonify({"error": "Refresh token required"}), 400

    # Decode token
    try:
        payload = jwt.decode(
            refresh_token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Refresh token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid refresh token"}), 401

    # Verify token type
    if payload.get("type") != "refresh":
        return jsonify({"error": "Invalid token type"}), 401

    # Check if token is revoked
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    if not is_refresh_token_valid(token_hash):
        return jsonify({"error": "Refresh token has been revoked"}), 401

    # Get user
    user_id = int(payload["sub"])
    from .models import get_user_by_id

    user = get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        return jsonify({"error": "User not found or deactivated"}), 401

    # Revoke old refresh token
    revoke_refresh_token(token_hash)

    # Generate new tokens
    access_token = create_access_token(user["id"], user["role"])
    new_refresh_token, refresh_expires = create_refresh_token(user["id"])

    return (
        jsonify(
            {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "token_type": "Bearer",
                "expires_in": int(
                    current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
                ),
            }
        ),
        200,
    )


@auth_bp.route("/logout", methods=["POST"])
@auth_required
def logout():
    """Logout endpoint - revokes all refresh tokens for user."""
    user = get_current_user()

    # Revoke all user's refresh tokens
    revoked_count = revoke_all_user_tokens(user["id"])

    return (
        jsonify(
            {
                "message": "Successfully logged out",
                "tokens_revoked": revoked_count,
            }
        ),
        200,
    )


@auth_bp.route("/me", methods=["GET"])
@auth_required
def get_me():
    """Get current user profile."""
    user = get_current_user()

    return (
        jsonify(
            {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user["role"],
                "is_active": user["is_active"],
                "created_at": (
                    user["created_at"].isoformat() if user.get("created_at") else None
                ),
            }
        ),
        200,
    )


@auth_bp.route("/register", methods=["POST"])
@get_limiter().limit("5 per minute")
def register():
    """Register new user (creates viewer role by default + personal team)."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()

    # Validation
    if not email:
        return jsonify({"error": "Email is required"}), 400

    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    # Check if user exists
    existing = get_user_by_email(email)
    if existing:
        return jsonify({"error": "Email already registered"}), 409

    # Create user
    password_hash = hash_password(password)
    user = create_user(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role="viewer",  # Default role for self-registration
    )

    # Create personal team
    from .models import create_team

    user_name = full_name or email.split("@")[0]
    team_slug = email.split("@")[0].lower().replace(".", "-")
    personal_team = create_team(
        name=f"{user_name}'s Team",
        slug=team_slug,
        owner_id=user["id"],
        description="Personal team",
    )

    return (
        jsonify(
            {
                "message": "Registration successful",
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "full_name": user.get("full_name", ""),
                    "role": user["role"],
                },
                "personal_team": {
                    "id": personal_team["id"],
                    "name": personal_team["name"],
                    "slug": personal_team["slug"],
                },
            }
        ),
        201,
    )


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """Request password reset token."""
    data = request.get_json()
    if not data or not data.get("email"):
        return jsonify({"error": "Email required"}), 400

    email = data.get("email", "").strip().lower()
    user = get_user_by_email(email)
    if not user:
        return jsonify({"message": "If email exists, reset link sent"}), 200

    from .auth_features import create_password_reset_token

    token, expires = create_password_reset_token(user["id"])
    return jsonify({"message": "Reset link sent", "token": token}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """Reset password with token."""
    data = request.get_json()
    if not data or not data.get("token") or not data.get("password"):
        return jsonify({"error": "Token and password required"}), 400

    from .auth_features import mark_token_used, validate_password_reset_token

    user_id = validate_password_reset_token(data["token"])
    if not user_id:
        return jsonify({"error": "Invalid or expired token"}), 401

    password = data.get("password", "")
    if len(password) < 8:
        return jsonify({"error": "Password must be 8+ characters"}), 400

    from .models import update_user

    password_hash = hash_password(password)
    update_user(user_id, password_hash=password_hash)
    mark_token_used(data["token"])
    return jsonify({"message": "Password reset successful"}), 200


@auth_bp.route("/confirm-email/<token>", methods=["POST"])
def confirm_email(token):
    """Confirm email with token."""
    from .auth_features import confirm_email, validate_email_token

    user_id = validate_email_token(token)
    if not user_id:
        return jsonify({"error": "Invalid or expired token"}), 401

    confirm_email(token)
    return jsonify({"message": "Email confirmed"}), 200


@auth_bp.route("/sessions", methods=["GET"])
@auth_required
def list_sessions():
    """List active sessions."""
    user = get_current_user()
    from .auth_features import get_user_sessions

    sessions = get_user_sessions(user["id"])
    return jsonify({"sessions": sessions}), 200


@auth_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@auth_required
def revoke_session_endpoint(session_id):
    """Revoke a session."""
    user = get_current_user()
    from .auth_features import revoke_session

    if revoke_session(session_id, user["id"]):
        return jsonify({"message": "Session revoked"}), 200
    return jsonify({"error": "Session not found"}), 404
