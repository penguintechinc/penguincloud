"""Authentication and Authorization Middleware (async Quart)."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import jwt as pyjwt
from jwt import PyJWK
from quart import Quart, Response, current_app, g, request

from .config import UNSCOPED_TENANT
from .killkrill import killkrill_manager
from .models import get_user_by_id

log = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

#: Value penguin-aaa stamps into the `token_use` claim of an access token
#: (see penguin_aaa.authn.oidc_provider.issue_token_set). Id tokens carry
#: "id" and are otherwise byte-for-byte comparable — same issuer, same
#: audience, same signing key — so this claim is the only thing separating
#: "may call a protected route" from "describes a user".
TOKEN_USE_ACCESS = "access"

# Decorators below either call through to the wrapped async view or
# short-circuit with an (error_body, status) tuple, so the wrapper's return
# type widens to Any rather than staying the view's own R.


def get_token_from_header() -> str | None:
    """Extract JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def get_current_user() -> dict[str, Any] | None:
    """Get current authenticated user from request context."""
    user: dict[str, Any] | None = g.get("current_user", None)
    return user


def get_current_tenant_id() -> str | None:
    """Return the active tenant ID, or None when the token is unscoped.

    The UNSCOPED_TENANT sentinel satisfies penguin-aaa's mandatory,
    non-empty tenant claim but does not name a real tenant, so it is
    normalised back to None here — tenant-gated routes must still reject it.
    """
    tenant_id: str | None = g.get("current_tenant_id", None)
    if tenant_id and tenant_id != UNSCOPED_TENANT:
        return tenant_id
    claims: dict[str, Any] | None = g.get("current_claims", None)
    if claims:
        claim_tenant = claims.get("tenant")
        if claim_tenant and claim_tenant != UNSCOPED_TENANT:
            return str(claim_tenant)
    return None


def tenant_required(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Require an active (non-sentinel) tenant on the request's token."""

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            return (
                {"error": "No active tenant. Switch to a tenant first."},
                400,
            )
        g.current_tenant_id = tenant_id
        return await f(*args, **kwargs)

    return decorated


def require_feature(
    feature_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Any]]]:
    """Build a decorator requiring a specific license-gated feature."""

    def decorator(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[Any]]:
        @wraps(f)
        async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
            tenant_id = get_current_tenant_id()
            if not tenant_id:
                return {"error": "Tenant context required"}, 400

            # TODO(phase-1b): resolve per-tenant entitlements through
            # penguin-dal (tenant_product_features) and grant when the
            # tenant holds `feature_name`.
            #
            # Until that lookup exists there is no way to establish that
            # the tenant is entitled, so this DENIES. A gate that cannot
            # check anything must not grant: an unverifiable entitlement is
            # exactly the case flags are required to default OFF for. The
            # previous body fell through to the view, making the decorator
            # documentation rather than enforcement.
            log.warning(
                "feature_gate_denied_unresolvable",
                extra={"feature": feature_name, "tenant": tenant_id},
            )
            return (
                {
                    "error": "feature_not_entitled",
                    "message": (f"Feature '{feature_name}' is not enabled for this tenant"),
                },
                403,
            )

        return decorated

    return decorator


