"""Rate limiting for every credential-accepting endpoint. On by default.

Founding principle (see docs/APP_STANDARDS.md and the CODEOWNERS-era
security review): a fresh deployment is secure when the operator
configures NOTHING. That ruled out an env var of any kind here — a
``RATE_LIMIT_ENABLED`` knob is a footgun with only one dangerous setting,
and "off" is exactly what every credential-accepting route had before this
module existed. The limits below are fixed constants, the same way
app/health_poller.py's poll interval and app/mfa.py's ``valid_window=1``
are fixed rather than deployment-tunable: a security control is not
deployment configuration.

What this defends
==================
``pyotp``'s ``valid_window=1`` accepts roughly 3 live 6-digit TOTP codes
out of 10**6 per guess. Unthrottled, an attacker holding a password can
exhaust that space in hours. The account-scoped windows below
(:data:`_ACCOUNT_WINDOWS`) are what turn that into years: 5 attempts per 5
minutes per account, independent of how many source IPs the guesses are
spread across.

Two scopes, checked together
=============================
* **IP-scoped** (:data:`_IP_WINDOWS`) — every bucket has one. It is the
  only defence available before an account is identifiable at all
  (``register``, a wrong/guessed refresh or reset token) and a floor
  underneath every other bucket.
* **Account-scoped** (:data:`_ACCOUNT_WINDOWS`) — narrower, and the one
  that actually stops a targeted attack: it is keyed on the *submitted*
  identifier (an email typed into the login form, or the authenticated
  caller's own user id), never a verified one, so a wrong password against
  a real account and every guess against a nonexistent one are metered
  identically. Nothing here reveals which case occurred.

Fails closed, never open
=========================
Every credential-accepting route (see
``tests/api/test_credential_routes_are_rate_limited.py`` for the derived
list) reaches :func:`check`, which ALWAYS enforces from the per-process
in-memory counter, and additionally from the shared Valkey store
(``CACHE_HOST`` — the same config app/health_cache.py already reads) when
it is configured and reachable.

This is deliberately the opposite trade-off from app/health_cache.py.
Health data going stale for an outage's duration is an acceptable
degradation — the endpoint still answers, just with a worker-local view.
A rate limiter that goes stale the same way, silently, at the moment
Valkey is unreachable, would mean "no limiting" on every deployment that
has not configured a shared cache — the common case, per
health_cache.log_startup_state's own warning. So the local counter is
never optional here: it runs unconditionally, and the effective count is
``max(local, shared)`` rather than "shared if present else local" — a
Valkey hiccup mid-window can only ever make one worker's view look too
LOW, never reset a caller's count to zero.

The trade-off this accepts: with CACHE_HOST unset (or unreachable), each
hypercorn worker enforces its own counter, so the EFFECTIVE limit for a
multi-worker deployment is ``per-worker limit x worker count`` rather than
the stated limit cluster-wide. Still bounded, never unbounded — which is
the property that matters here.

What this cannot see
=====================
* The fixed-window counter (INCR, then EXPIRE only on the first hit) has
  the standard boundary-double-count race shared by every fixed-window
  rate limiter: a burst spanning a window boundary can admit up to
  ``2 x max_attempts`` in the worst case. A sliding-window-log
  implementation would close this at the cost of a per-attempt timestamp
  list; not built here because the account-scoped windows this exists to
  protect (5 per 300s) tolerate a worst case of 10 per 300s without
  changing the years-not-hours conclusion above.
* A distributed attacker spreading guesses across many source IPs AND
  many differently-cased/whitespace-padded submitted emails defeats the
  account key. ``_hash_subject`` normalises via the same
  ``.strip().lower()`` the login/register routes already apply before
  comparing against the stored account, so this is bounded to genuine
  case/whitespace variants, not open-ended.
* Clearing an in-progress lockout no longer requires restarting the
  affected worker or evicting the Valkey key by hand:
  ``POST /api/v1/users/<user_id>/rate-limit-reset``
  (app/users.py::reset_user_rate_limit) calls :func:`rate_limit_reset`
  behind ``members:manage`` in the target's tenant, audit-logged, and
  itself rate limited via the ``admin_ratelimit_reset`` bucket above. Every
  window is still bounded (60s-3600s; see the tables below) even without
  that route, so the worst case was always a wait, not a permanent lock —
  the route exists for operator convenience and auditability, not to close
  a hole. The WARNING log line and :data:`RATE_LIMIT_REJECTIONS`
  Prometheus counter (labelled ``bucket``/``scope``) remain the
  observability half.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Final, ParamSpec, TypeVar

import structlog
from prometheus_client import Counter
from quart import current_app, request

log = structlog.get_logger()

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(slots=True, frozen=True)
class _Window:
    """One bucket's cap: at most ``max_attempts`` inside ``seconds``."""

    max_attempts: int
    seconds: int


