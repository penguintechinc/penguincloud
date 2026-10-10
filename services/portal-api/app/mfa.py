"""Multi-Factor Authentication (2FA/MFA) Endpoints."""

import json
import secrets
import time
from typing import Any

import pyotp
from quart import Blueprint, jsonify, request

from . import ratelimit
from .middleware import auth_required, get_current_user
from .models import (
    create_mfa_secret,
    disable_mfa,
    enable_mfa,
    get_db,
    get_mfa_secret,
    update_mfa_last_counter,
)

mfa_bp = Blueprint("mfa", __name__)

#: TOTP step, in seconds (pyotp's default). One counter == one 30s window.
_TOTP_STEP = 30


async def verify_totp_code(
    user_id: int, mfa_record: dict[str, Any], code: str, *, valid_window: int = 1
) -> bool:
    """Verify a TOTP code and consume it to prevent replay.

    pyotp's ``TOTP.verify`` accepts any code inside ``valid_window`` but does
    not record that it was used, so the same code is replayable for the whole
    window. This instead finds the matching time-step counter, rejects it if
    its counter is at or below the last one accepted for the user
    (``last_totp_counter``), and otherwise advances the stored counter — so a
    given code works exactly once.
    """
    secret = mfa_record.get("secret")
    if not secret or not code:
        return False

    totp = pyotp.TOTP(secret)
    now = int(time.time())
    last = mfa_record.get("last_totp_counter")

    # Check the window oldest-first so the recorded counter only ever moves
    # forward to the step that actually matched.
    for offset in range(-valid_window, valid_window + 1):
        ts = now + offset * _TOTP_STEP
        counter = ts // _TOTP_STEP
        if pyotp.utils.strings_equal(str(totp.at(ts)), str(code)):
            if last is not None and counter <= int(last):
                return False  # already used (replay) or older than the last accepted
            await update_mfa_last_counter(user_id, counter)
            return True
    return False


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
    if user is None:  # pragma: no cover - auth_required guarantees a user
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
@ratelimit.rate_limited("mfa_verify", account_key_fn=ratelimit.user_account_key)
async def verify_mfa() -> tuple[Any, int]:
    """Verify TOTP code and enable MFA."""
    user = get_current_user()
    if user is None:  # pragma: no cover - auth_required guarantees a user
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

    # Verify TOTP code (allow 30-second window), single-use
    if not await verify_totp_code(user_id, mfa, totp_code):
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
@ratelimit.rate_limited("mfa_disable", account_key_fn=ratelimit.user_account_key)
async def disable_mfa_endpoint() -> tuple[Any, int]:
    """Disable MFA (requires password and TOTP verification)."""
    user = get_current_user()
    if user is None:  # pragma: no cover - auth_required guarantees a user
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

    if not await verify_totp_code(user_id, mfa, totp_code):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Disable MFA
    await disable_mfa(user_id)

    return jsonify({"message": "MFA disabled successfully"}), 200


@mfa_bp.route("/backup-codes", methods=["GET"])
@auth_required
async def get_backup_codes() -> tuple[Any, int]:
    """View backup codes."""
    user = get_current_user()
    if user is None:  # pragma: no cover - auth_required guarantees a user
        return jsonify({"error": "Unauthorized"}), 401
    user_id = user["id"]

    mfa = await get_mfa_secret(user_id)
    if not mfa or not mfa.get("enabled_at"):
        return jsonify({"error": "MFA not enabled"}), 404

    codes = parse_backup_codes(mfa.get("backup_codes", "[]"))
    return jsonify({"backup_codes": codes}), 200


@mfa_bp.route("/backup-codes/regenerate", methods=["POST"])
@auth_required
@ratelimit.rate_limited("mfa_backup_regenerate", account_key_fn=ratelimit.user_account_key)
async def regenerate_backup_codes() -> tuple[Any, int]:
    """Regenerate backup codes."""
    user = get_current_user()
    if user is None:  # pragma: no cover - auth_required guarantees a user
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

    if not await verify_totp_code(user_id, mfa, totp_code):
        return jsonify({"error": "Invalid TOTP code"}), 401

    # Generate new backup codes
    new_codes = generate_backup_codes()

    # Update in database via penguin-dal. Encrypt at rest to match
    # create_mfa_secret (get_mfa_secret decrypts on read).
    from .encryption import encrypt_value

    db = get_db()
    await db(db.mfa_secrets.user_id == user_id).update(
        backup_codes=encrypt_value(format_backup_codes(new_codes))
    )

    return (
        jsonify({"message": "Backup codes regenerated", "backup_codes": new_codes}),
        200,
    )