def auth_required(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Require a valid, signature-verified JWT on the request."""

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        token = get_token_from_header()

        if not token:
            return {"error": "Missing authorization token"}, 401

        try:
            from .auth import get_oidc_provider

            oidc = get_oidc_provider()

            # Get token header (kid) to find correct signing key
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")

            # Public JWKS off the provider — no reaching into private
            # _keystore/_config attributes.
            jwks: dict[str, Any] = oidc.jwks()

            if not jwks.get("keys"):
                return {"error": "Auth system not initialized"}, 500

            # Find the public key by kid
            public_key_data = None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    # from_dict, not from_json — get_jwks() hands back parsed
                    # dicts, and from_json expects a raw JSON string.
                    jwk = PyJWK.from_dict(key_data)
                    public_key_data = jwk.key
                    break

            if not public_key_data:
                return {"error": "Invalid token - key not found"}, 401

            # Verify signature + claims with explicit algorithm allowlist
            payload: dict[str, Any] = pyjwt.decode(
                token,
                public_key_data,
                algorithms=["RS256", "ES256", "ES384", "ES512"],
                issuer=current_app.config["JWT_ISSUER"],
                audience=list(current_app.config["JWT_AUDIENCES"]),
            )

            # Only an ACCESS token authenticates a protected route.
            # penguin-aaa's issue_token_set mints the access and id tokens
            # from one base payload, with the same iss, aud and signing key
            # — the sole discriminator is `token_use`. Without this check an
            # id token (handed to clients for profile display, and routinely
            # passed around more freely) is accepted everywhere an access
            # token is. Refresh tokens are opaque strings, so they fail
            # earlier at header parsing, but are named here for the reader.
            if payload.get("token_use") != TOKEN_USE_ACCESS:
                return {"error": "Invalid token type - access token required"}, 401

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
        except pyjwt.InvalidTokenError:
            # Detail stays server-side: the reason a token failed
            # verification (bad signature vs wrong audience vs malformed)
            # is a probing oracle for an unauthenticated caller.
            log.info("token_verification_failed", exc_info=True)
            return {"error": "Invalid token"}, 401
        except Exception:
            # Anything else is a server fault, not a client one. The
            # previous message echoed raw exception text — which also
            # mislabelled genuine 500s raised inside the wrapped view as
            # "Authentication error", hiding real bugs behind an auth
            # message.
            log.exception("authentication_error")
            return {"error": "Authentication error"}, 500

    return decorated


# `role_required`, `admin_required` and `maintainer_or_admin_required` were
# removed here. They compared `user["role"]` against a name list, which
# security.md forbids ("authorization decisions on scope, never role
# names") and which this phase eliminated everywhere else. Their last two
# callers — license_api.get_license_status and hello.hello_protected — now
# use `@require_scope(SCOPE_LICENSE_READ)` and
# `@require_scope(SCOPE_PLATFORM_READ)`, each admitting exactly the callers
# the decorator did. Leaving the decorators behind as unused helpers would
# leave the next author a working, forbidden shortcut.


def _coerce_team_id(raw: Any) -> int | None:
    """Narrow a route kwarg to an int team id, or None when unusable.

    Route kwargs arrive as `object` under ParamSpec, so the team decorators
    below need an explicit narrowing step before passing the value to
    get_user_team_role(user_id: int, team_id: int).
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def team_member_required(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Require team membership; expects team_id in the view's kwargs."""

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = _coerce_team_id(kwargs.get("team_id"))
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role

        role = await model_get_role(user["id"], team_id)
        if not role:
            return {"error": "Not a member of this team"}, 403

        return await f(*args, **kwargs)

    return decorated


def team_admin_required(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Require team admin/owner role; expects team_id in the view's kwargs."""

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = _coerce_team_id(kwargs.get("team_id"))
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role

        role = await model_get_role(user["id"], team_id)
        if role not in ["owner", "admin"]:
            return {"error": "Team admin access required"}, 403

        return await f(*args, **kwargs)

    return decorated


def team_owner_required(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Require team ownership; expects team_id in the view's kwargs."""

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        user = get_current_user()
        if not user:
            return {"error": "Authentication required"}, 401

        team_id = _coerce_team_id(kwargs.get("team_id"))
        if not team_id:
            return {"error": "Team ID required"}, 400

        from .models import get_user_team_role as model_get_role

        role = await model_get_role(user["id"], team_id)
        if role != "owner":
            return {"error": "Team owner access required"}, 403

        return await f(*args, **kwargs)

    return decorated


def setup_request_logging(app: Quart) -> None:
    """Attach structured request/response logging hooks to the Quart app."""

    @app.before_request
    async def before_request() -> None:
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.start_time = time.time()
        g.user_id = None
        g.team_id = None
        # TODO: Extract user and tenant from JWT claims

    @app.after_request
    async def after_request(response: Response) -> Response:
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
