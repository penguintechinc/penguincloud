"""Authentication and Authorization Middleware."""

import time
import uuid
from functools import wraps
from typing import Callable, Optional

import jwt
from flask import current_app, g, jsonify, request

from .killkrill import killkrill_manager
from .models import get_user_by_id


def get_token_from_header() -> Optional[str]:
    """Extract JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user() -> Optional[dict]:
    """Get current authenticated user from request context."""
    return getattr(g, "current_user", None)


def get_current_tenant_id() -> Optional[int]:
    """Get current tenant ID from JWT claims or request context."""
    tenant_id = getattr(g, "current_tenant_id", None)
    if tenant_id:
        return tenant_id
    token = get_token_from_header()
    if token:
        payload = decode_token(token)
        if payload:
            return payload.get("current_tenant_id")
    return None


def tenant_required(f: Callable) -> Callable:
    """Decorator to require an active tenant context."""

    @wraps(f)
    def decorated(*args, **kwargs):
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            return jsonify({"error": "No active tenant. Switch to a tenant first."}), 400
        g.current_tenant_id = tenant_id
        return f(*args, **kwargs)

    return decorated


def require_feature(feature_name: str) -> Callable:
    """Decorator to require a specific license-gated feature."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            tenant_id = get_current_tenant_id()
            if not tenant_id:
                return jsonify({"error": "Tenant context required"}), 400

            from .models import get_db
            db = get_db()
            feature = db(
                (db.tenant_product_features.tenant_id == tenant_id)
                & (db.tenant_product_features.feature_name == feature_name)
                & (db.tenant_product_features.enabled == True)
            ).select().first()

            if not feature:
                return jsonify({
                    "error": f"Feature '{feature_name}' not available",
                    "upgrade_required": True,
                }), 403

            return f(*args, **kwargs)

        return decorated

    return decorator


def auth_required(f: Callable) -> Callable:
    """Decorator to require authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_header()

        if not token:
            return jsonify({"error": "Missing authorization token"}), 401

        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Check token type
        if payload.get("type") != "access":
            return jsonify({"error": "Invalid token type"}), 401

        # Get user from database
        user_id = payload.get("sub")
        if not user_id:
            return jsonify({"error": "Invalid token payload"}), 401

        user = get_user_by_id(int(user_id))
        if not user:
            return jsonify({"error": "User not found"}), 401

        if not user.get("is_active"):
            return jsonify({"error": "User account is deactivated"}), 401

        # Store user in request context
        g.current_user = user

        return f(*args, **kwargs)

    return decorated


def role_required(*allowed_roles: str) -> Callable:
    """Decorator to require specific roles."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({"error": "Authentication required"}), 401

            user_role = user.get("role", "")
            if user_role not in allowed_roles:
                return (
                    jsonify(
                        {
                            "error": "Insufficient permissions",
                            "required_roles": list(allowed_roles),
                            "your_role": user_role,
                        }
                    ),
                    403,
                )

            return f(*args, **kwargs)

        return decorated

    return decorator


def admin_required(f: Callable) -> Callable:
    """Decorator to require admin role."""
    return role_required("admin")(f)


def maintainer_or_admin_required(f: Callable) -> Callable:
    """Decorator to require maintainer or admin role."""
    return role_required("admin", "maintainer")(f)


def team_member_required(f: Callable) -> Callable:
    """Decorator to check team membership. Expects team_id in kwargs."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return jsonify({"error": "Team ID required"}), 400

        role = get_user_team_role(user["id"], team_id)
        if not role:
            return jsonify({"error": "Not a member of this team"}), 403

        return f(*args, **kwargs)

    return decorated


def team_admin_required(f: Callable) -> Callable:
    """Decorator to check team admin role. Expects team_id in kwargs."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return jsonify({"error": "Team ID required"}), 400

        role = get_user_team_role(user["id"], team_id)
        if role not in ["owner", "admin"]:
            return jsonify({"error": "Team admin access required"}), 403

        return f(*args, **kwargs)

    return decorated


def team_owner_required(f: Callable) -> Callable:
    """Decorator to check team ownership. Expects team_id in kwargs."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return jsonify({"error": "Team ID required"}), 400

        role = get_user_team_role(user["id"], team_id)
        if role != "owner":
            return jsonify({"error": "Team owner access required"}), 403

        return f(*args, **kwargs)

    return decorated


def get_user_team_role(user_id: int, team_id: int) -> Optional[str]:
    """Get user's role in a team."""
    from .models import get_user_team_role as model_get_role

    return model_get_role(user_id, team_id)


def setup_request_logging(app):
    """Setup structured logging middleware for all requests."""

    @app.before_request
    def before_request():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.start_time = time.time()
        g.user_id = None
        g.team_id = None

        # Try to extract user and tenant from token
        token = get_token_from_header()
        if token:
            payload = decode_token(token)
            if payload:
                g.user_id = payload.get("sub")
                g.team_id = payload.get("current_team_id")
                g.current_tenant_id = payload.get("current_tenant_id")

    @app.after_request
    def after_request(response):
        # Log request in ECS format
        duration_ms = (time.time() - g.start_time) * 1000
        killkrill_manager.log(
            "info",
            f"{request.method} {request.path}",
            http={
                "method": request.method,
                "status_code": response.status_code,
            },
            url={"path": request.path},
            event={"duration": int(duration_ms)},
            user={"id": str(g.user_id)} if g.user_id else None,
            team={"id": str(g.team_id)} if g.team_id else None,
            request_id=g.request_id,
        )

        # Track API request metric
        from .killkrill import track_api_request

        track_api_request(
            request.path, request.method, response.status_code, duration_ms
        )

        return response