#: IP-scoped windows, one per credential-accepting bucket. Deliberately
#: more generous than the account-scoped table: this is the floor that
#: applies even before an account is identifiable, not the primary
#: defence (see module docstring).
_IP_WINDOWS: Final[dict[str, _Window]] = {
    "login": _Window(max_attempts=20, seconds=60),
    "register": _Window(max_attempts=20, seconds=3600),
    "refresh": _Window(max_attempts=30, seconds=60),
    "forgot_password": _Window(max_attempts=10, seconds=3600),
    "reset_password": _Window(max_attempts=20, seconds=3600),
    "confirm_email": _Window(max_attempts=20, seconds=3600),
    "mfa_verify": _Window(max_attempts=20, seconds=60),
    "mfa_disable": _Window(max_attempts=20, seconds=60),
    "mfa_backup_regenerate": _Window(max_attempts=20, seconds=60),
    "change_password": _Window(max_attempts=20, seconds=60),
    # Not a credential-verification route itself — see
    # app/users.py::reset_user_rate_limit. It exists so the admin clear
    # primitive below cannot become the hole in the protection it manages:
    # unthrottled, it would let a caller who already holds members:manage
    # authority repeatedly clear a target's lockout as fast as the target
    # can exhaust it, which defeats the account-scoped windows above just
    # as completely as not having them.
    "admin_ratelimit_reset": _Window(max_attempts=30, seconds=60),
}

#: Account-scoped windows. Narrower on purpose — see module docstring for
#: why this table, not the IP one, is the control that actually matters
#: for the TOTP-guessing threat. A bucket absent here has no account
#: concept yet (``register``) or no account identifiable pre-verification
#: (``refresh``, ``reset_password``, ``confirm_email``) and relies on the
#: IP table alone.
_ACCOUNT_WINDOWS: Final[dict[str, _Window]] = {
    "login": _Window(max_attempts=5, seconds=300),
    "forgot_password": _Window(max_attempts=3, seconds=3600),
    "mfa_verify": _Window(max_attempts=5, seconds=300),
    "mfa_disable": _Window(max_attempts=5, seconds=300),
    "mfa_backup_regenerate": _Window(max_attempts=5, seconds=300),
    "change_password": _Window(max_attempts=5, seconds=300),
    # Keyed on the ADMIN caller's own id (`user_account_key`), not on the
    # target being unlocked — a compromised or over-eager admin account is
    # the threat this narrows against, independent of how many different
    # users' lockouts it is clearing.
    "admin_ratelimit_reset": _Window(max_attempts=15, seconds=60),
}

#: Bucket names a locked-out END USER can be identified by — the valid
#: values for the ``bucket`` field of an admin lockout-clear request (see
#: app/users.py::reset_user_rate_limit). Derived from ``_ACCOUNT_WINDOWS``
#: rather than hand-listed a second time, minus ``admin_ratelimit_reset``
#: itself: that entry protects the ADMIN action, not a credential path, so
#: it is not something the admin route can be asked to "clear" — there is
#: no user on the other end of it to unlock.
CLEARABLE_ACCOUNT_BUCKETS: Final[frozenset[str]] = frozenset(_ACCOUNT_WINDOWS) - {
    "admin_ratelimit_reset"
}

#: Requests refused, by bucket and which table refused them. The
#: operator-visible half of "how is a lockout observed" — see module
#: docstring.
RATE_LIMIT_REJECTIONS: Final[Counter] = Counter(
    "portal_rate_limit_rejections_total",
    "Requests refused by app.ratelimit, by bucket and scope",
    ["bucket", "scope"],
)

#: Per-process fallback: key -> (window_start_monotonic, count). Always
#: written to, regardless of whether the shared store is configured — see
#: module docstring "Fails closed, never open".
_LOCAL_COUNTS: dict[str, tuple[float, int]] = {}

#: Lazily constructed shared Valkey client, mirroring app.health_cache's
#: memoisation exactly (see that module's docstring for the reasoning) —
#: but its OWN module-level state, deliberately. Resetting the health
#: cache's client in a test must never reset this module's, and vice
#: versa; sharing one memoised client between two independently-reasoned
#: subsystems is how a fix to one becomes a silent behaviour change in
#: the other.
_cache_client: Any = None
_cache_init_attempted = False


