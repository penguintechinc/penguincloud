"""Hello World Endpoint - Example authenticated endpoint (async Quart)."""

from datetime import UTC, datetime
from typing import Any

from quart import Blueprint

from .authz import SCOPE_PLATFORM_READ, require_scope
from .middleware import auth_required, get_current_user

hello_bp = Blueprint("hello", __name__)


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
                f"Hello, {user.get('full_name') or user['email']}! "
                "You have elevated access."
            ),
            "timestamp": datetime.now(UTC).isoformat(),
            "access_level": SCOPE_PLATFORM_READ,
            "your_role": user["role"],
        },
        200,
    )


@hello_bp.route("/status", methods=["GET"])
async def status() -> tuple[dict[str, Any], int]:
    """Public status endpoint - no authentication required."""
    return (
        {
            "status": "running",
            "service": "portal-api",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        200,
    )
