"""OAuth2/SSO Integration Endpoints (async Quart)."""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from quart import Blueprint, current_app, redirect, request, session

from . import devmode
from .auth import issue_and_store_token_set
from .config import Config

# The local stub this replaces returned the view unconditionally in BOTH
# branches — a gate that never gated. license.require_feature is the real
# entitlement check (LicenseManager.is_feature_enabled) and 403s when the
# tier does not include the feature. SSO is Professional+ per general.md.
#
# Redundant-looking alias is the explicit re-export form: it tells mypy
# (and the reader) that require_feature is deliberately part of this
# module's namespace, not an incidental import.
from .license import require_feature as require_feature
from .middleware import auth_required, get_current_user
from .models import (
    create_user,
    get_oauth_connection,
    get_oauth_connection_by_provider_id,
    get_user_by_email,
    get_user_by_id,
    store_oauth_connection,
)

oauth_bp = Blueprint("oauth", __name__)


def get_state_token() -> str:
    """Generate secure CSRF state token."""
    return secrets.token_urlsafe(32)


def validate_state_token(state: str) -> bool:
    """Validate and CONSUME the CSRF state token held in the session.

    Single-use by construction: the stored value is popped, so a replayed
    callback (an attacker re-sending a captured redirect) finds nothing to
    compare against and fails. Reusable state defeats the point of the
    parameter.

    Previously read the session via `session.get_json()`, which does not
    exist on Quart's session object — the hasattr guard fell through to an
    empty dict, so this returned False unconditionally and every OAuth
    callback 401'd regardless of the state presented.
    """
    stored = session.pop("oauth_state", None)
    if not stored or not state:
        return False
    return secrets.compare_digest(str(stored), state)


def get_provider_config(provider: str) -> dict[str, Any] | None:
    """Get provider configuration."""
    if provider not in Config.OAUTH_PROVIDERS:
        return None
    config: dict[str, Any] = Config.OAUTH_PROVIDERS[provider].copy()

    # Handle Okta tenant URL substitution
    if provider == "okta" and config.get("tenant_url"):
        tenant_url = config["tenant_url"]
        config["authorization_url"] = config["authorization_url"].format(tenant_url=tenant_url)
        config["token_url"] = config["token_url"].format(tenant_url=tenant_url)
        config["userinfo_url"] = config["userinfo_url"].format(tenant_url=tenant_url)

    return config


async def get_redirect_uri(provider: str) -> str:
    """Get OAuth2 redirect URI."""
    root = request.url_root.rstrip("/") if hasattr(request, "url_root") else "http://localhost:8000"
    return f"{root}/api/v1/auth/oauth/{provider}/callback"


@oauth_bp.route("/auth/oauth/<provider>", methods=["GET"])
@require_feature("sso_integration")
async def oauth_redirect(provider: str) -> Any:
    """Redirect to OAuth provider for authorization."""
    config = get_provider_config(provider)
    if not config:
        return {"error": "OAuth provider not configured"}, 400

    if not config.get("client_id") or not config.get("client_secret"):
        return {"error": "Provider credentials not configured"}, 500

    state = get_state_token()
    session["oauth_state"] = state

    # Build authorization URL
    redirect_uri = await get_redirect_uri(provider)
    auth_params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }

    auth_url = config["authorization_url"] + "?" + urlencode(auth_params)
    return redirect(auth_url)


