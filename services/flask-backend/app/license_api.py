"""License Server API endpoints (async Quart)."""

from typing import Any

from quart import Blueprint, jsonify

from .license import license_manager
from .middleware import admin_required, auth_required

license_bp = Blueprint("license", __name__)


@license_bp.route("/status", methods=["GET"])
@auth_required
@admin_required
async def get_license_status() -> tuple[Any, int]:
    """
    Get license status.

    Returns:
        JSON response with license details (admin only).
    """
    status = license_manager.get_status()
    return jsonify(status), 200
