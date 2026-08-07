"""Authentication and Authorization Middleware (async Quart)."""

import time
import uuid
from functools import wraps
from typing import Any, Callable, Optional

from quart import current_app, g, request

from .killkrill import killkrill_manager
from .models import get_user_by_id


def get_token_from_header() -> Optional[str]:
    """Extract JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def get_current_user() -> Optional[dict[str, Any]]:
    """Get current authenticated user from request context."""
    return g.get("current_user", None)


def get_current_tenant_id() -> Optional[str]:
    """Get current tenant ID from JWT claims or request context."""
    tenant_id = g.get("current_tenant_id", None)
    if tenant_id:
        return tenant_id
    claims = g.get("current_claims", None)
    if claims:
        return claims.get("tenant")
    return None


def tenant_required(f: Callable) -> Callable:
    """Decorator to require an active tenant context."""

    @wraps(f)
    async def decorated(*args: Any, **kwargs: Any) -> Any:
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            return (
                {"error": "No active tenant. Switch to a tenant first."},
                400,
            )
        g.current_tenant_id = tenant_id
        return await f(*args, **kwargs)

    return decorated


def require_feature(feature_name: str) -> Callable:
    """Decorator to require a specific license-gated feature."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        async def decorated(*args: Any, **kwargs: Any) -> Any:
            tenant_id = get_current_tenant_id()
            if not tenant_id:
                return {"error": "Tenant context required"}, 400

            # TODO: Implement feature checking with penguin-dal
            # For now, allow all features
            return await f(*args, **kwargs)

        return decorated

    return decorator


def auth_required(f: Callable) -> Callable:
    """Decorator to require authentication (validates JWT token signature)."""

    @wraps(f)
    async def decorated(*args: Any, **kwargs: Any) -> Any:
        token = get_token_from_header()

        if not token:
            return {"error": "Missing authorization token"}, 401

        try:
            import jwt as pyjwt
            from jwt import PyJWK

            # Get OIDC provider from app context
            oidc = current_app.extensions.get("oidc_provider")
            if not oidc:
                return {"error": "Auth not configured"}, 500

            # Get token header (kid) to find correct signing key
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")

            # Get JWKS from OIDCProvider's keystore
            config = oidc._config
            keystore = oidc._keystore
            jwks = keystore.get_jwks()

            if not jwks.get("keys"):
                return {"error": "Auth system not initialized"}, 500

            # Find the public key by kid
            public_key_data = None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    jwk = PyJWK.from_json(key_data)
                    public_key_data = jwk.key
                    break

            if not public_key_data:
                return {"error": "Invalid token - key not found"}, 401

            # Verify signature + claims with explicit algorithm allowlist
            payload = pyjwt.decode(
                token,
                public_key_data,
                algorithms=["RS256", "ES256", "ES384", "ES512"],
                issuer=config.issuer,
                audience=config.audiences,
            )

            # Validate required claims
            user_id = payload.get("sub")
            if not user_id:
                return {"error": "Invalid token payload - missing sub"}, 401

            tenant_id = payload.get("tenant")
            if not tenant_id:
                return {"error": "Invalid token payload - missing tenant"}, 401

            # Get user from database
            user = await get_user_by_id(int(user_id))
            if not user:
                return {"error": "User not found"}, 401

            if not user.get("is_active"):
                return {"error": "User account is deactivated"}, 401

            # Store user and claims in request context
            g.current_user = user
            g.current_claims = payload

            return await f(*args, **kwargs)

        except pyjwt.ExpiredSignatureError:
            return {"error": "Token has expired"}, 401
        except pyjwt.InvalidTokenError as e:
            return {"error": f"Invalid token: {str(e)}"}, 401
        except Exception as e:
            return {"error": f"Authentication error: {str(e)}"}, 500

    return decorated


def role_required(*allowed_roles: str) -> Callable:
    """Decorator to require specific roles."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        async def decorated(*args: Any, **kwargs: Any) -> Any:
            user = get_current_user()

            if not user:
                return {"error": "Authentication required"}, 401

            user_role = user.get("role", "")
            if user_role not in allowed_roles:
                return (
                    {
                        "error": "Insufficient permissions",
                        "required_roles": list(allowed_roles),
                        "your_role": user_role,
                    },
                    403,
                )

            return await f(*args, **kwargs)

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
    async def decorated(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role
        role = await model_get_role(user["id"], team_id)
        if not role:
            return {"error": "Not a member of this team"}, 403

        return await f(*args, **kwargs)

    return decorated


def team_admin_required(f: Callable) -> Callable:
    """Decorator to check team admin role. Expects team_id in kwargs."""

    @wraps(f)
    async def decorated(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role
        role = await model_get_role(user["id"], team_id)
        if role not in ["owner", "admin"]:
            return {"error": "Team admin access required"}, 403

        return await f(*args, **kwargs)

    return decorated


def team_owner_required(f: Callable) -> Callable:
    """Decorator to check team ownership. Expects team_id in kwargs."""

    @wraps(f)
    async def decorated(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = kwargs.get("team_id")
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role
        role = await model_get_role(user["id"], team_id)
        if role != "owner":
            return {"error": "Team owner access required"}, 403

        return await f(*args, **kwargs)

    return decorated


def setup_request_logging(app: Any) -> None:
    """Setup structured logging middleware for all requests (Quart)."""

    @app.before_request
    async def before_request() -> None:
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.start_time = time.time()
        g.user_id = None
        g.team_id = None
        # TODO: Extract user and tenant from JWT claims

    @app.after_request
    async def after_request(response: Any) -> Any:
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
        return response
