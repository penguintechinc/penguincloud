"""Authentication Endpoints (async Quart)."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import bcrypt
import pyotp
from penguin_aaa.authn.oidc_provider import OIDCProvider
from penguin_aaa.authn.types import Claims
from penguintechinc_utils.logging import get_logger
from quart import Blueprint, current_app, request

from . import devmode, quotas
from .config import UNSCOPED_TENANT
from .middleware import auth_required, get_current_user
from .models import (
    create_user,
    get_mfa_secret,
    get_refresh_token_by_hash,
    get_user_by_email,
    get_user_by_id,
    is_mfa_enabled,
    is_refresh_token_valid,
    revoke_all_user_tokens,
    revoke_refresh_token,
    store_refresh_token,
)

auth_bp = Blueprint("auth", __name__)

#: Sanitized structured logger. Redacts token/secret-shaped keys and email
#: addresses, so a reset-flow log line cannot leak the very material the
#: endpoint exists to keep out of band.
log = get_logger(__name__)

#: The single response /forgot-password ever produces, for every input.
#:
#: Returned verbatim whether or not the address resolves to a user: the body
#: must not distinguish the two, or the endpoint becomes an unauthenticated
#: account-enumeration oracle. It carries no reset token — the token leaves
#: the system out of band only (see _deliver_password_reset_token).
PASSWORD_RESET_ACK: Final[dict[str, str]] = {"message": "If email exists, reset link sent"}


def get_oidc_provider() -> OIDCProvider:
    """Return the OIDC provider registered by the app factory.

    Raises RuntimeError rather than returning None: create_app always
    registers a provider, so its absence is a misconfigured app, not a
    condition every caller should have to branch on.
    """
    oidc = current_app.extensions.get("oidc_provider")
    if oidc is None:
        raise RuntimeError(
            "OIDC provider not initialized — create_app() must register "
            "app.extensions['oidc_provider']"
        )
    if not isinstance(oidc, OIDCProvider):  # pragma: no cover - defensive
        raise RuntimeError(
            f"app.extensions['oidc_provider'] is {type(oidc)!r}, expected OIDCProvider"
        )
    return oidc


async def hash_password_async(password: str) -> str:
    """Hash password using bcrypt (async-wrapped)."""
    loop = asyncio.get_event_loop()
    hashed = await loop.run_in_executor(
        None, lambda: bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    )
    return hashed.decode("utf-8")


async def verify_password_async(password: str, password_hash: str) -> bool:
    """Verify password against hash (async-wrapped)."""
    loop = asyncio.get_event_loop()
    pwd_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")
    return await loop.run_in_executor(None, lambda: bcrypt.checkpw(pwd_bytes, hash_bytes))


async def create_token_set_async(
    user_id: int,
    tenant_id: str,
    role: str,
    teams: list[str] | None = None,
    home_tenant: str | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Create a JWT token set using penguin-aaa.

    Args:
        user_id: User ID
        tenant_id: Active tenant ID; empty selects the UNSCOPED_TENANT
            sentinel, since penguin-aaa rejects an empty tenant claim.
        role: User role
        teams: Team IDs the user belongs to; looked up when omitted.
        home_tenant: The user's "home" tenant (for tenant switching context).
        scopes: Resolved authorization scopes for the active tenant. Omitted
            means "no active tenant" and yields the unscoped bundle — a
            holder can enumerate their tenants and switch, nothing more.
            Scopes are resolved once, at issue time (security.md: authz
            decisions are made on `scope`, never on a role name), and never
            contain a descendant id list.

    Returns:
        Dict with access_token, id_token, refresh_token, expires_in
    """
    from .models import get_user_teams
    from .tenancy import UNSCOPED_SCOPES
    from .tenancy.authz import platform_scopes

    if teams is None:
        user_teams = await get_user_teams(user_id)
        teams = [str(t["id"]) for t in user_teams]

    tenant_scopes = list(scopes) if scopes is not None else list(UNSCOPED_SCOPES)

    # Platform authority (user administration, audit trail) rides on the
    # user row's role, not on tenant membership, so it is merged in here
    # rather than resolved per-tenant. This is the single choke point every
    # token in the service passes through — adding it anywhere else would
    # leave some issuance path minting tokens without it.
    resolved_scopes = sorted(set(tenant_scopes) | set(platform_scopes(role)))

    oidc = get_oidc_provider()
    now = datetime.now(UTC)
    ttl: timedelta = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(hours=1))
    exp = now + ttl

    # Build extra claims dict
    ext_claims: dict[str, Any] = {}
    if home_tenant:
        ext_claims["home_tenant"] = home_tenant

    claims = Claims(
        sub=str(user_id),
        iss=current_app.config["JWT_ISSUER"],
        # aud is list[str] in penguin-aaa's Claims model — a bare string
        # fails validation before the token is ever signed.
        aud=list(current_app.config["JWT_AUDIENCES"]),
        iat=now,
        exp=exp,
        scope=resolved_scopes,
        roles=[role],
        tenant=tenant_id or UNSCOPED_TENANT,
        teams=teams,
        ext=ext_claims,
    )

    token_set = oidc.issue_token_set(claims)
    return {
        "access_token": token_set.access_token,
        "id_token": token_set.id_token,
        "refresh_token": token_set.refresh_token,
        "token_type": token_set.token_type,
        "expires_in": token_set.expires_in,
    }


