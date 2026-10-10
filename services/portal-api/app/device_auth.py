"""RFC 8628 OAuth 2.0 Device Authorization Grant -- headless `pcli` login.

Four endpoints, three roles
============================
* **POST /api/v1/auth/device/authorize** -- unauthenticated. The CLI calls
  this to mint a ``device_code`` (a high-entropy opaque secret it polls
  with) and a ``user_code`` (a short, human-typeable code it shows the
  user). RFC 8628 SS3.1/3.2.
* **POST /api/v1/auth/device/approve** and **.../device/deny** --
  authenticated. A human, in a real browser session with their own
  existing login, enters/confirms the ``user_code`` shown by the CLI. This
  is the ONLY place a device authorization is bound to an identity: the
  approving caller's own already-validated JWT is the sole source of who
  the resulting token will be minted for. RFC 8628 SS3.3.
* **POST /api/v1/auth/device/token** -- unauthenticated, polled by the CLI
  with the ``device_code`` from step 1. Returns an RFC 8628 SS3.5 error
  (``authorization_pending`` / ``slow_down`` / ``expired_token`` /
  ``access_denied``) until the human has approved, then the real token set
  -- minted through app.auth.issue_and_store_token_set, the exact same
  primitive app.auth.login uses, so a device-issued token is claim-for-
  claim identical to one obtained by password login. Single-use: a second
  poll after a successful one gets ``expired_token``, never a second token.

No client registry
===================
RFC 8628's token endpoint accepts ``client_id`` (SS3.4) because it is
designed for a multi-client authorization server. This service has no
OAuth client registration surface anywhere else (app.auth.login,
.../refresh are JSON bodies with no client_id either), so device/token
mirrors THEIR shape -- ``{"device_code": "..."}"``, JSON, nothing else --
rather than inventing a client registry for this one grant type alone.

Never trust the client's polling cadence
=========================================
``slow_down`` (RFC 8628 SS3.5) exists because an unthrottled poll loop is a
brute-force amplifier on ``device_code`` guesses. Enforced here from the
row's OWN ``last_polled_at`` column (app.models.
touch_device_authorization_poll), written on every poll attempt regardless
of outcome -- never from anything the client claims about its own timing.

user_code is guessable by design -- the mitigation is the account-scoped
rate limit, not secrecy
========================================================================
8 characters from a 32-symbol alphabet (RFC 8628 SS5.1's own recommended
shape -- ~40 bits) is short enough to be typed by hand and short enough to
be brute-forced without a rate limit. app.ratelimit's "device_approve"
bucket (5 attempts/300s, account-scoped on the APPROVING caller -- see
that module) is what actually closes this, the same way app.ratelimit's
module docstring explains for TOTP codes. approve and deny share one
bucket: they are both "an attempt against a user_code", and two separate
budgets would double an attacker's guesses for zero benefit to a real
caller, who only ever needs one or the other.

Never log a device_code, user_code, or minted token
=====================================================
These are credentials, RFC 8628 SS5.4's own explicit concern for
user_code. Every log call in this module is scoped to non-secret fields
(row id, status, bucket name) -- see
tests/api/test_device_auth_security.py for the enforced version of this
claim (a recording-logger fake, not caplog -- see
tests/api/test_password_reset_delivery.py's module docstring for why
caplog would pass vacuously here).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import quote

import structlog
from quart import Blueprint, current_app
from quart_schema import validate_request, validate_response

from . import ratelimit
from .auth import (
    AuthenticatedUser,
    LoginResponse,
    build_absolute_url,
    issue_and_store_token_set,
)
from .middleware import auth_required, get_current_user
from .models import (
    approve_device_authorization,
    consume_device_authorization,
    create_device_authorization,
    deny_device_authorization,
    get_device_authorization_by_device_code_hash,
    get_device_authorization_by_user_code,
    get_user_by_id,
    touch_device_authorization_poll,
)

log = structlog.get_logger()

device_auth_bp = Blueprint("device_auth", __name__)

#: Fallback values, only reached if create_app somehow started without
#: config.py's Config.DEVICE_CODE_TTL/DEVICE_POLL_INTERVAL -- current_app.
#: config.get() below always finds the real ones in every real deployment
#: and every test app() fixture.
_DEFAULT_DEVICE_CODE_TTL: Final[int] = 600
_DEFAULT_DEVICE_POLL_INTERVAL: Final[int] = 5

#: 32-symbol alphabet, RFC 8628 SS5.1's own recommended shape for
#: user_code (8 chars from a 32-char alphabet -- ~40 bits of entropy).
#: Excludes visually ambiguous characters (0/O, 1/I/L) since this code is
#: read off one screen and typed into another.
_USER_CODE_ALPHABET: Final[str] = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_USER_CODE_LEN: Final[int] = 8
_USER_CODE_GROUP: Final[int] = 4

#: The RFC 8628 SS3.5 error codes this module can return, plus the two
#: this deployment adds for the same "never a token" family
#: (``invalid_request`` for a malformed poll, matching RFC 6749 SS5.2).
_ERROR_AUTHORIZATION_PENDING: Final[str] = "authorization_pending"
_ERROR_SLOW_DOWN: Final[str] = "slow_down"
_ERROR_EXPIRED_TOKEN: Final[str] = "expired_token"  # noqa: S105 -- RFC 8628 error code, not a credential
_ERROR_ACCESS_DENIED: Final[str] = "access_denied"
_ERROR_INVALID_REQUEST: Final[str] = "invalid_request"
_ERROR_INVALID_USER_CODE: Final[str] = "invalid_user_code"


@dataclass(slots=True, frozen=True)
class DeviceAuthorizationResponse:
    """Envelope for POST /api/v1/auth/device/authorize (RFC 8628 SS3.2).

    Attributes:
        device_code: High-entropy opaque secret; the CLI polls
            /device/token with this. Never displayed to the user.
        user_code: Short, human-typeable code; the CLI displays this and
            the user enters it at verification_uri.
        verification_uri: Where the user goes to enter user_code.
        verification_uri_complete: Same, with user_code pre-filled --
            lets a CLI print one clickable link.
        expires_in: Seconds until device_code/user_code both expire.
        interval: Minimum seconds the CLI must wait between polls.
    """

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(slots=True)
class DeviceTokenRequest:
    """Request body for POST /api/v1/auth/device/token."""

    device_code: str


@dataclass(slots=True)
class DeviceUserCodeRequest:
    """Request body shared by POST .../device/approve and .../device/deny."""

    user_code: str


@dataclass(slots=True, frozen=True)
class DeviceResolutionResponse:
    """Envelope for POST .../device/approve and .../device/deny.

    Attributes:
        status: "approved" or "denied".
        user_code: Echoes the resolved code back, formatted, for the
            browser page's own confirmation display.
    """

    status: str
    user_code: str


def _hash_secret(value: str) -> str:
    """Digest a device_code before it is stored or looked up.

    Same SHA-256-hex scheme as app.auth.hash_refresh_token, applied to a
    different secret -- named locally rather than imported so this
    module's own docstring stays the single place a reader needs to look
    to see every secret this file handles gets the same treatment.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _generate_user_code() -> str:
    """A fresh RFC 8628-shaped user_code: 8 chars, 32-symbol alphabet."""
    return "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(_USER_CODE_LEN))


