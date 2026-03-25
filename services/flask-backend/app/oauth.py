"""OAuth2/SSO Integration Endpoints."""

import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session

from .auth import create_access_token, create_refresh_token
from .config import Config
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


def require_feature(feature_name: str):
    """Decorator to gate features behind license checks."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # In development mode, skip feature gating
            if not Config.RELEASE_MODE:
                return f(*args, **kwargs)

            # Check if feature is enabled (would integrate with license server)
            # For now, always allow in non-release mode
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_state_token() -> str:
    """Generate secure CSRF state token."""
    return secrets.token_urlsafe(32)


def validate_state_token(state: str) -> bool:
    """Validate CSRF state token from session."""
    if "oauth_state" not in session:
        return False
    return secrets.compare_digest(session.pop("oauth_state"), state)


def get_provider_config(provider: str) -> Optional[dict]:
    """Get provider configuration."""
    if provider not in Config.OAUTH_PROVIDERS:
        return None
    config = Config.OAUTH_PROVIDERS[provider].copy()

    # Handle Okta tenant URL substitution
    if provider == "okta" and config.get("tenant_url"):
        tenant_url = config["tenant_url"]
        config["authorization_url"] = config["authorization_url"].format(
            tenant_url=tenant_url
        )
        config["token_url"] = config["token_url"].format(tenant_url=tenant_url)
        config["userinfo_url"] = config["userinfo_url"].format(tenant_url=tenant_url)

    return config


def get_redirect_uri(provider: str) -> str:
    """Get OAuth2 redirect URI."""
    return request.url_root.rstrip("/") + f"/api/v1/auth/oauth/{provider}/callback"


@oauth_bp.route("/auth/oauth/<provider>", methods=["GET"])
@require_feature("sso_integration")
def oauth_redirect(provider: str):
    """Redirect to OAuth provider for authorization."""
    config = get_provider_config(provider)
    if not config:
        return jsonify({"error": "OAuth provider not configured"}), 400

    if not config.get("client_id") or not config.get("client_secret"):
        return jsonify({"error": "Provider credentials not configured"}), 500

    state = get_state_token()
    session["oauth_state"] = state

    # Build authorization URL
    auth_params = {
        "client_id": config["client_id"],
        "redirect_uri": get_redirect_uri(provider),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }

    auth_url = config["authorization_url"] + "?" + urlencode(auth_params)
    return redirect(auth_url)


@oauth_bp.route("/auth/oauth/<provider>/callback", methods=["GET"])
@require_feature("sso_integration")
def oauth_callback(provider: str):
    """Handle OAuth2 callback and create/link user account."""
    config = get_provider_config(provider)
    if not config:
        return jsonify({"error": "OAuth provider not configured"}), 400

    # Validate state token
    state = request.args.get("state")
    if not state or not validate_state_token(state):
        return jsonify({"error": "Invalid state parameter"}), 401

    # Check for authorization errors
    error = request.args.get("error")
    if error:
        return jsonify({"error": f"Authorization failed: {error}"}), 401

    # Get authorization code
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "No authorization code received"}), 400

    try:
        # Exchange code for tokens
        token_data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": get_redirect_uri(provider),
            "grant_type": "authorization_code",
        }

        token_response = requests.post(
            config["token_url"],
            data=token_data,
            timeout=10,
        )
        token_response.raise_for_status()
        tokens = token_response.json()

        # Get user info from provider
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        userinfo_response = requests.get(
            config["userinfo_url"],
            headers=headers,
            timeout=10,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

        # Extract user info (provider-specific)
        provider_user_id = _extract_provider_user_id(provider, userinfo)
        email = _extract_provider_email(provider, userinfo)
        full_name = _extract_provider_name(provider, userinfo)

        if not provider_user_id or not email:
            return jsonify({"error": "Failed to get user info from provider"}), 400

        # Check if OAuth connection exists
        existing_connection = get_oauth_connection_by_provider_id(
            provider, provider_user_id
        )

        if existing_connection:
            # Link to existing user
            user_id = existing_connection["user_id"]
            user = get_user_by_id(user_id)
        else:
            # Check if user with email exists
            user = get_user_by_email(email)

            if not user:
                # Create new user with OAuth
                import bcrypt

                # Generate random password for OAuth users
                random_password = secrets.token_urlsafe(32)
                password_hash = bcrypt.hashpw(
                    random_password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")

                user = create_user(
                    email=email,
                    password_hash=password_hash,
                    full_name=full_name,
                    role="viewer",
                )
                user_id = user["id"]
            else:
                user_id = user["id"]

        # Store/update OAuth connection
        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.utcnow() + timedelta(seconds=tokens["expires_in"])

        store_oauth_connection(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
        )

        # Generate JWT tokens
        access_token = create_access_token(user_id, user["role"])
        refresh_token, refresh_expires = create_refresh_token(user_id)

        # Return tokens (would redirect to frontend in production)
        return (
            jsonify(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer",
                    "user": {
                        "id": user["id"],
                        "email": user["email"],
                        "full_name": user["full_name"],
                        "role": user["role"],
                    },
                }
            ),
            200,
        )

    except requests.RequestException as e:
        current_app.logger.error(f"OAuth callback error: {e}")
        return jsonify({"error": "Failed to complete OAuth flow"}), 500


def _extract_provider_user_id(provider: str, userinfo: dict) -> Optional[str]:
    """Extract provider-specific user ID."""
    if provider == "google":
        return userinfo.get("sub")
    elif provider == "microsoft":
        return userinfo.get("id")
    elif provider == "okta":
        return userinfo.get("sub")
    return None


def _extract_provider_email(provider: str, userinfo: dict) -> Optional[str]:
    """Extract provider-specific email."""
    if provider == "google":
        return userinfo.get("email")
    elif provider == "microsoft":
        return userinfo.get("userPrincipalName") or userinfo.get("mail")
    elif provider == "okta":
        return userinfo.get("email")
    return None


def _extract_provider_name(provider: str, userinfo: dict) -> str:
    """Extract provider-specific full name."""
    if provider == "google":
        return userinfo.get("name", "")
    elif provider == "microsoft":
        return userinfo.get("displayName", "")
    elif provider == "okta":
        return userinfo.get("name", "")
    return ""


@oauth_bp.route("/auth/oauth/connections", methods=["GET"])
@auth_required
def get_oauth_connections():
    """Get OAuth connections for current user."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    connections = []
    for provider in Config.OAUTH_PROVIDERS.keys():
        connection = get_oauth_connection(user["id"], provider)
        if connection:
            # Don't expose tokens
            connection.pop("access_token", None)
            connection.pop("refresh_token", None)
            connections.append(connection)

    return jsonify({"connections": connections}), 200


@oauth_bp.route("/auth/oauth/<provider>/disconnect", methods=["POST"])
@auth_required
def disconnect_oauth(provider: str):
    """Disconnect OAuth connection for current user."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    connection = get_oauth_connection(user["id"], provider)
    if not connection:
        return jsonify({"error": "OAuth connection not found"}), 404

    # Delete connection (would use delete function, implementing inline for now)
    from .models import get_db

    db = get_db()
    db(db.oauth_connections.id == connection["id"]).delete()
    db.commit()

    return jsonify({"message": "OAuth connection disconnected"}), 200
