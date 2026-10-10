"""License Server API endpoints (async Quart)."""

from typing import Any

from quart import Blueprint, jsonify

from .authz import SCOPE_LICENSE_READ, require_scope
from .license import license_manager
from .middleware import auth_required

license_bp = Blueprint("license", __name__)


@license_bp.route("/status", methods=["GET"])
@auth_required
@require_scope(SCOPE_LICENSE_READ)
async def get_license_status() -> tuple[Any, int]:
    """Get license status.

    Gated on the ``license:read`` scope, which the platform-admin bundle
    carries and no other role does — the same authority the previous
    ``@admin_required`` conferred, expressed as a scope so the decision is
    made on the token claim rather than on a role-name comparison
    (security.md: authorization decisions on scope, never role names).

    Returns:
        JSON response with license details.
    """
    status = license_manager.get_status()
    return jsonify(status), 200
