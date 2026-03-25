"""License Server API endpoints."""

from flask import Blueprint, jsonify

from .license import license_manager
from .middleware import admin_required

license_bp = Blueprint("license", __name__)


@license_bp.route("/status", methods=["GET"])
@admin_required
def get_license_status():
    """
    Get license status.

    Returns:
        JSON response with license details (admin only).
    """
    status = license_manager.get_status()
    return jsonify(status), 200