def _format_user_code(code: str) -> str:
    """Render a stored (dash-free) user_code for display: "WDGTBKRP" -> "WDGT-BKRP"."""
    return f"{code[:_USER_CODE_GROUP]}-{code[_USER_CODE_GROUP:]}"


def _normalize_user_code(raw: str) -> str:
    """Upper-case and strip everything but alphanumerics, for lookup.

    Accepts "wdgt-bkrp", "WDGT BKRP" or "WDGTBKRP" identically -- stored
    values never contain a dash (see _generate_user_code), so the
    dash/space a human is likely to type or a CLI likely to render must be
    removed before comparison, not just case-folded.
    """
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def _aware(value: datetime) -> datetime:
    """Normalize a DB-fetched datetime to tz-aware UTC before comparing it.

    penguin-dal/SQLite round-trips DATETIME columns as timezone-naive,
    while every timestamp this module writes uses datetime.now(UTC) --
    comparing the two directly raises TypeError. Identical fix to
    app.teams.accept_invitation's, needed here for the same reason: this
    module must distinguish several outcomes (authorization_pending vs
    slow_down vs expired_token vs access_denied) from one fetched row, so
    the comparison can't be pushed into a WHERE clause the way
    is_refresh_token_valid does.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _device_code_ttl() -> int:
    return int(current_app.config.get("DEVICE_CODE_TTL", _DEFAULT_DEVICE_CODE_TTL))


def _poll_interval() -> int:
    return int(current_app.config.get("DEVICE_POLL_INTERVAL", _DEFAULT_DEVICE_POLL_INTERVAL))


def _device_error(code: str) -> tuple[dict[str, str], int]:
    """RFC 6749 SS5.2 shape: 400 + `{"error": "<code>"}`, used by every SS3.5 branch."""
    return {"error": code}, 400


@device_auth_bp.route("/authorize", methods=["POST"])
@ratelimit.rate_limited("device_authorize")
@validate_response(DeviceAuthorizationResponse)
async def device_authorize() -> tuple[Any, int]:
    """Mint a device_code/user_code pair. Unauthenticated. RFC 8628 SS3.1/3.2."""
    ttl = _device_code_ttl()
    interval = _poll_interval()
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

    device_code = secrets.token_urlsafe(32)
    stored_user_code = _generate_user_code()

    await create_device_authorization(
        device_code_hash=_hash_secret(device_code),
        user_code=stored_user_code,
        expires_at=expires_at,
    )

    display_code = _format_user_code(stored_user_code)
    verification_uri = build_absolute_url("/device")
    verification_uri_complete = build_absolute_url(f"/device?user_code={quote(display_code)}")

    log.info("device_authorization_created", expires_in=ttl)

    return (
        DeviceAuthorizationResponse(
            device_code=device_code,
            user_code=display_code,
            verification_uri=verification_uri,
            verification_uri_complete=verification_uri_complete,
            expires_in=ttl,
            interval=interval,
        ),
        200,
    )


async def _lookup_pending_by_user_code(raw: str) -> dict[str, Any] | None:
    """Normalize + look up a PENDING, unexpired authorization by user_code.

    Returns None uniformly for an unknown code, a wrong-length code, an
    already-resolved code, or an expired one -- distinguishing them would
    tell whoever is submitting guesses which case they hit, the same
    reasoning as app.auth._REFRESH_REJECTED's single message for every
    refresh-token failure mode. Named to double as the CREDENTIAL_
    VERIFICATION_PRIMITIVES entry in
    tests/api/test_credential_routes_are_rate_limited.py: the guard used
    to derive which routes are credential-accepting resolves this by NAME
    off app.models.get_device_authorization_by_user_code's own call site,
    so this wrapper deliberately does not rename or wrap that call in a
    way that would hide it from that scan.
    """
    normalized = _normalize_user_code(raw)
    if len(normalized) != _USER_CODE_LEN:
        return None
    row = await get_device_authorization_by_user_code(normalized)
    if row is None:
        return None
    if row["status"] != "pending":
        return None
    if _aware(row["expires_at"]) <= datetime.now(UTC):
        return None
    return row


@device_auth_bp.route("/approve", methods=["POST"])
@auth_required
@ratelimit.rate_limited("device_approve", account_key_fn=ratelimit.user_account_key)
@validate_request(DeviceUserCodeRequest)
@validate_response(DeviceResolutionResponse)
async def device_approve(data: DeviceUserCodeRequest) -> tuple[Any, int]:
    """Bind a pending device authorization to the CALLING user. RFC 8628 SS3.3.

    The approving user's identity comes ENTIRELY from their own already-
    verified JWT (get_current_user, via @auth_required) -- user_code
    selects WHICH pending authorization to resolve, never WHO it resolves
    to. There is deliberately no tenant selection here: see
    app.models_sqlalchemy.DeviceAuthorization's docstring for why the
    resulting grant mirrors login's own current unscoped-tenant shape.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    row = await _lookup_pending_by_user_code(data.user_code)
    if row is None:
        return {"error": _ERROR_INVALID_USER_CODE}, 400

    if not await approve_device_authorization(row["id"], user["id"]):
        # Lost a race: resolved (approved/denied) or expired between the
        # lookup above and this write. Same refusal either way.
        return {"error": _ERROR_INVALID_USER_CODE}, 400

    log.info("device_authorization_approved", device_authorization_id=row["id"])

    return (
        DeviceResolutionResponse(status="approved", user_code=_format_user_code(row["user_code"])),
        200,
    )


