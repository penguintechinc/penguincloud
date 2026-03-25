"""Hello World Endpoint - Example authenticated endpoint."""

from datetime import datetime

from flask import Blueprint, jsonify

from .middleware import auth_required, get_current_user, maintainer_or_admin_required

hello_bp = Blueprint("hello", __name__)


@hello_bp.route("/hello", methods=["GET"])
@auth_required
def hello():
    """Hello world endpoint - requires authentication."""
    user = get_current_user()

    return (
        jsonify(
            {
                "message": f"Hello, {user.get('full_name') or user['email']}!",
                "timestamp": datetime.utcnow().isoformat(),
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "role": user["role"],
                },
            }
        ),
        200,
    )


@hello_bp.route("/hello/protected", methods=["GET"])
@auth_required
@maintainer_or_admin_required
def hello_protected():
    """Protected hello - requires maintainer or admin role."""
    user = get_current_user()

    return (
        jsonify(
            {
                "message": f"Hello, {user.get('full_name') or user['email']}! You have elevated access.",
                "timestamp": datetime.utcnow().isoformat(),
                "access_level": "maintainer_or_admin",
                "your_role": user["role"],
            }
        ),
        200,
    )


@hello_bp.route("/status", methods=["GET"])
def status():
    """Public status endpoint - no authentication required."""
    return (
        jsonify(
            {
                "status": "running",
                "service": "flask-backend",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ),
        200,
    )