def hash_refresh_token(token: str) -> str:
    """Hash an opaque refresh token for storage.

    penguin-aaa's refresh tokens are opaque random strings, not JWTs, so
    the only way to recognise one later is by digest. Only the digest is
    persisted — a database read cannot recover a usable token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_and_store_token_set(
    user_id: int,
    tenant_id: str,
    role: str,
    teams: list[str] | None = None,
) -> dict[str, Any]:
    """Issue a token set and persist its refresh token's hash.

    Issuance alone is not enough: /auth/refresh, /auth/logout and
    /auth/sessions all read the refresh_tokens table, so a token set that
    is never stored is unusable for refresh and invisible to session
    listing and revocation.
    """
    token_set = await create_token_set_async(user_id, tenant_id, role, teams)

    refresh_ttl: timedelta = current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES", timedelta(days=7))
    await store_refresh_token(
        user_id=user_id,
        token_hash=hash_refresh_token(token_set["refresh_token"]),
        expires_at=datetime.now(UTC) + refresh_ttl,
    )
    return token_set


@auth_bp.route("/login", methods=["POST"])
async def login() -> tuple[dict[str, Any], int]:
    """Login endpoint - returns access and refresh tokens."""
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    totp_code = data.get("mfa_code", "")

    if not email or not password:
        return {"error": "Email and password required"}, 400

    # Find user
    user = await get_user_by_email(email)
    if not user:
        return {"error": "Invalid email or password"}, 401

    # Verify password
    pwd_valid = await verify_password_async(password, user["password_hash"])
    if not pwd_valid:
        return {"error": "Invalid email or password"}, 401

    # Check if user is active
    if not user.get("is_active"):
        return {"error": "Account is deactivated"}, 401

    # Check MFA requirement
    mfa_enabled = await is_mfa_enabled(user["id"])
    if mfa_enabled:
        if not totp_code:
            return {"error": "MFA code required", "mfa_required": True}, 401

        # Verify TOTP code
        mfa = await get_mfa_secret(user["id"])
        if not mfa:
            return {"error": "MFA configuration error"}, 500

        totp = pyotp.TOTP(mfa["secret"])
        if not totp.verify(totp_code, valid_window=1):
            return {"error": "Invalid MFA code"}, 401

    # Generate tokens using penguin-aaa and record the refresh token so it
    # can later be rotated, listed as a session, and revoked on logout.
    token_set = await issue_and_store_token_set(
        user["id"],
        tenant_id="",  # TODO: get from user's current tenant
        role=user["role"],
    )

    return (
        {
            "access_token": token_set["access_token"],
            "refresh_token": token_set["refresh_token"],
            "token_type": "Bearer",
            "expires_in": token_set["expires_in"],
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user["role"],
            },
        },
        200,
    )


#: Single response for every refresh failure — unknown, revoked, expired,
#: or belonging to a deactivated user. Distinguishing them would tell an
#: attacker holding a stolen token which of those states it is in.
_REFRESH_REJECTED = "Invalid or expired refresh token"


@auth_bp.route("/refresh", methods=["POST"])
async def refresh() -> tuple[dict[str, Any], int]:
    """Exchange a refresh token for a new token pair, rotating the old one.

    Rotation is one-use: the presented token is revoked before its
    replacement is issued, so replaying it afterwards fails even if
    issuance errors partway through.
    """
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    refresh_token = data.get("refresh_token", "")

    if not refresh_token:
        return {"error": "Refresh token required"}, 400

    token_hash = hash_refresh_token(refresh_token)

    # Identify the presenting user, then authorise separately: the lookup
    # deliberately matches revoked/expired rows so a replay is a rejection
    # rather than an indistinguishable "unknown token".
    record = await get_refresh_token_by_hash(token_hash)
    if not record:
        return {"error": _REFRESH_REJECTED}, 401

    user_id = int(record["user_id"])
    if not await is_refresh_token_valid(user_id, token_hash):
        return {"error": _REFRESH_REJECTED}, 401

    user = await get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        return {"error": _REFRESH_REJECTED}, 401

    # Revoke before issuing: a failure after this point costs the client a
    # re-login, whereas revoking afterwards would leave the presented token
    # replayable if issuance raised.
    await revoke_refresh_token(token_hash)

    token_set = await issue_and_store_token_set(
        user_id,
        # Refresh re-issues an unscoped token, exactly as login does; tenant
        # selection is a separate step (see the tenant switch endpoint).
        tenant_id="",
        role=user["role"],
    )

    return (
        {
            "access_token": token_set["access_token"],
            "refresh_token": token_set["refresh_token"],
            "token_type": "Bearer",
            "expires_in": token_set["expires_in"],
        },
        200,
    )


@auth_bp.route("/logout", methods=["POST"])
@auth_required
async def logout() -> tuple[dict[str, Any], int]:
    """Logout endpoint - revokes all refresh tokens for user."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    # Revoke all user's refresh tokens
    revoked_count = await revoke_all_user_tokens(user["id"])

    return (
        {
            "message": "Successfully logged out",
            "tokens_revoked": revoked_count,
        },
        200,
    )


