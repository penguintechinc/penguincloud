"""Hello World Endpoint - Example authenticated endpoint (async Quart)."""

from datetime import UTC, datetime
from typing import Any

from quart import Blueprint

from .middleware import auth_required, get_current_user, maintainer_or_admin_required

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
@maintainer_or_admin_required
async def hello_protected() -> tuple[dict[str, Any], int]:
    """Protected hello - requires maintainer or admin role."""
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
            "access_level": "maintainer_or_admin",
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
            "service": "flask-backend",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        200,
    )
