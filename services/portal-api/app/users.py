"""User Management Endpoints (platform-scope gated, async Quart).

Platform user administration is gated on ``users:read`` / ``users:manage``
rather than on the user row's role name. The scopes are expanded from
that role at token issue time (app.tenancy.authz.platform_scopes), so the
authority is identical while the decision here is made on a scope —
security.md requires the latter, and the previous ``@admin_required``
compared a role name inside the request.
"""

from typing import Any

from quart import Blueprint, request

from .auth import hash_password_async, verify_password_async
from .authz import SCOPE_AUDIT_READ, SCOPE_USERS_MANAGE, SCOPE_USERS_READ, require_scope
from .middleware import auth_required, get_current_user
from .models import (
    VALID_ROLES,
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    update_user,
)

users_bp = Blueprint("users", __name__)


@users_bp.route("", methods=["GET"])
@auth_required
@require_scope(SCOPE_USERS_READ)
async def get_users() -> tuple[dict[str, Any], int]:
    """List all users with pagination (Admin only)."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Limit per_page to reasonable bounds
    per_page = min(max(per_page, 1), 100)

    users, total = await list_users(page=page, per_page=per_page)

    # Remove password hashes from response
    for user in users:
        user.pop("password_hash", None)

    return {
        "users": users,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }, 200


@users_bp.route("/<int:user_id>", methods=["GET"])
@auth_required
@require_scope(SCOPE_USERS_READ)
async def get_user(user_id: int) -> tuple[dict[str, Any], int]:
    """Get single user by ID (Admin only)."""
    user = await get_user_by_id(user_id)

    if not user:
        return {"error": "User not found"}, 404

    # Remove password hash from response
    user.pop("password_hash", None)

    return user, 200


@users_bp.route("", methods=["POST"])
@auth_required
@require_scope(SCOPE_USERS_MANAGE)
async def create_new_user() -> tuple[dict[str, Any], int]:
    """Create new user (Admin only)."""
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    role = data.get("role", "viewer")

    # Validation
    if not email:
        return {"error": "Email is required"}, 400

    if not password or len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400

    if role not in VALID_ROLES:
        return {"error": f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"}, 400

    # Check if user exists
    existing = await get_user_by_email(email)
    if existing is not None:
        return {"error": "Email already registered"}, 409

    # Create user
    password_hash = await hash_password_async(password)
    user = await create_user(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
    )

    if not user:
        return {"error": "Failed to create user"}, 500

    # Remove password hash from response
    user.pop("password_hash", None)

    return {
        "message": "User created successfully",
        "user": user,
    }, 201


@users_bp.route("/<int:user_id>", methods=["PUT"])
@auth_required
@require_scope(SCOPE_USERS_MANAGE)
async def update_existing_user(user_id: int) -> tuple[dict[str, Any], int]:
    """Update user by ID (Admin only)."""
    user = await get_user_by_id(user_id)

    if not user:
        return {"error": "User not found"}, 404

    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    update_data: dict[str, Any] = {}

    # Email update
    if "email" in data:
        email = data["email"].strip().lower()
        if email != user["email"]:
            existing = await get_user_by_email(email)
            if existing is not None:
                return {"error": "Email already in use"}, 409
            update_data["email"] = email

    # Full name update
    if "full_name" in data:
        update_data["full_name"] = data["full_name"].strip()

    # Role update
    if "role" in data:
        role = data["role"]
        if role not in VALID_ROLES:
            return {
                "error": f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
            }, 400
        update_data["role"] = role

    # Active status update
    if "is_active" in data:
        update_data["is_active"] = bool(data["is_active"])

    # Password update
    if "password" in data:
        password = data["password"]
        if len(password) < 8:
            return {"error": "Password must be at least 8 characters"}, 400
        update_data["password_hash"] = await hash_password_async(password)

    if not update_data:
        return {"error": "No valid fields to update"}, 400

    updated_user = await update_user(user_id, **update_data)

    if not updated_user:
        return {"error": "Failed to update user"}, 500

    # Remove password hash from response
    updated_user.pop("password_hash", None)

    return {
        "message": "User updated successfully",
        "user": updated_user,
    }, 200


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@auth_required
@require_scope(SCOPE_USERS_MANAGE)
async def delete_existing_user(user_id: int) -> tuple[dict[str, Any], int]:
    """Delete user by ID (Admin only)."""
    current_user = get_current_user()
    if not current_user:
        return {"error": "User not authenticated"}, 401

    # Prevent self-deletion
    if current_user["id"] == user_id:
        return {"error": "Cannot delete your own account"}, 400

    user = await get_user_by_id(user_id)

    if not user:
        return {"error": "User not found"}, 404

    success = await delete_user(user_id)

    if not success:
        return {"error": "Failed to delete user"}, 500

    return {"message": "User deleted successfully"}, 200


@users_bp.route("/roles", methods=["GET"])
@auth_required
@require_scope(SCOPE_USERS_READ)
async def get_roles() -> tuple[dict[str, Any], int]:
    """Get list of valid roles (Admin only)."""
    return {
        "roles": VALID_ROLES,
        "descriptions": {
            "admin": "Full access: user CRUD, settings, all features",
            "maintainer": "Read/write access to resources, no user management",
            "viewer": "Read-only access to resources",
        },
    }, 200


@users_bp.route("/me", methods=["GET"])
@auth_required
async def get_profile() -> tuple[dict[str, Any], int]:
    """Get own profile."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    user.pop("password_hash", None)
    return user, 200


