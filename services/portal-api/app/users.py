"""User Management Endpoints (platform-scope gated, async Quart).

Platform user administration is gated on ``users:read`` / ``users:manage``
rather than on the user row's role name. The scopes are expanded from
that role at token issue time (app.tenancy.authz.platform_scopes), so the
authority is identical while the decision here is made on a scope —
security.md requires the latter, and the previous ``@admin_required``
compared a role name inside the request.
"""

from dataclasses import dataclass
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_response

from . import devmode, quotas, ratelimit
from .auth import hash_password_async, verify_password_async
from .authz import (
    SCOPE_AUDIT_READ,
    SCOPE_MEMBERS_MANAGE,
    SCOPE_TENANTS_MANAGE,
    SCOPE_USERS_MANAGE,
    SCOPE_USERS_READ,
    require_scope,
    require_tenant_scope,
)
from .license import require_feature
from .middleware import auth_required, get_current_tenant_id, get_current_user
from .models import (
    VALID_ROLES,
    create_audit_log,
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    get_user_tenant_role,
    list_users,
    update_user,
)

users_bp = Blueprint("users", __name__)


def _isoformat(value: Any) -> str | None:
    """Render a datetime column as ISO-8601, tolerating NULL or a string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


@dataclass(slots=True, frozen=True)
class UserSummary:
    """One user row, as the admin listing publishes it.

    Never carries ``password_hash`` — the route pops it before this DTO is
    built. Nothing else on the users table is sensitive today, but pinning
    the field set means a column added tomorrow (an MFA secret, an SSO
    subject id) does not reach this response without a deliberate edit
    here.

    Attributes:
        id: Identifier of the user.
        email: The user's email address.
        full_name: Display name.
        role: Global role: admin, maintainer or viewer.
        is_active: Whether the account can currently authenticate.
        created_at: When the account was created, ISO-8601.
        updated_at: When the account was last modified, ISO-8601.
    """

    id: int
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: str | None
    updated_at: str | None


def _to_user_summary(user: dict[str, Any]) -> UserSummary:
    """Project a raw (password_hash-stripped) user row onto UserSummary."""
    return UserSummary(
        id=int(user["id"]),
        email=str(user.get("email") or ""),
        full_name=user.get("full_name"),
        role=str(user.get("role") or ""),
        is_active=bool(user.get("is_active")),
        created_at=_isoformat(user.get("created_at")),
        updated_at=_isoformat(user.get("updated_at")),
    )


@dataclass(slots=True, frozen=True)
class Pagination:
    """Page metadata shared by the portal's paginated list endpoints.

    Attributes:
        page: The page returned.
        per_page: Page size used.
        total: Total matching rows across every page.
        pages: Total number of pages.
    """

    page: int
    per_page: int
    total: int
    pages: int


@dataclass(slots=True, frozen=True)
class UsersListResponse:
    """Envelope for GET /api/v1/users.

    Attributes:
        users: The matching users, credentials never included.
        pagination: Page metadata for this result set.
    """

    users: list[UserSummary]
    pagination: Pagination


def _resolve_tenant_id() -> int | None:
    """The tenant this request acts on: verified claim, else explicit param.

    Same resolution the dashboard uses. The claim is read from what
    ``auth_required`` already verified — never re-decoded here — and the
    explicit parameter exists for a delegated admin acting on a descendant,
    whose own active tenant is the provider rather than the target.
    """
    claim_tenant = get_current_tenant_id()
    if claim_tenant:
        try:
            return int(claim_tenant)
        except ValueError:
            # A non-numeric tenant claim cannot address this schema's
            # integer tenants.id; fall through to the explicit param.
            pass
    return request.args.get("tenant_id", type=int)


@users_bp.route("", methods=["GET"])
@auth_required
@require_scope(SCOPE_USERS_READ)
@validate_response(UsersListResponse)
async def get_users() -> tuple[Any, int]:
    """List all users with pagination (Admin only)."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Limit per_page to reasonable bounds
    per_page = min(max(per_page, 1), 100)

    users, total = await list_users(page=page, per_page=per_page)

    # Remove password hashes from response
    for user in users:
        user.pop("password_hash", None)

    return (
        UsersListResponse(
            users=[_to_user_summary(user) for user in users],
            pagination=Pagination(
                page=page,
                per_page=per_page,
                total=total,
                pages=(total + per_page - 1) // per_page,
            ),
        ),
        200,
    )


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

    # Same dev-mode cap as the self-service path: an admin creating users
    # by hand is still bound by the single-user evaluation limit.
    refusal = await devmode.user_creation_refusal()
    if refusal is not None:
        return refusal

    # Global admins: 1 / 1 / unlimited. Non-admin members are unlimited at
    # every tier, so only the admin role is metered — a viewer or
    # maintainer passes straight through.
    if role == "admin":
        quota_refusal = await quotas.quota_refusal(
            "global_admins", await quotas.count_global_admins()
        )
        if quota_refusal is not None:
            return quota_refusal

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
            return {"error": f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"}, 400
        # Promoting an existing user is the other way to gain a global
        # admin. Metering only the create path would leave "create as
        # viewer, then promote" as an unmetered route to the same
        # structure. Re-promoting someone already admin is a no-op and must
        # not be refused for a seat they already occupy.
        if role == "admin" and user.get("role") != "admin":
            quota_refusal = await quotas.quota_refusal(
                "global_admins", await quotas.count_global_admins()
            )
            if quota_refusal is not None:
                return quota_refusal
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
    if not current_user:  # pragma: no cover - auth_required guarantees a user
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
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    user.pop("password_hash", None)
    return user, 200


@users_bp.route("/me", methods=["PUT"])
@auth_required
async def update_profile() -> tuple[dict[str, Any], int]:
    """Update own profile."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
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
@ratelimit.rate_limited("change_password", account_key_fn=ratelimit.user_account_key)
async def change_password() -> tuple[dict[str, Any], int]:
    """Change own password."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    data = await request.get_json()

    if not data or not data.get("current_password") or not data.get("new_password"):
        return {"error": "Current and new password required"}, 400

    pwd_valid = await verify_password_async(data["current_password"], user["password_hash"])
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
    if not user:  # pragma: no cover - auth_required guarantees a user
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
    if not user:  # pragma: no cover - auth_required guarantees a user
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
    if not user:  # pragma: no cover - auth_required guarantees a user
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
@require_feature("audit_logs")
async def get_audit_logs_endpoint() -> tuple[dict[str, Any], int]:
    """Get audit logs for one tenant. Requires audit:read and tenants:manage."""
    # NOTE: this docstring is EXPORTED into openapi/v1.yaml as the
    # operation description, so the rationale lives in comments. Publishing
    # a narrative of a fixed disclosure defect to anyone who can read the
    # spec is not documentation.
    #
    # This route had no tenant predicate: it served db(db.audit_logs.id > 0)
    # — the whole deployment — to any caller holding audit:read in any
    # tenant. It also carried no licence gate, so it was a third door onto
    # the audit trail that walked around the Enterprise gate on
    # /api/v1/audit/logs and /api/v1/audit/export.
    #
    # Both are fixed, and the tenant scoping is the load-bearing half: it
    # would be required even if audit were free on every tier.
    #
    # Tenancy follows the same shape as /api/v1/audit/logs and the
    # dashboard: the tenant comes from the verified claim, or from an
    # explicit tenant_id for a delegated MSP admin acting on a descendant —
    # and authority over it is asked as a SCOPE, so a delegated admin (who
    # has no tenant_members row in the descendant) is answered the same way
    # the rest of the API answers them, rather than being silently refused.
    from .auth_features import get_audit_logs

    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    tenant_id = _resolve_tenant_id()
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    # TENANT authority is asked with a TENANT-minted scope. `audit:read` is
    # platform-only (_PLATFORM_ROLE_SCOPES); resolve_scopes never mints it
    # per tenant, so requiring it here would 403 every token the portal can
    # issue — a gate that looks tighter and is simply dead. `tenants:manage`
    # is what /api/v1/audit/logs asks for the same trail, so the two routes
    # answer the same caller the same way.
    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_TENANTS_MANAGE)
    if denied:
        return denied

    limit = request.args.get("limit", 100, type=int)
    # get_audit_logs is async — see list_api_keys above.
    logs = await get_audit_logs(tenant_id, min(limit, 1000))
    return {"logs": logs}, 200