@auth_bp.route("/me", methods=["GET"])
@auth_required
async def get_me() -> tuple[dict[str, Any], int]:
    """Get current user profile."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    return (
        {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name", ""),
            "role": user["role"],
            "is_active": user["is_active"],
            "created_at": (user["created_at"].isoformat() if user.get("created_at") else None),
        },
        200,
    )


@auth_bp.route("/register", methods=["POST"])
async def register() -> tuple[dict[str, Any], int]:
    """Register new user (creates viewer role by default + personal team)."""
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()

    # Validation
    if not email:
        return {"error": "Email is required"}, 400

    if not password or len(password) < 8:
        msg = "Password must be at least 8 characters"
        return {"error": msg}, 400

    # Check if user exists
    existing = await get_user_by_email(email)
    if existing:
        return {"error": "Email already registered"}, 409

    # Development mode caps the identity table at one user. Checked here
    # rather than only at the model layer so the second registrant gets a
    # reason they can act on instead of a generic failure.
    refusal = await devmode.user_creation_refusal()
    if refusal is not None:
        return refusal

    # Create user
    password_hash = await hash_password_async(password)
    user = await create_user(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role="viewer",
    )
    if not user:
        return {"error": "Failed to create user"}, 500

    # Create personal team — METERED. This was the second entrance to the
    # `teams` wall: self-service registration created a team through the
    # model layer with no quota check, so a Free deployment limited to one
    # team acquired another on every signup, indefinitely.
    #
    # The over-limit action refused is the TEAM, not the registration.
    # Non-admin members are unlimited at every tier by design, so refusing
    # the signup would convert a team wall into a user cap the tier model
    # deliberately does not have. The refusal is reported in the response
    # rather than swallowed, so the client can show the upgrade prompt
    # instead of silently wondering where the team went.
    from .models import create_team

    team_refusal = await quotas.quota_refusal("teams", await quotas.count_teams())

    if team_refusal is not None:
        # A bare "you already have 1 of 1 teams" is baffling to someone who
        # has never created one — the team that consumed the limit was
        # created FOR them, by this same endpoint, possibly for a different
        # account. Say so, or the operator reads the refusal as a bug.
        # Keys are unchanged (see quotas.scale_refusal_body); only the
        # message is given the missing half of the explanation.
        body = dict(team_refusal[0])
        body["message"] = (
            "Your account was created, but its personal team was not: every "
            "account is given a personal team, and each one counts toward "
            "the licensed team limit. " + str(body["message"])
        )
        team_refusal = (body, team_refusal[1])

    personal_team: dict[str, Any] | None = None
    if team_refusal is None:
        user_name = full_name or email.split("@")[0]
        team_slug = email.split("@")[0].lower().replace(".", "-")
        personal_team = await create_team(
            name=f"{user_name}'s Team",
            slug=team_slug,
            owner_id=user["id"],
        )

    personal_team_info: dict[str, Any] | None = None
    if personal_team:
        personal_team_info = {
            "id": personal_team["id"],
            "name": personal_team["name"],
            "slug": personal_team["slug"],
        }

    return (
        {
            "message": "Registration successful",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user["role"],
            },
            "personal_team": personal_team_info,
            # Present only when the team was refused, carrying the same
            # quota body every other wall answers with.
            "personal_team_refused": (team_refusal[0] if team_refusal is not None else None),
        },
        201,
    )


async def _deliver_password_reset_token(user_id: int, token: str, expires_at: datetime) -> None:
    """Deliver a reset token to the user out of band.

    No SMTP transport is configured in this service, so delivery cannot
    happen yet; the token is still created and persisted, so a reset link
    issued by any future transport (or by an operator reading the table
    directly) keeps working. The undeliverable request is recorded at WARN
    so the gap is visible in logs rather than silently swallowed.

    The token value and the user's email address are deliberately absent
    from the log record — only the internal user id identifies the subject.
    Logging either would reintroduce, in the log sink, exactly the leak this
    endpoint was fixed to close.
    """
    log.warning(
        "password_reset_token_undeliverable",
        extra={
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
            "reason": "no SMTP transport configured for this service",
        },
    )


@auth_bp.route("/forgot-password", methods=["POST"])
async def forgot_password() -> tuple[dict[str, Any], int]:
    """Request a password reset link.

    Unauthenticated. Always answers with :data:`PASSWORD_RESET_ACK` and 200,
    whether or not the address is registered, and never returns the reset
    token itself.

    Both properties are load-bearing security controls, not cosmetics:
    returning the token handed any anonymous caller a full account takeover
    for any address they could name, and returning a distinct message for
    the not-found case made the endpoint a user-enumeration oracle. Any
    change here that reintroduces a branch-dependent body reintroduces one
    of those two bugs.
    """
    data = await request.get_json()
    if not data or not data.get("email"):
        return {"error": "Email required"}, 400

    email = data.get("email", "").strip().lower()
    user = await get_user_by_email(email)
    if user:
        from .auth_features import create_password_reset_token

        token, expires_at = await create_password_reset_token(user["id"])
        await _deliver_password_reset_token(user["id"], token, expires_at)

    return dict(PASSWORD_RESET_ACK), 200


@auth_bp.route("/reset-password", methods=["POST"])
async def reset_password() -> tuple[dict[str, Any], int]:
    """Reset password with token."""
    data = await request.get_json()
    if not data or not data.get("token") or not data.get("password"):
        return {"error": "Token and password required"}, 400

    from .auth_features import mark_token_used, validate_password_reset_token

    user_id = await validate_password_reset_token(data["token"])
    if not user_id:
        return {"error": "Invalid or expired token"}, 401

    password = data.get("password", "")
    if len(password) < 8:
        return {"error": "Password must be 8+ characters"}, 400

    from .models import update_user

    password_hash = await hash_password_async(password)
    await update_user(user_id, password_hash=password_hash)
    await mark_token_used(data["token"])
    return {"message": "Password reset successful"}, 200


@auth_bp.route("/confirm-email/<token>", methods=["POST"])
async def confirm_email_endpoint(token: str) -> tuple[dict[str, Any], int]:
    """Confirm a user's email address with a confirmation token.

    Both helpers are async coroutines; awaiting them directly (rather than
    scheduling them on an executor, which would just hand back an
    un-awaited coroutine object) is what actually runs the DB work.
    """
    from .auth_features import confirm_email, validate_email_token

    user_id = await validate_email_token(token)
    if not user_id:
        return {"error": "Invalid or expired token"}, 401

    await confirm_email(token)
    return {"message": "Email confirmed"}, 200


@auth_bp.route("/sessions", methods=["GET"])
@auth_required
async def list_sessions() -> tuple[dict[str, Any], int]:
    """List active sessions for the authenticated user."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    from .auth_features import get_user_sessions

    sessions = await get_user_sessions(user["id"])
    return {"sessions": sessions}, 200


@auth_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@auth_required
async def revoke_session_endpoint(session_id: int) -> tuple[dict[str, Any], int]:
    """Revoke one of the authenticated user's sessions."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    from .auth_features import revoke_session

    revoked = await revoke_session(session_id, user["id"])
    if revoked:
        return {"message": "Session revoked"}, 200
    return {"error": "Session not found"}, 404