async def _get_cache_client() -> Any | None:
    """Return the shared Valkey client, building it once, or None.

    None means "no shared store for this process": either CACHE_HOST is
    unset (the common case — see health_cache.log_startup_state) or the
    client library is unavailable. Both are treated identically by
    :func:`_bump`: fall back to the local counter alone.
    """
    global _cache_client, _cache_init_attempted

    if _cache_client is not None:
        return _cache_client
    if _cache_init_attempted:
        return None
    _cache_init_attempted = True

    host = str(current_app.config.get("CACHE_HOST", "") or "")
    if not host:
        log.warning("ratelimit_shared_store_disabled", reason="CACHE_HOST_not_configured")
        return None

    try:
        from penguin_dal.cache.valkey import AsyncValkeyCache, ValkeyConfig
    except ImportError:
        log.warning("ratelimit_shared_store_disabled", reason="valkey_module_unavailable")
        return None

    try:
        _cache_client = AsyncValkeyCache(
            ValkeyConfig(
                host=host,
                port=int(current_app.config.get("CACHE_PORT", 6379)),
                db=int(current_app.config.get("CACHE_DB", 0)),
                password=str(current_app.config.get("CACHE_PASS", "") or "") or None,
                ssl=bool(current_app.config.get("CACHE_SSL", False)),
                # No prefix here: this module prefixes its own keys
                # (`ratelimit:...`) explicitly below, so it never needs to
                # reach into the wrapper's private `_make_key` to compute
                # the same string a second time for the raw `.expire()`
                # call in `_bump`.
                prefix="",
            )
        )
    except ImportError:
        log.warning("ratelimit_shared_store_disabled", reason="valkey_client_library_missing")
        return None

    return _cache_client


def _local_bump(key: str, window_seconds: int) -> int:
    now = time.monotonic()
    started, count = _LOCAL_COUNTS.get(key, (now, 0))
    if now - started >= window_seconds:
        started, count = now, 0
    count += 1
    _LOCAL_COUNTS[key] = (started, count)
    return count


async def _bump(key: str, window_seconds: int) -> int:
    """Increment ``key``'s attempt count for this window; return the total.

    See module docstring — the local counter always runs, and the shared
    store's count (when reachable) is combined with ``max()``, never used
    alone. ``increment`` (INCRBY) is atomic; the ``EXPIRE`` immediately
    after the first hit is not part of the same round trip, so a crash in
    that narrow window could in principle leave a key with no TTL — the
    failure mode is a key that outlives its window (over-strict), never
    one that is missing its count (under-strict/fail-open).
    """
    local_count = _local_bump(key, window_seconds)

    try:
        client = await _get_cache_client()
    except Exception:
        log.warning("ratelimit_cache_client_init_failed")
        return local_count
    if client is None:
        return local_count

    try:
        shared_count = int(await client.increment(key))
        if shared_count == 1:
            await client.client.expire(key, window_seconds)
    except Exception:
        log.warning("ratelimit_cache_increment_failed")
        return local_count

    return max(local_count, shared_count)


