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
import dataclasses
import os
import threading
import time
from collections import OrderedDict
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

#: Product types that intentionally carry NO enablement flag, and are
#: therefore never refused by :func:`product_gate_refusal`.
#:
#: ``PRODUCT_TYPES`` is a legacy-inclusive list: it still names products that
#: penguintech.md records as retired or absorbed into another product
#: (``marchproxy`` → Envoy/WaddleAI, ``articdbm`` → Nest, ``darwin`` →
#: SkausWatch, ``icecharts`` → Elder, ``killkrill`` → SigNoz), products with
#: no portal module of their own (``squawk`` is a page inside Tobogganing;
#: ``license_server``, ``cerberus``, ``waddleperf``, ``iceshelves``), the
#: internal ``admin`` type, and the ``generic`` escape hatch that exists
#: precisely for a product with no dedicated module.
#:
#: Declaring them here rather than letting them fall through unnamed is the
#: point: ``tests/api/test_flags.py`` asserts every ``PRODUCT_TYPES`` value
#: is either flagged or listed here, so adding a product type without
#: deciding which it is fails a test rather than shipping an ungated module.
UNFLAGGED_PRODUCT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "generic",
        "admin",
        "marchproxy",
        "squawk",
        "license_server",
        "articdbm",
        "cerberus",
        "waddleperf",
        "iceshelves",
        "icecharts",
        "killkrill",
        "darwin",
    }
)

#: Non-product feature flags. Licensed features carry a flag too — the
#: license says "may", the flag says "is on", and general.md requires both.
FEATURE_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "sso_integration",
        "delegated_admin",
        # `waddleai` (the product-connection flag) is a PRODUCT flag and a
        # tenant may register that product on any tier. This is the
        # portal-side hosted assist, which is the licensed capability. One
        # key must never mean two things — the two sets are asserted
        # disjoint in tests/api/test_flags.py.
        "waddleai_assist",
        "byok_ai",
        "saml_sso",
        "audit_export",
        "external_kms",
        "advanced_analytics",
        "whitelabel",
        "multi_tenant",
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


#: Hard ceiling on cache entries. The cache is keyed by flag AND principal,
#: so its size grows with the number of distinct users the process has
#: served — unbounded, in a long-lived worker, for a dict nothing ever
#: evicts. At |KNOWN_FLAGS| ≈ 20 this holds roughly the last 400 users,
#: which is a working set, not a leak.
FLAG_CACHE_MAX_ENTRIES: Final[int] = 8192

#: ``"{key}|{distinct_id}"`` → last observed value, least-recently-written
#: first so the bound above evicts the coldest entry. Guarded by a lock
#: because ``asyncio.to_thread`` puts evaluations on worker threads.
_CACHE: "OrderedDict[str, _CachedFlag]" = OrderedDict()
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
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > FLAG_CACHE_MAX_ENTRIES:
            # Evicting the coldest entry costs at most one re-evaluation.
            # Evicting nothing costs the worker's memory, without limit.
            _CACHE.popitem(last=False)


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


def evaluate_all_blocking(distinct_id: str) -> dict[str, bool]:
    """Evaluate every declared flag for one principal, blocking.

    One bulk call, not |KNOWN_FLAGS| single ones. The per-flag loop this
    replaces made ~20 sequential evaluations inside a single ``to_thread``
    hop; whenever the SDK could not evaluate locally that was 20 sequential
    HTTP round trips holding one worker thread, on a request the UI makes on
    every page load. ``get_all_flags`` answers the same question in one.

    The fallback is the old loop, so a flag server that cannot answer in
    bulk still works and every degradation rule in this module still
    applies.
    """
    client = get_client()
    if client is None:
        return {feature: False for feature in sorted(KNOWN_FLAGS)}

    try:
        bulk = client.get_all_flags(distinct_id)
    except Exception:
        log.warning("flag_bulk_evaluation_failed", exc_info=True)
        bulk = None

    if not isinstance(bulk, dict):
        # No bulk answer: fall back to the per-flag path, which keeps the
        # cache and the last-known-value rules intact.
        return {
            feature: is_enabled_blocking(feature, distinct_id)
            for feature in sorted(KNOWN_FLAGS)
        }

    resolved: dict[str, bool] = {}
    for feature in sorted(KNOWN_FLAGS):
        raw = bulk.get(flag_key(feature))
        if raw is None:
            # Unknown to the server. Same rule as the single-flag path:
            # "never seen" is not "known false", so it is not cached, and a
            # previously observed value still wins over the default.
            cached = _cache_read(f"{flag_key(feature)}|{distinct_id}")
            resolved[feature] = cached.value if cached is not None else False
            continue
        value = bool(raw)
        _cache_write(f"{flag_key(feature)}|{distinct_id}", value)
        resolved[feature] = value
    return resolved


async def evaluate_all(distinct_id: str) -> dict[str, bool]:
    """Evaluate every declared flag for one principal, off the event loop."""
    return await asyncio.to_thread(evaluate_all_blocking, distinct_id)


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


def feature_disabled_body(feature: str) -> dict[str, Any]:
    """The 403 body for a feature whose FLAG is off on this deployment.

    Distinct from the licensing refusal on purpose. "Not enabled here" and
    "not included in your licence" have different remedies — an operator
    flips the first themselves and buys the second — and a single body
    telling them to upgrade when the real answer is a rollout toggle sends
    them to sales for something they already own.
    """
    return {
        "error": "feature_disabled",
        "message": (
            f"'{feature}' is not enabled on this deployment. "
            f"Enable the {flag_key(feature)} feature flag to turn it on."
        ),
        "feature": feature,
        "flag": flag_key(feature),
    }


async def product_gate_refusal(
    product_type: str, distinct_id: str
) -> tuple[dict[str, Any], int] | None:
    """Refuse a product-backed request when its module is not available.

    THE SERVER-SIDE HALF OF THE CONJUNCTION. ``is_feature_available`` was
    documented as "the one place the conjunction lives" while having no
    production caller at all: the flags were computed, published to the
    browser by ``GET /api/v1/features``, and enforced only by
    ``featureGates.ts`` — which decides what to render, not what the API
    will do. Any caller holding a token could register a connection to a
    disabled product, or proxy to it, by not using the UI.

    Returns ``None`` when the product may be used, else a refusal body and
    status. Licensed-capability refusals keep the licensing shape and 403;
    a flag-off refusal says so plainly.
    """
    from . import licensing

    if product_type in UNFLAGGED_PRODUCT_TYPES:
        # Not a flagged module — see UNFLAGGED_PRODUCT_TYPES. Refusing here
        # would take the `generic` escape hatch away from every deployment
        # that has not created a flag nobody documented.
        return None

    if await is_feature_available(product_type, distinct_id):
        return None

    if product_type in licensing.FEATURE_MIN_TIER and await is_enabled(
        product_type, distinct_id
    ):
        # The flag is on; the licence is what refused.
        required = licensing.FEATURE_MIN_TIER[product_type]
        current = await licensing.resolve_tier()
        return (
            dataclasses.asdict(
                licensing.upgrade_required(product_type, required, current)
            ),
            403,
        )

    log.info("product_module_disabled", product_type=product_type)
    return feature_disabled_body(product_type), 403