@oauth_bp.route("/auth/oauth/<provider>/callback", methods=["GET"])
@require_feature("sso_integration")
async def oauth_callback(provider: str) -> tuple[dict[str, Any], int]:
    """Handle OAuth2 callback and create/link user account."""
    config = get_provider_config(provider)
    if not config:
        return {"error": "OAuth provider not configured"}, 400

    # Validate state token (consumes it — single use)
    state = request.args.get("state")
    if not state or not validate_state_token(state):
        return {"error": "Invalid state parameter"}, 401

    # Check for authorization errors
    error = request.args.get("error")
    if error:
        return {"error": f"Authorization failed: {error}"}, 401

    # Get authorization code
    code = request.args.get("code")
    if not code:
        return {"error": "No authorization code received"}, 400

    try:
        # Exchange code for tokens. Native async: the previous form ran
        # blocking `requests` calls through asyncio.to_thread, which works
        # but burns a worker thread per in-flight OAuth callback for the
        # entire round trip to the identity provider.
        token_data: dict[str, str] = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": await get_redirect_uri(provider),
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(config["token_url"], data=token_data)
            token_response.raise_for_status()
            tokens: dict[str, Any] = token_response.json()

            userinfo_response = await client.get(
                config["userinfo_url"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        # Extract user info (provider-specific)
        provider_user_id = _extract_provider_user_id(provider, userinfo)
        email = _extract_provider_email(provider, userinfo)
        full_name = _extract_provider_name(provider, userinfo)

        if not provider_user_id or not email:
            return {"error": "Failed to get user info from provider"}, 400

        # Check if OAuth connection exists
        existing_connection = await get_oauth_connection_by_provider_id(provider, provider_user_id)

        if existing_connection:
            # Link to existing user
            user_id = existing_connection["user_id"]
            user = await get_user_by_id(user_id)
        else:
            # Check if user with email exists
            user = await get_user_by_email(email)

            if not user:
                # Development mode caps the identity table at one user, and
                # SSO is a user-creation path like any other. Without this
                # the second SSO sign-in reached the model-layer backstop,
                # whose exception escapes the view as a 500 — the cap held,
                # but the operator was told "internal server error" instead
                # of what to do about it.
                refusal = await devmode.user_creation_refusal()
                if refusal is not None:
                    return refusal

                # Create new user with OAuth
                import bcrypt

                # Generate random password for OAuth users
                random_password = secrets.token_urlsafe(32)

                def _hash_password() -> str:
                    return bcrypt.hashpw(random_password.encode("utf-8"), bcrypt.gensalt()).decode(
                        "utf-8"
                    )

                password_hash = await asyncio.to_thread(_hash_password)

                user = await create_user(
                    email=email,
                    password_hash=password_hash,
                    full_name=full_name,
                    role="viewer",
                )
                user_id = user["id"] if user else None
            else:
                user_id = user["id"]

        if not user_id or not user:
            return {"error": "Failed to create or retrieve user"}, 500

        # Store/update OAuth connection
        expires_at: datetime | None = None
        if "expires_in" in tokens:
            expires_at = datetime.now(UTC) + timedelta(seconds=tokens["expires_in"])

        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token")
        await store_oauth_connection(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        # Generate JWT tokens using penguin-aaa. Stored, like a password
        # login, so an OAuth session is refreshable, listable and revocable.
        token_set = await issue_and_store_token_set(
            user_id=user_id,
            # OAuth users have no active tenant until they switch to one;
            # create_token_set_async maps "" onto the UNSCOPED_TENANT sentinel.
            tenant_id="",
            role=user["role"],
        )

        # Return tokens (would redirect to frontend in production)
        return (
            {
                "access_token": token_set.get("access_token"),
                "refresh_token": token_set.get("refresh_token"),
                "token_type": "Bearer",
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "full_name": user.get("full_name", ""),
                    "role": user["role"],
                },
            },
            200,
        )

    except httpx.HTTPError as e:
        current_app.logger.error(f"OAuth callback error: {e}")
        return {"error": "Failed to complete OAuth flow"}, 500


def _extract_provider_user_id(provider: str, userinfo: dict[str, Any]) -> str | None:
    """Extract provider-specific user ID."""
    if provider == "google":
        return userinfo.get("sub")
    elif provider == "microsoft":
        return userinfo.get("id")
    elif provider == "okta":
        return userinfo.get("sub")
    return None


def _extract_provider_email(provider: str, userinfo: dict[str, Any]) -> str | None:
    """Extract provider-specific email."""
    if provider == "google":
        return userinfo.get("email")
    elif provider == "microsoft":
        email = userinfo.get("userPrincipalName") or userinfo.get("mail")
        return email
    elif provider == "okta":
        return userinfo.get("email")
    return None


def _extract_provider_name(provider: str, userinfo: dict[str, Any]) -> str:
    """Extract provider-specific full name."""
    if provider == "google":
        name = userinfo.get("name", "")
        return str(name) if name else ""
    elif provider == "microsoft":
        name = userinfo.get("displayName", "")
        return str(name) if name else ""
    elif provider == "okta":
        name = userinfo.get("name", "")
        return str(name) if name else ""
    return ""


@oauth_bp.route("/auth/oauth/connections", methods=["GET"])
@auth_required
async def get_oauth_connections() -> tuple[dict[str, Any], int]:
    """Get OAuth connections for current user."""
    user = get_current_user()
    if not user:
        return {"error": "Unauthorized"}, 401

    connections = []
    for provider in Config.OAUTH_PROVIDERS.keys():
        connection = await get_oauth_connection(user["id"], provider)
        if connection:
            # Don't expose tokens
            connection.pop("access_token", None)
            connection.pop("refresh_token", None)
            connections.append(connection)

    return {"connections": connections}, 200


@oauth_bp.route("/auth/oauth/<provider>/disconnect", methods=["POST"])
@auth_required
async def disconnect_oauth(provider: str) -> tuple[dict[str, Any], int]:
    """Disconnect OAuth connection for current user."""
    user = get_current_user()
    if not user:
        return {"error": "Unauthorized"}, 401

    connection = await get_oauth_connection(user["id"], provider)
    if not connection:
        return {"error": "OAuth connection not found"}, 404

    # Delete connection
    from .models import get_db

    db = get_db()
    await db(db.oauth_connections.id == connection["id"]).delete()

    return {"message": "OAuth connection disconnected"}, 200