def _hash_subject(value: str) -> str:
    """Digest an account-identifying value before it becomes a cache key.

    Never the raw value: an email address is exactly the PII this
    codebase's logging convention forbids reproducing (see
    app.auth._deliver_password_reset_token), and a cache key lands in
    Valkey's keyspace as visibly as a log line would.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _client_ip() -> str:
    return request.remote_addr or "unknown"


async def _refuse(bucket: str, window: _Window, scope: str) -> tuple[dict[str, Any], int]:
    RATE_LIMIT_REJECTIONS.labels(bucket=bucket, scope=scope).inc()
    log.warning("rate_limit_exceeded", bucket=bucket, scope=scope)
    return (
        {
            "error": "rate_limited",
            "message": "Too many attempts. Try again later.",
            "retry_after_seconds": window.seconds,
        },
        429,
    )


async def check(
    bucket: str, *, account_key: str | None = None
) -> tuple[dict[str, Any], int] | None:
    """Return a 429 refusal if ``bucket`` is over limit for this request, else None.

    The account-scoped check runs FIRST when ``account_key`` is given: the
    property this module exists to guarantee is that one targeted account
    is protected regardless of how many source IPs the attempts are
    spread across, so it must never be skipped merely because the IP
    bucket happened to already be exhausted by unrelated traffic sharing
    that address (a NAT gateway, a proxy).
    """
    if account_key and bucket in _ACCOUNT_WINDOWS:
        window = _ACCOUNT_WINDOWS[bucket]
        key = f"ratelimit:acct:{bucket}:{_hash_subject(account_key)}"
        if await _bump(key, window.seconds) > window.max_attempts:
            return await _refuse(bucket, window, "account")

    if bucket in _IP_WINDOWS:
        window = _IP_WINDOWS[bucket]
        key = f"ratelimit:ip:{bucket}:{_client_ip()}"
        if await _bump(key, window.seconds) > window.max_attempts:
            return await _refuse(bucket, window, "ip")

    return None


def rate_limited(
    bucket: str,
    account_key_fn: Callable[[], Awaitable[str | None]] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Any]]]:
    """Decorator: refuse with 429 before the view runs, once ``bucket`` is over limit.

    ``account_key_fn`` runs inside the same request/app context, so it may
    read the posted body (an email — see :func:`email_account_key`) or
    ``g.current_user`` (an authenticated caller — see
    :func:`user_account_key`, and place this decorator BELOW
    ``@auth_required`` so that context already exists) without this module
    importing either concern itself.
    """

    def decorator(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[Any]]:
        @wraps(f)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
            account_key = await account_key_fn() if account_key_fn else None
            refusal = await check(bucket, account_key=account_key)
            if refusal is not None:
                return refusal
            return await f(*args, **kwargs)

        return wrapped

    return decorator


async def email_account_key(field: str = "email") -> str | None:
    """The email the caller SUBMITTED, whether or not it resolves to a user.

    Keyed on the submitted value, never a verified one: an attacker never
    gets a verified account back from an unknown-email or wrong-password
    attempt, so keying on the row looked up afterwards would give every
    guess against a nonexistent account an unmetered, unlimited budget —
    the opposite of what this module exists to close. Normalised with the
    same ``.strip().lower()`` the login/register/forgot-password routes
    already apply before their own comparisons, so case/whitespace
    variants of one address share one counter rather than each getting a
    fresh budget.
    """
    data = await request.get_json(silent=True) or {}
    value = str(data.get(field, "")).strip().lower()
    return value or None


async def user_account_key() -> str | None:
    """The authenticated caller's own id, for routes behind ``@auth_required``.

    Not hashed like :func:`email_account_key`: a user id is an internal
    integer, not the PII this codebase's PII-tokenization convention
    protects (see backend-database.md) — it is already exactly what
    app/auth.py's own log lines (e.g. ``password_reset_token_undeliverable``)
    use to identify a subject without reproducing an email address.
    """
    from .middleware import get_current_user

    user = get_current_user()
    return f"user:{user['id']}" if user else None


def clear_local_state() -> None:
    """Empty the in-process fallback outright. Test isolation hook only.

    Without a per-test reset, every credential-accepting route sharing one
    pytest process (and, per Quart's test client, one apparent source IP)
    would accumulate attempts across unrelated tests and start refusing
    ones that were never meant to be anywhere near a limit — the same
    isolation gap app.health_cache's own module-level state has, addressed
    the same way (see tests/conftest.py's autouse fixtures).
    """
    _LOCAL_COUNTS.clear()


async def close_cache_client() -> None:
    """Release the shared Valkey connection, if one was ever opened."""
    global _cache_client, _cache_init_attempted
    if _cache_client is not None:
        try:
            await _cache_client.close()
        except Exception:
            log.warning("ratelimit_cache_close_failed")
    _cache_client = None
    _cache_init_attempted = False


def reset_cache_client_for_tests() -> None:
    """Forget the memoised client/init state. Test isolation hook only.

    Mirrors app.health_cache.reset_cache_client_for_tests exactly, for the
    same reason: does NOT close the client, since tests never open a real
    one (CACHE_HOST is unset under TestingConfig) — this only exists so a
    test that monkeypatches CACHE_HOST cannot leak a cached client into
    whatever runs next.
    """
    global _cache_client, _cache_init_attempted
    _cache_client = None
    _cache_init_attempted = False


async def rate_limit_reset(
    bucket: str, *, ip: str | None = None, account_key: str | None = None
) -> None:
    """Clear an in-progress lockout for one bucket/subject. Ops primitive.

    Not wired to an HTTP route yet — see module docstring "What this
    cannot see". Deletes from both tiers so a cleared lockout does not
    reappear from the local fallback on the next request this worker
    handles.
    """
    targets: list[str] = []
    if ip is not None:
        targets.append(f"ratelimit:ip:{bucket}:{ip}")
    if account_key is not None:
        targets.append(f"ratelimit:acct:{bucket}:{_hash_subject(account_key)}")

    for key in targets:
        _LOCAL_COUNTS.pop(key, None)

    try:
        client = await _get_cache_client()
    except Exception:
        client = None
    if client is None:
        return
    for key in targets:
        try:
            await client.delete(key)
        except Exception:
            log.warning("ratelimit_cache_delete_failed")