@dataclass(slots=True, frozen=True)
class RateLimitResetResponse:
    """Envelope for POST /api/v1/users/<user_id>/rate-limit-reset.

    Attributes:
        message: Human-readable confirmation.
        user_id: The user whose lockout bucket was cleared.
        bucket: Which credential bucket was cleared.
    """

    message: str
    user_id: int
    bucket: str


@users_bp.route("/<int:user_id>/rate-limit-reset", methods=["POST"])
@auth_required
@ratelimit.rate_limited("admin_ratelimit_reset", account_key_fn=ratelimit.user_account_key)
@validate_response(RateLimitResetResponse)
async def reset_user_rate_limit(user_id: int) -> tuple[Any, int]:
    """Clear one credential-lockout bucket for a user (holders of members:manage).

    An operator-facing escape hatch for app.ratelimit's account-scoped
    windows: without it, a locked-out user waits out the TTL (up to 1h) or
    an operator opens a Python shell against production to call
    :func:`app.ratelimit.rate_limit_reset` by hand — see that module's
    docstring.

    ``tenant_id`` is REQUIRED in the body, not derived from the target
    user, and the caller's authority is checked against exactly that
    tenant — the same shape ``GET /api/v1/users/audit-logs`` uses, and for
    the same reason: that route used to read ``db(db.audit_logs.id > 0)``,
    every row in the deployment, behind a scope check with no tenant
    predicate. The check below closes the same class of leak here: naming
    a tenant the caller genuinely administers is not enough on its own — the
    membership lookup a few lines down also requires ``user_id`` to be a
    MEMBER of that exact tenant, so a delegated admin of tenant A cannot
    reach a user who only exists in tenant B by naming A. Scope is checked
    BEFORE that membership lookup runs, so a caller with no authority over
    ``tenant_id`` at all learns nothing about who is or is not a member of
    it — the 403 and the 404 never depend on each other's timing or
    presence.

    Clears BOTH key shapes app.ratelimit's account-scoped buckets can use
    (the submitted email for ``login``/``forgot_password``, and
    ``user:<id>`` for the MFA/change-password buckets) rather than
    hand-mapping which bucket uses which — deleting a key that was never
    set is a no-op, and a hand-maintained bucket->key-shape table is
    exactly the kind of parallel structure that drifts silently the day a
    new bucket is added and only one side of it is updated.
    """
    admin = get_current_user()
    if not admin:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    data = await request.get_json(silent=True) or {}
    tenant_id = data.get("tenant_id")
    bucket = data.get("bucket")

    # `isinstance(tenant_id, bool)` guard: bool is an int subclass, and
    # `True` would otherwise resolve to tenant 1 (see
    # app.authz._coerce_tenant_id, which guards the same trap).
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool):
        return {"error": "tenant_id required"}, 400
    if bucket not in ratelimit.CLEARABLE_ACCOUNT_BUCKETS:
        return {
            "error": "Invalid bucket. Must be one of: "
            + ", ".join(sorted(ratelimit.CLEARABLE_ACCOUNT_BUCKETS))
        }, 400

    # Authority over the NAMED tenant, checked before anything about the
    # target user is looked up — see docstring.
    denied = await require_tenant_scope(admin["id"], tenant_id, SCOPE_MEMBERS_MANAGE)
    if denied:
        return denied

    # Direct membership only, deliberately (see app.tenants
    # add_tenant_member_endpoint for the same reasoning): this is what
    # stops "name a tenant I administer" from being sufficient to reach a
    # user who is not actually in it. A nonexistent user_id and a real
    # user_id who simply isn't a member of tenant_id are answered
    # identically — neither leaks which case occurred.
    if await get_user_tenant_role(user_id, tenant_id) is None:
        return {"error": "User not found"}, 404

    target = await get_user_by_id(user_id)
    if not target:  # pragma: no cover - membership row implies the user exists
        return {"error": "User not found"}, 404

    email = str(target.get("email") or "").strip().lower()
    if email:
        await ratelimit.rate_limit_reset(bucket, account_key=email)
    await ratelimit.rate_limit_reset(bucket, account_key=f"user:{user_id}")

    await create_audit_log(
        user_id=admin["id"],
        tenant_id=tenant_id,
        action="user.ratelimit.reset",
        resource_type="user",
        resource_id=str(user_id),
        changes=bucket,
        ip_address=request.remote_addr or "unknown",
    )

    return (
        RateLimitResetResponse(
            message="Rate limit cleared",
            user_id=user_id,
            bucket=bucket,
        ),
        200,
    )
