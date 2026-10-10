"""Hello World Endpoint - Example authenticated endpoint (async Quart)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from quart import Blueprint, current_app
from quart_schema import validate_response

from .authz import SCOPE_PLATFORM_READ, require_scope
from .middleware import auth_required, get_current_user

hello_bp = Blueprint("hello", __name__)


@dataclass(slots=True, frozen=True)
class StatusResponse:
    """Envelope for the public, unauthenticated GET /api/v1/status.

    Attributes:
        status: Liveness state — always "running" once the process is
            serving requests.
        service: Which service answered.
        version: Deployed service version.
        timestamp: When this response was generated, ISO-8601.
    """

    status: str
    service: str
    version: str
    timestamp: str


@dataclass(slots=True, frozen=True)
class RegistrationStatusResponse:
    """Envelope for the public, unauthenticated GET /api/v1/registration-status.

    Attributes:
        self_registration_enabled: Whether ``Config.ALLOW_SELF_REGISTRATION``
            is currently on for this deployment.
    """

    self_registration_enabled: bool


@hello_bp.route("/hello", methods=["GET"])
@auth_required
async def hello() -> tuple[dict[str, Any], int]:
    """Hello world endpoint - requires authentication."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    return (
        {
            "message": f"Hello, {user.get('full_name') or user['email']}!",
            "timestamp": datetime.now(UTC).isoformat(),
            "user": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
            },
        },
        200,
    )


@hello_bp.route("/hello/protected", methods=["GET"])
@auth_required
@require_scope(SCOPE_PLATFORM_READ)
async def hello_protected() -> tuple[dict[str, Any], int]:
    """Protected hello — requires the ``platform:read`` scope.

    ``platform:read`` is carried by the platform admin and maintainer
    bundles and by nothing else, so this admits exactly the callers the
    previous ``@maintainer_or_admin_required`` did, decided on the token's
    scope claim instead of a role-name comparison.
    """
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    return (
        {
            "message": (
                f"Hello, {user.get('full_name') or user['email']}! " "You have elevated access."
            ),
            "timestamp": datetime.now(UTC).isoformat(),
            "access_level": SCOPE_PLATFORM_READ,
            "your_role": user["role"],
        },
        200,
    )


@hello_bp.route("/status", methods=["GET"])
@validate_response(StatusResponse)
async def status() -> tuple[Any, int]:
    """Public status endpoint - no authentication required."""
    return (
        StatusResponse(
            status="running",
            service="portal-api",
            version="1.0.0",
            timestamp=datetime.now(UTC).isoformat(),
        ),
        200,
    )


@hello_bp.route("/registration-status", methods=["GET"])
@validate_response(RegistrationStatusResponse)
async def registration_status() -> tuple[Any, int]:
    """Public: whether this deployment currently allows self-service signup.

    Deliberately unauthenticated, and deliberately the ONLY thing this route
    reports. ``Config.ALLOW_SELF_REGISTRATION`` closed by default is correct
    (app/auth.py's ``register`` checks it before anything else runs) — but a
    visitor deciding whether to look for a sign-up button has no token by
    definition, so the one place that already answers "what is on for this
    deployment" (``GET /api/v1/features``) cannot be the one that answers
    this: it is auth-gated on purpose, for the same reason the full OpenAPI
    document is (app/openapi.py) — publishing the whole commercial/flag
    surface to an anonymous caller is reconnaissance, not a feature.

    This route is the narrow exception, not a second unauthenticated
    features endpoint: it names exactly one boolean, never anything else a
    future flag or licensed capability might add to ``/features``. Whether a
    caller can currently self-register is not secret — the sign-up button's
    presence or absence would tell an anonymous visitor the same thing — so
    the risk here is scope creep on THIS route, not disclosure.
    """
    return (
        RegistrationStatusResponse(
            self_registration_enabled=bool(current_app.config.get("ALLOW_SELF_REGISTRATION", False))
        ),
        200,
    )