@device_auth_bp.route("/deny", methods=["POST"])
@auth_required
@ratelimit.rate_limited("device_approve", account_key_fn=ratelimit.user_account_key)
@validate_request(DeviceUserCodeRequest)
@validate_response(DeviceResolutionResponse)
async def device_deny(data: DeviceUserCodeRequest) -> tuple[Any, int]:
    """Reject a pending device authorization. The next poll gets access_denied."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    row = await _lookup_pending_by_user_code(data.user_code)
    if row is None:
        return {"error": _ERROR_INVALID_USER_CODE}, 400

    if not await deny_device_authorization(row["id"]):
        return {"error": _ERROR_INVALID_USER_CODE}, 400

    log.info("device_authorization_denied", device_authorization_id=row["id"])

    return (
        DeviceResolutionResponse(status="denied", user_code=_format_user_code(row["user_code"])),
        200,
    )


@device_auth_bp.route("/token", methods=["POST"])
@ratelimit.rate_limited("device_token")
@validate_request(DeviceTokenRequest)
@validate_response(LoginResponse)
async def device_token(data: DeviceTokenRequest) -> tuple[Any, int]:
    """Poll for a token. Unauthenticated. RFC 8628 SS3.4/3.5.

    Order of checks is deliberate: expiry is checked BEFORE slow_down (an
    expired code must never yield a token no matter how it is polled), and
    slow_down is enforced UNIFORMLY across every status (including
    "approved") before branching on status -- a client that ignores
    `interval` gets throttled the same way regardless of how close the
    flow is to finishing.
    """
    device_code = data.device_code.strip()
    if not device_code:
        return _device_error(_ERROR_INVALID_REQUEST)

    now = datetime.now(UTC)
    row = await get_device_authorization_by_device_code_hash(_hash_secret(device_code))

    if row is None:
        # Unknown device_code is indistinguishable from an expired one --
        # RFC 8628 defines no separate code for "never existed", and
        # inventing one would let a client fingerprint which is true.
        return _device_error(_ERROR_EXPIRED_TOKEN)

    if _aware(row["expires_at"]) <= now:
        return _device_error(_ERROR_EXPIRED_TOKEN)

    interval = _poll_interval()
    last_polled_at = row.get("last_polled_at")
    if last_polled_at is not None:
        elapsed = (now - _aware(last_polled_at)).total_seconds()
        if elapsed < interval:
            return _device_error(_ERROR_SLOW_DOWN)

    await touch_device_authorization_poll(row["id"], now)

    status = row["status"]
    if status == "pending":
        return _device_error(_ERROR_AUTHORIZATION_PENDING)
    if status == "denied":
        return _device_error(_ERROR_ACCESS_DENIED)
    if status == "consumed":
        # Replay of an already-claimed device_code -- single-use. RFC 8628
        # has no distinct code for this; expired_token is the closest
        # ("this device_code is no longer valid to poll").
        return _device_error(_ERROR_EXPIRED_TOKEN)

    # status == "approved": claim it exactly once, racing polls included.
    if not await consume_device_authorization(row["id"]):
        return _device_error(_ERROR_EXPIRED_TOKEN)

    user_id = row.get("user_id")
    user = await get_user_by_id(int(user_id)) if user_id is not None else None
    if user is None or not user.get("is_active"):
        return _device_error(_ERROR_ACCESS_DENIED)

    # Same primitive app.auth.login uses, with the same unscoped tenant_id
    # login itself uses today -- the token this mints is claim-for-claim
    # identical to a password-login token for this user, per the module
    # docstring.
    token_set = await issue_and_store_token_set(
        user["id"],
        tenant_id="",
        role=user["role"],
    )

    log.info("device_authorization_consumed", device_authorization_id=row["id"])

    return (
        LoginResponse(
            access_token=token_set["access_token"],
            refresh_token=token_set["refresh_token"],
            # RFC 6749 fixed token_type string, not a credential.
            token_type="Bearer",  # noqa: S106
            expires_in=token_set["expires_in"],
            user=AuthenticatedUser(
                id=user["id"],
                email=user["email"],
                full_name=user.get("full_name", ""),
                role=user["role"],
            ),
        ),
        200,
    )
