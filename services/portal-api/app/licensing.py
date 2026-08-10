"""License tier resolution and entitlement gating for the portal.

Why this module exists
======================
``license.py`` used to answer every entitlement question with ``True``
whenever ``RELEASE_MODE`` was false::

    def is_feature_enabled(self, feature_name: str) -> bool:
        if not self.release_mode:
            return True

That is an environment-variable license bypass, which general.md forbids in
terms that leave no room ("Bypass is domain-based ONLY — never via env vars,
CLI args, or config flags"). Every deployment that had not set
``RELEASE_MODE=true`` — which is the default — unlocked Professional and
Enterprise features for free, and the only thing standing between a customer
and the whole feature set was one unset variable.

The bypass now lives in exactly one place: :func:`host_is_license_exempt`,
matching the hardcoded PenguinTech domain list. There is no other way to
turn gating off, and adding one is the failure this module was written to
end.

Two questions, deliberately separate
====================================
* :func:`resolve_tier` — *what tier is this deployment licensed for*. Answers
  ``community`` / ``professional`` / ``enterprise``, and callers compare the
  SPECIFIC tier via :func:`tier_satisfies`. A boolean "has feature" alone is
  not enough (general.md), because it cannot express "Enterprise only".
* :func:`is_feature_entitled` — *may this feature run here*. Domain bypass,
  then tier, then an explicit per-feature entitlement from the license
  payload.

Both delegate to ``penguin_licensing.LicenseClient`` rather than re-deriving
license state: it already caches for five minutes, falls back to the last
cached value across a license-server outage, drops the cache on a definitive
401/403/404, and answers ``community`` with no network call at all when no
``LICENSE_KEY`` is configured. Reimplementing that here is exactly the
duplicated-utility pattern backend.md forbids.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Awaitable, Callable, Final, ParamSpec, TypeVar

import structlog
from penguin_licensing.client import LicenseClient

# The domain matcher is IMPORTED, not reimplemented. It is the security
# boundary of the only bypass that exists, and it already handles the case a
# hand-written version gets wrong: `evilpenguincloud.io` must not match
# `.penguincloud.io`, while the bare apex `penguincloud.io` must. Two copies
# of that rule is how one of them quietly loosens.
#
# It is private upstream (`_is_bypass_domain`) because penguin-licensing
# only ever calls it from its own Flask-shaped decorator, which reads
# `flask.request` and therefore fails closed — never bypasses — inside a
# Quart app. penguin-libs issue filed to publish it alongside a
# framework-agnostic host parameter; until then the import is deliberate and
# `test_licensing_domain_bypass.py` pins the boundary semantics locally, so
# an upstream change that loosens them fails here rather than in production.
from penguin_licensing.decorators import _is_bypass_domain

log = structlog.get_logger()

P = ParamSpec("P")
R = TypeVar("R")

#: The three tiers, cumulative — each includes everything below it.
TIER_COMMUNITY: Final[str] = "community"
TIER_PROFESSIONAL: Final[str] = "professional"
TIER_ENTERPRISE: Final[str] = "enterprise"

#: Ordering used by :func:`tier_satisfies`. An unknown tier string resolves
#: to rank 0 (below community), never to a permissive default: "we do not
#: recognise this licence" must not read as "grant everything".
_TIER_RANK: Final[dict[str, int]] = {
    TIER_COMMUNITY: 1,
    TIER_PROFESSIONAL: 2,
    TIER_ENTERPRISE: 3,
}

#: Every tier, narrowest first. Published so the features endpoint and the
#: webui can render an upgrade path without re-deriving the ordering.
TIER_ORDER: Final[tuple[str, ...]] = (
    TIER_COMMUNITY,
    TIER_PROFESSIONAL,
    TIER_ENTERPRISE,
)

#: Minimum tier for each licensed feature.
#:
#: This is the MINT side of feature gating. The ``require_feature``
#: decorator is the enforce side, and a name it passes that is absent here
#: can never be granted — a gate nothing mints, which is how the dead
#: ``gough:*`` scopes would have 403'd every token.
#: ``tests/api/test_licensing_domain_bypass.py`` scans the app package for
#: every decorated feature name and asserts it appears below, so the two
#: sides cannot drift apart silently.
FEATURE_MIN_TIER: Final[dict[str, str]] = {
    # Professional
    "sso_integration": TIER_PROFESSIONAL,
    "delegated_admin": TIER_PROFESSIONAL,
    # Hosted WaddleAI API. Professional gets the hosted endpoint; bringing
    # your own provider key is the Enterprise step below.
    "waddleai_assist": TIER_PROFESSIONAL,
    # Enterprise
    "saml_sso": TIER_ENTERPRISE,
    "audit_export": TIER_ENTERPRISE,
    "external_kms": TIER_ENTERPRISE,
    "advanced_analytics": TIER_ENTERPRISE,
    "whitelabel": TIER_ENTERPRISE,
    # Direct Anthropic/OpenAI/Ollama credentials instead of the hosted API.
    "byok_ai": TIER_ENTERPRISE,
    # Tenants: 1 / 1 / unlimited, so more than one tenant is an Enterprise
    # STRUCTURE. `unlimited_hierarchy` was a second name for this same
    # concept and is gone: two names for one gate is how half the call
    # sites end up checking the one nobody mints. The numeric wall lives in
    # quotas.TierLimits.tenants; this entry is the capability half.
    "multi_tenant": TIER_ENTERPRISE,
}


@dataclass(slots=True, frozen=True)
class UpgradeRequired:
    """Why a gate refused, in the shape the webui renders.

    A bare ``403 {"error": "..."}`` tells an operator they cannot do
    something but not what would let them; both tiers are published so the
    UI can name the upgrade rather than inventing the mapping client-side.
    """

    error: str
    message: str
    feature: str
    required_tier: str
    current_tier: str


def host_is_license_exempt(host: str | None) -> bool:
    """True when a host is a PenguinTech-managed domain that skips gating.

    THE ONLY BYPASS. There is no environment variable, CLI flag or config
    key that reaches this decision, and there must never be one — see the
    module docstring for the bypass this replaced.
    """
    if not host:
        return False
    return _is_bypass_domain(host)


def current_host_is_license_exempt() -> bool:
    """True when the in-flight request targets an exempt domain.

    Outside a request there is no host to trust, so this fails closed. That
    matters for background work (keepalive, the flag refresh loop): a task
    with no request context must not inherit an exemption it cannot verify.
    """
    try:
        from quart import request

        host = request.host
    except (ImportError, RuntimeError):
        return False
    exempt = host_is_license_exempt(host)
    if exempt:
        log.debug("license_check_domain_bypass", host=host)
    return exempt


def tier_satisfies(current_tier: str, required_tier: str) -> bool:
    """True when ``current_tier`` meets or exceeds ``required_tier``.

    An unrecognised ``required_tier`` is treated as unreachable rather than
    as "no requirement": a typo in a gate must deny, not open.
    """
    return _TIER_RANK.get(current_tier, 0) >= _TIER_RANK.get(required_tier, 99)


_client: LicenseClient | None = None


def get_client() -> LicenseClient:
    """The process-wide license client, built lazily against this product.

    penguin-licensing ships its own ``get_license_client()`` singleton, but
    it hardcodes ``product="elder"`` — a portal validating as Elder gets
    Elder's entitlements, which is the wrong answer delivered confidently.
    """
    global _client
    if _client is None:
        _client = LicenseClient(
            license_key=os.getenv("LICENSE_KEY", ""),
            product=os.getenv("PRODUCT_NAME", "penguincloud"),
        )
    return _client


def reset_client() -> None:
    """Drop the cached client. Tests only — no runtime caller."""
    global _client
    _client = None


def resolve_tier_blocking() -> str:
    """Resolve the licensed tier, blocking on the license server if needed.

    Synchronous because ``LicenseClient`` is; call :func:`resolve_tier` from
    async code. With no ``LICENSE_KEY`` this performs no I/O at all — the
    client answers ``community`` directly — which is why the default
    development and test path never touches the network.
    """
    try:
        return get_client().validate().tier
    except Exception:
        # LicenseClient already swallows transport failures and falls back
        # to its cache; anything reaching here is unexpected. Degrade to the
        # narrowest tier rather than propagating a 500 out of a gate.
        log.warning("license_tier_resolution_failed", exc_info=True)
        return TIER_COMMUNITY


async def resolve_tier() -> str:
    """Resolve the licensed tier without blocking the event loop."""
    return await asyncio.to_thread(resolve_tier_blocking)


def is_feature_entitled_blocking(feature_name: str) -> bool:
    """Entitlement for one feature. NO domain bypass is applied here.

    Deliberately pure entitlement: the bypass is applied by the callers that
    have a request to read a host from
    (:func:`current_host_is_license_exempt`). Keeping them apart means a
    background caller cannot accidentally acquire a bypass, and means this
    function answers the same way regardless of who is asking.

    An unknown feature name denies. That is the "gate nothing mints" case —
    better a loud 403 on a name that is not in :data:`FEATURE_MIN_TIER` than
    a silent grant for a feature nobody declared a tier for.
    """
    required = FEATURE_MIN_TIER.get(feature_name)
    if required is None:
        log.warning("feature_gate_unknown_feature", feature=feature_name)
        return False

    client = get_client()
    try:
        if tier_satisfies(client.validate().tier, required):
            return True
        # A license may entitle a single feature below its nominal tier
        # (a trial, a contractual add-on). Tier is the gate; this is an
        # additional grant path, never a narrower one.
        return client.check_feature(feature_name)
    except Exception:
        log.warning(
            "feature_entitlement_check_failed", feature=feature_name, exc_info=True
        )
        return False


async def is_feature_entitled(feature_name: str) -> bool:
    """True when this deployment may run ``feature_name``.

    Domain exemption is evaluated FIRST and in the request context, so the
    blocking entitlement path is skipped entirely on a managed domain.
    """
    if current_host_is_license_exempt():
        return True
    return await asyncio.to_thread(is_feature_entitled_blocking, feature_name)


async def has_tier(required_tier: str) -> bool:
    """True when the deployment is licensed at ``required_tier`` or above."""
    if current_host_is_license_exempt():
        return True
    return tier_satisfies(await resolve_tier(), required_tier)


def upgrade_required(
    feature: str, required_tier: str, current_tier: str
) -> UpgradeRequired:
    """Build the 403 body a refused gate answers with."""
    return UpgradeRequired(
        error="feature_not_entitled",
        message=(
            f"'{feature}' requires the {required_tier} tier; "
            f"this deployment is licensed for {current_tier}."
        ),
        feature=feature,
        required_tier=required_tier,
        current_tier=current_tier,
    )


def require_tier(
    required_tier: str, feature: str = ""
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Any]]]:
    """Gate an async Quart view on a minimum license tier.

    The Quart-shaped counterpart to ``penguin_licensing.license_required``,
    which cannot be used directly here for two reasons: it reads
    ``flask.request`` for the domain bypass (a ``RuntimeError`` under Quart,
    so the bypass never fires), and it RAISES ``LicenseRequiredError``
    instead of answering an HTTP response — an uncaught exception out of a
    Quart view is a 500, not a 403 an operator can act on.
    """

    def decorator(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[Any]]:
        gate_name = feature or getattr(f, "__name__", required_tier)

        @wraps(f)
        async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
            if current_host_is_license_exempt():
                return await f(*args, **kwargs)
            current = await resolve_tier()
            if not tier_satisfies(current, required_tier):
                log.warning(
                    "license_tier_insufficient",
                    feature=gate_name,
                    required_tier=required_tier,
                    current_tier=current,
                )
                # asdict, not __dict__: UpgradeRequired is slots=True, so it
                # has no instance __dict__ at all — that attribute access
                # would be an AttributeError inside the deny path, turning
                # every refused gate into a 500.
                return asdict(upgrade_required(gate_name, required_tier, current)), 403
            return await f(*args, **kwargs)

        return decorated

    return decorator