@users_bp.route("/me", methods=["PUT"])
@auth_required
async def update_profile() -> tuple[dict[str, Any], int]:
    """Update own profile."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    update_data: dict[str, Any] = {}

    if "full_name" in data:
        update_data["full_name"] = data["full_name"].strip()

    if "email" in data:
        email = data["email"].strip().lower()
        if email != user["email"]:
            existing = await get_user_by_email(email)
            if existing is not None:
                return {"error": "Email already in use"}, 409
            update_data["email"] = email

    if not update_data:
        return {"error": "No fields to update"}, 400

    updated = await update_user(user["id"], **update_data)
    if not updated:
        return {"error": "Failed to update profile"}, 500

    updated.pop("password_hash", None)
    return updated, 200


@users_bp.route("/me/password", methods=["PUT"])
@auth_required
async def change_password() -> tuple[dict[str, Any], int]:
    """Change own password."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    data = await request.get_json()

    if not data or not data.get("current_password") or not data.get("new_password"):
        return {"error": "Current and new password required"}, 400

    pwd_valid = await verify_password_async(
        data["current_password"], user["password_hash"]
    )
    if not pwd_valid:
        return {"error": "Current password incorrect"}, 401

    if len(data["new_password"]) < 8:
        return {"error": "New password must be 8+ characters"}, 400

    new_hash = await hash_password_async(data["new_password"])
    await update_user(user["id"], password_hash=new_hash)
    return {"message": "Password changed"}, 200


@users_bp.route("/api-keys", methods=["GET"])
@auth_required
async def list_api_keys() -> tuple[dict[str, Any], int]:
    """List user's API keys."""
    from .auth_features import get_user_api_keys

    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    # get_user_api_keys is async; to_thread would build the coroutine in a
    # worker thread and hand it back un-awaited, so the endpoint returned a
    # coroutine object instead of the key list.
    keys = await get_user_api_keys(user["id"])
    return {"api_keys": keys}, 200


@users_bp.route("/api-keys", methods=["POST"])
@auth_required
async def create_api_key_endpoint() -> tuple[dict[str, Any], int]:
    """Create new API key."""
    from .auth_features import create_api_key

    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    data = await request.get_json()

    if not data or not data.get("name"):
        return {"error": "API key name required"}, 400

    # create_api_key is itself async — to_thread would only build the
    # coroutine in a worker thread and hand it back un-awaited.
    key, key_id = await create_api_key(
        user["id"],
        data.get("name"),
        data.get("scopes", ""),
    )
    return {
        "id": key_id,
        "name": data.get("name"),
        "key": key,
        "message": "Save key now - won't be shown again",
    }, 201


@users_bp.route("/api-keys/<int:key_id>", methods=["DELETE"])
@auth_required
async def delete_api_key(key_id: int) -> tuple[dict[str, Any], int]:
    """Revoke an API key."""
    from .auth_features import revoke_api_key

    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    # revoke_api_key is async. Wrapped in to_thread it produced an un-awaited
    # coroutine — always truthy — so this endpoint reported success without
    # revoking anything, and the ownership predicate in its WHERE clause
    # (user_id == caller) could never fail. Direct await restores both the
    # revocation and the 404 on a key the caller does not own.
    success = await revoke_api_key(key_id, user["id"])
    if success:
        return {"message": "API key revoked"}, 200
    return {"error": "API key not found"}, 404


@users_bp.route("/audit-logs", methods=["GET"])
@auth_required
@require_scope(SCOPE_AUDIT_READ)
async def get_audit_logs_endpoint() -> tuple[dict[str, Any], int]:
    """Get audit logs (Admin only)."""
    from .auth_features import get_audit_logs

    limit = request.args.get("limit", 100, type=int)
    # get_audit_logs is async — see list_api_keys above.
    logs = await get_audit_logs(min(limit, 1000))
    return {"logs": logs}, 200
