"""PostHog feature flags — general enablement, layered under license tiers.

Two different questions, and they are not interchangeable
========================================================
* **Flag** (this module) — *is this feature turned on at all*. Staged
  rollout, kill switch, experiment. Applies to EVERY feature, licensed or
  not, and defaults OFF for anything nobody has explicitly enabled.
* **License tier** (:mod:`app.licensing`) — *is this deployment entitled to
  it*. Layered on top; a flag that is on does not entitle an unlicensed
  deployment, and a license does not turn on a flag that is off.

A feature ships only when both agree. :func:`is_feature_available` is the
one place that conjunction is expressed, so no caller can accidentally
check one and believe it checked both.

Never crash, always degrade
===========================
general.md is explicit: "if the flag/license server is unreachable, fall
back to the last-known cached value (new/never-seen flags default OFF) —
never crash". Every path here honours that:

* no ``POSTHOG_KEY`` configured   → default (OFF), no network call at all;
* flag unknown to the server      → default (OFF), and NOT cached, because
                                    "never seen" is not "known false";
* server unreachable / errored    → last known value if one was ever
                                    observed, else default (OFF);
* anything else raising           → logged, default (OFF).

Caching is IN-PROCESS ONLY, and deliberately so
-----------------------------------------------
Same call as ``app/tenancy/resolver.py`` makes, for the same reason: a
shared Valkey tier is a drop-in change (penguin-dal ships
``penguin_dal.cache.AsyncValkeyCache``) but a half-present cache backend
that silently no-ops when its client library is absent is worse than an
honest in-process one.

Consequences an operator must know:

* each hypercorn worker holds its own copy, so a flag flip takes up to
  :data:`FLAG_CACHE_TTL_SECONDS` to be seen by every worker;
* the TTL bounds *staleness of a working server*. The last-known value has
  no expiry and is used only when a refresh fails — a flag server outage
  must not silently turn features off, which is what a TTL on the fallback
  would do.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Final

import structlog

log = structlog.get_logger()

#: Flag key namespace. general.md fixes the convention as
#: ``{product}.{feature-name}``; this is the ``{product}`` half.
FLAG_NAMESPACE: Final[str] = "penguincloud"

#: How long a successfully evaluated flag is reused before re-evaluating.
FLAG_CACHE_TTL_SECONDS: Final[float] = 30.0

#: Every flag this service evaluates, WITHOUT the namespace prefix.
#:
#: This is the declaration side. :func:`is_enabled` refuses a key that is
#: not listed, which is the same guard :data:`app.licensing.FEATURE_MIN_TIER`
#: applies to license gates and for the same reason: a flag nothing declares
#: is a flag nobody can find to turn on, and it would sit permanently OFF
#: while reading like a working toggle at the call site.
#:
#: Product enablement flags are named for the ``product_type`` they gate, so
#: ``PRODUCT_TYPES`` in ``app/models.py`` and this set can be compared
#: mechanically — see ``tests/api/test_flags.py``.
PRODUCT_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "gough",
        "nest",
        "tobogganing",
        "waddleai",
        "waddlebot",
        "elder",
        "skauswatch",
        "current",
    }
)

#: Non-product feature flags. Licensed features carry a flag too — the
#: license says "may", the flag says "is on", and general.md requires both.
FEATURE_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "sso_integration",
        "whitelabel",
        "multi_tenant",
        "delegated_admin",
        "saml_sso",
        "audit_export",
        "external_kms",
        "waddleai_assist",
        "advanced_analytics",
        "unlimited_hierarchy",
    }
)

#: Everything :func:`is_enabled` will evaluate.
KNOWN_FLAGS: Final[frozenset[str]] = PRODUCT_FLAGS | FEATURE_FLAGS


def flag_key(feature: str) -> str:
    """Namespace a feature name into its full PostHog flag key."""
    return f"{FLAG_NAMESPACE}.{feature}"


@dataclass(slots=True)
class _CachedFlag:
    """One evaluated flag value and when it was observed.

    ``fetched_at`` is a monotonic timestamp: wall-clock would let an NTP
    step make a fresh value look stale (or a stale one look fresh).
    """

    value: bool
    fetched_at: float


#: ``"{key}|{distinct_id}"`` → last observed value. Guarded by a lock
#: because ``asyncio.to_thread`` puts evaluations on worker threads.
_CACHE: dict[str, _CachedFlag] = {}
_CACHE_LOCK: Final[threading.Lock] = threading.Lock()

_client: Any | None = None
_client_built = False
_CLIENT_LOCK: Final[threading.Lock] = threading.Lock()


def get_client() -> Any | None:
    """The process-wide PostHog client, or None when unconfigured.

    None is a first-class answer, not an error: a deployment with no
    ``POSTHOG_KEY`` has no flag server, and every flag must then resolve to
    its default without a single network call. Returning None here is what
    keeps the test suite and offline development off the wire entirely.

    Built under a lock and latched with ``_client_built`` so concurrent
    first requests neither race to construct rival clients nor retry a
    failed construction on every call.
    """
    global _client, _client_built
    if _client_built:
        return _client

    with _CLIENT_LOCK:
        if _client_built:
            return _client
        _client_built = True

        api_key = os.getenv("POSTHOG_KEY", "")
        if not api_key:
            log.info("posthog_not_configured", detail="all flags resolve to default")
            _client = None
            return None

        try:
            from posthog import Posthog

            # posthog ships py.typed but leaves Posthog.__init__ entirely
            # unannotated, so --strict rejects the call itself. Narrow,
            # coded, single-line suppression per mypy.ini's own instruction
            # ("if a third-party library's own stubs genuinely force a
            # suppression, use a narrow, single-line, coded and commented
            # suppression at the offending line instead of a config-level
            # exemption"). Scope is this constructor call only; every value
            # passed to it is annotated on this side.
            _client = Posthog(  # type: ignore[no-untyped-call]
                project_api_key=api_key,
                host=os.getenv("POSTHOG_HOST", "https://license.penguintech.io"),
                # A personal API key is what lets the SDK pull flag
                # DEFINITIONS and evaluate locally, turning a per-request
                # /decide round trip into an in-process computation. Absent,
                # the SDK still works — it just evaluates remotely — so this
                # is an optimisation, never a requirement.
                personal_api_key=os.getenv("POSTHOG_PERSONAL_API_KEY") or None,
                # Bounded so a hung flag server cannot hold a worker thread.
                feature_flags_request_timeout_seconds=3,
                timeout=5,
                # No product analytics from the portal: this integration is
                # for flag evaluation, and capturing events would put user
                # activity on a third-party pipeline nobody asked for.
                disabled=False,
                disable_geoip=True,
            )
        except Exception:
            log.warning("posthog_client_init_failed", exc_info=True)
            _client = None

    return _client


def reset_client() -> None:
    """Drop the client and the flag cache. Tests only — no runtime caller."""
    global _client, _client_built
    with _CLIENT_LOCK:
        _client = None
        _client_built = False
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_read(cache_key: str) -> _CachedFlag | None:
    with _CACHE_LOCK:
        return _CACHE.get(cache_key)


def _cache_write(cache_key: str, value: bool) -> None:
    with _CACHE_LOCK:
        _CACHE[cache_key] = _CachedFlag(value=value, fetched_at=time.monotonic())


def is_enabled_blocking(
    feature: str, distinct_id: str, default: bool = False
) -> bool:
    """Evaluate one flag, blocking. Call :func:`is_enabled` from async code.

    ``default`` exists for callers that have a considered reason to differ;
    it is False everywhere today and a new flag must not be given a True
    default just to skip the rollout step.
    """
    if feature not in KNOWN_FLAGS:
        # Same failure class as an unminted scope: the call site reads like
        # a working toggle, the flag exists nowhere, and it is off forever.
        log.warning("flag_not_declared", feature=feature)
        return default

    key = flag_key(feature)
    cache_key = f"{key}|{distinct_id}"

    cached = _cache_read(cache_key)
    if cached is not None and (time.monotonic() - cached.fetched_at) < (
        FLAG_CACHE_TTL_SECONDS
    ):
        return cached.value

    client = get_client()
    if client is None:
        return default

    try:
        # only_evaluate_locally is left False on purpose: the SDK computes
        # locally when it has the definitions and falls back to the decide
        # endpoint when it cannot, which is strictly better than forcing
        # local-only (silently None, i.e. OFF, for any flag whose
        # conditions need server-side data).
        result = client.feature_enabled(key, distinct_id)
    except Exception:
        # Unreachable or erroring server: last known value wins, and it has
        # no expiry. Letting the TTL apply here would turn an outage into a
        # silent feature-wide kill switch.
        log.warning("flag_evaluation_failed", flag=key, exc_info=True)
        if cached is not None:
            return cached.value
        return default

    if result is None:
        # PostHog answers None for a flag it does not know. Deliberately NOT
        # cached: "never seen" is not "known false", and caching it would
        # delay a newly created flag by the TTL for no benefit.
        return default

    value = bool(result)
    _cache_write(cache_key, value)
    return value


async def is_enabled(feature: str, distinct_id: str, default: bool = False) -> bool:
    """Evaluate one flag without blocking the event loop."""
    return await asyncio.to_thread(is_enabled_blocking, feature, distinct_id, default)


async def evaluate_all(distinct_id: str) -> dict[str, bool]:
    """Evaluate every declared flag for one principal.

    One ``to_thread`` hop for the whole set rather than one per flag: the
    SDK's local evaluation is a dict lookup, and the remote path shares a
    connection pool, so fanning out gains nothing and costs a thread each.
    """

    def _all() -> dict[str, bool]:
        return {
            feature: is_enabled_blocking(feature, distinct_id)
            for feature in sorted(KNOWN_FLAGS)
        }

    return await asyncio.to_thread(_all)


async def is_feature_available(feature: str, distinct_id: str) -> bool:
    """True only when the flag is ON **and** the license entitles it.

    The conjunction lives here so no caller can check one and believe it
    checked both. An unlicensed feature name (absent from
    ``FEATURE_MIN_TIER``) is unentitled, so this returns False for it —
    a flag alone never unlocks a licensed capability.
    """
    from . import licensing

    if not await is_enabled(feature, distinct_id):
        return False
    if feature not in licensing.FEATURE_MIN_TIER:
        # Not a licensed feature at all: the flag is the whole gate.
        return True
    return await licensing.is_feature_entitled(feature)
