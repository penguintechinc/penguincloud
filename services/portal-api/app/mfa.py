"""Multi-Factor Authentication (2FA/MFA) Endpoints."""

import json
import secrets
from typing import Any

import pyotp
from quart import Blueprint, jsonify, request

from .middleware import auth_required, get_current_user
from .models import (
    create_mfa_secret,
    disable_mfa,
    enable_mfa,
    get_db,
    get_mfa_secret,
)

mfa_bp = Blueprint("mfa", __name__)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate backup codes for account recovery."""
    return [secrets.token_hex(4).upper() for _ in range(count)]


def format_backup_codes(codes: list[str]) -> str:
    """Format backup codes as JSON string."""
    return json.dumps(codes)


def parse_backup_codes(codes_json: str) -> list[str]:
    """Parse backup codes from JSON string."""
    if not codes_json:
        return []
    try:
        result = json.loads(codes_json)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


@mfa_bp.route("/setup", methods=["POST"])
@auth_required
async def setup_mfa() -> tuple[Any, int]:
    """Generate TOTP secret and QR code for 2FA setup."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]

    # Check if MFA already exists
    existing = await get_mfa_secret(user_id)
    if existing and existing.get("enabled_at"):
        return jsonify({"error": "MFA already enabled for this user"}), 409

    # Generate secret and backup codes
    secret = pyotp.random_base32()
    backup_codes = generate_backup_codes()

    # Store secret (not enabled yet)
    await create_mfa_secret(user_id, secret, format_backup_codes(backup_codes))

    # Generate QR code provisioning URI
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user["email"], issuer_name="Project Template")

    return (
        jsonify(
            {
                "secret": secret,
                "provisioning_uri": provisioning_uri,
                "backup_codes": backup_codes,
                "message": "Scan QR code and verify with a code to enable MFA",
            }
        ),
        200,
    )


@mfa_bp.route("/verify", methods=["POST"])
@auth_required
# TODO(phase-3): Add rate limiting via quart-rate-limiter adapter
async def verify_mfa() -> tuple[Any, int]:
    """Verify TOTP code and enable MFA."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]
    data = await request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    totp_code = data.get("code", "").strip()
    if not totp_code or len(totp_code) != 6:
        return jsonify({"error": "TOTP code must be 6 digits"}), 400

    # Get stored secret
    mfa = await get_mfa_secret(user_id)
    if not mfa:
        return jsonify({"error": "MFA secret not found"}), 404

    # Verify TOTP code (allow 30-second window)
    totp = pyotp.TOTP(mfa["secret"])
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Enable MFA
    await enable_mfa(user_id)

    return (
        jsonify(
            {
                "message": "MFA enabled successfully",
                "backup_codes": parse_backup_codes(mfa.get("backup_codes", "[]")),
            }
        ),
        200,
    )


@mfa_bp.route("/disable", methods=["POST"])
@auth_required
# TODO(phase-3): Add rate limiting via quart-rate-limiter adapter
async def disable_mfa_endpoint() -> tuple[Any, int]:
    """Disable MFA (requires password and TOTP verification)."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]
    data = await request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    password = data.get("password", "")
    totp_code = data.get("code", "").strip()

    if not password or not totp_code:
        return jsonify({"error": "Password and TOTP code required"}), 400

    # Verify password
    from .auth import verify_password_async
    from .models import get_user_by_id

    current = await get_user_by_id(user_id)
    if not current:
        return jsonify({"error": "User not found"}), 404
    verify_result = await verify_password_async(password, current["password_hash"])
    if not verify_result:
        return jsonify({"error": "Invalid password"}), 401

    # Verify TOTP code
    mfa = await get_mfa_secret(user_id)
    if not mfa:
        return jsonify({"error": "MFA not enabled"}), 404

    totp = pyotp.TOTP(mfa["secret"])
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Disable MFA
    await disable_mfa(user_id)

    return jsonify({"message": "MFA disabled successfully"}), 200


@mfa_bp.route("/backup-codes", methods=["GET"])
@auth_required
async def get_backup_codes() -> tuple[Any, int]:
    """View backup codes."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]

    mfa = await get_mfa_secret(user_id)
    if not mfa or not mfa.get("enabled_at"):
        return jsonify({"error": "MFA not enabled"}), 404

    codes = parse_backup_codes(mfa.get("backup_codes", "[]"))
    return jsonify({"backup_codes": codes}), 200


@mfa_bp.route("/backup-codes/regenerate", methods=["POST"])
@auth_required
# TODO(phase-3): Add rate limiting via quart-rate-limiter adapter
async def regenerate_backup_codes() -> tuple[Any, int]:
    """Regenerate backup codes."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]
    data = await request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    totp_code = data.get("code", "").strip()
    if not totp_code:
        return jsonify({"error": "TOTP code required"}), 400

    # Get stored secret and verify TOTP
    mfa = await get_mfa_secret(user_id)
    if not mfa or not mfa.get("enabled_at"):
        return jsonify({"error": "MFA not enabled"}), 404

    totp = pyotp.TOTP(mfa["secret"])
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Generate new backup codes
    new_codes = generate_backup_codes()

    # Update in database via penguin-dal
    db = get_db()
    await db(db.mfa_secrets.user_id == user_id).update(backup_codes=format_backup_codes(new_codes))

    return (
        jsonify({"message": "Backup codes regenerated", "backup_codes": new_codes}),
        200,
    )
