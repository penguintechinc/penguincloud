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
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

import structlog
from penguin_licensing.client import LicenseClient

log = structlog.get_logger()

#: The PenguinTech-managed domains that skip licence gating, from
#: penguintech.md's License Bypass Domains.
#:
#: Implemented HERE rather than imported. This module used to do::
#:
#:     from penguin_licensing.decorators import _is_bypass_domain
#:
#: which worked only because an editable ~/code/penguin-libs checkout was on
#: the path. The RELEASED penguin-licensing==0.1.0 that requirements.txt
#: hash-pins exports no such name — nor any bypass logic at all — so the
#: container, which installs with `uv pip install --require-hashes`, failed
#: at import. The service could not start from its own declared
#: dependencies, and the failure was in the one code path that decides
#: whether the paywall applies.
#:
#: The leading underscore was upstream saying "this may vanish without
#: notice". It had already vanished. A local shim with an upstream-
#: compatible signature is this project's stated mitigation: never block a
#: phase on a libs release.
#:
#: NOT widened to the product ``.app`` domains penguintech.md also lists.
#: Two reasons, both deliberate: widening a security boundary while fixing
#: an import is how a fix becomes a regression, and dev mode's domain set
#: (devmode.DEV_MODE_APP_DOMAINS) is wider precisely so `--dev` can be
#: proven to unlock on its own rather than riding this bypass. Widening is
#: a policy decision — see the report.
#:
#: penguin-libs issue for a PUBLIC, framework-agnostic matcher:
#: https://github.com/penguintechinc/penguin-libs/issues/77
LICENSE_BYPASS_DOMAINS: Final[tuple[str, ...]] = (
    ".penguincloud.io",
    ".penguintech.cloud",
    ".localhost.local",
)


def _is_bypass_domain(host: str) -> bool:
    """True when ``host`` is a PenguinTech-managed domain that skips gating.

    Signature and semantics match the upstream private helper this replaced,
    so adopting a public upstream API later is a one-line swap.

    Matches on a DOT BOUNDARY only. ``evilpenguincloud.io`` must not match
    ``.penguincloud.io`` while the bare apex ``penguincloud.io`` must — a
    plain ``endswith`` against the apex would grant a free licence to anyone
    who registered a domain ending in those characters.
    """
    bare = host.split(":")[0].lower()
    return any(
        bare == domain.lstrip(".") or bare.endswith(domain) for domain in LICENSE_BYPASS_DOMAINS
    )


#: Environment keys naming the host this deployment is configured to answer
#: on, in precedence order. ``BASE_URL`` is the key devops-kubernetes.md
#: already sets per environment; ``SERVER_NAME`` is the ASGI/WSGI-native
#: spelling, accepted so a deployment that sets only that one still resolves.
#:
#: THIS IS CONFIGURATION, NOT A REQUEST HEADER, and the distinction is the
#: whole security property — see :func:`configured_host`.
HOST_CONFIG_KEYS: Final[tuple[str, ...]] = ("BASE_URL", "SERVER_NAME")

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
    # Reading the audit trail is the Enterprise product. Audit rows are
    # WRITTEN on every tier — that is a security property, not a feature,
    # and gating it would be a locked module.
    "audit_logs": TIER_ENTERPRISE,
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

#: Declared in the licensing contract above, but NOT BUILT YET in this
#: portal — so there is no call site to gate, and inventing one would be a
#: fake gate on a feature that does not exist.
#:
#: This set is the honest half of the declaration. ``FEATURE_MIN_TIER`` is
#: the commercial contract and every entry belongs in it, but "declared"
#: without "enforced" is the failure this project has already shipped twice
#: (the dead ``gough:*`` scopes, the unconsumed
#: ``SCOPE_MANAGE_DESCENDANTS``): a name that reads like a gate, is checked
#: nowhere, and nobody notices until a customer gets something they did not
#: buy.
#:
#: ``TestGateAndMintMeet`` asserts the CONVERSE of the usual scan — every
#: key in ``FEATURE_MIN_TIER`` is either gated at a real call site or listed
#: here. Building one of these therefore fails a test until its gate lands,
#: and adding a new licensed feature without gating it fails immediately.
#:
#: Removing a name from this set is the last step of implementing it, not
#: the first — and forgetting that step is not a theoretical risk.
#: ``audit_export`` sat here while ``GET /api/v1/audit/export`` was fully
#: built and reachable behind nothing but a tenant scope: membership of this
#: set EXEMPTS a feature from the mint-vs-enforce guard, so a built feature
#: parked here is invisible to the very check meant to catch it. The
#: converse assertion — no implementation may exist for anything listed here
#: — is what closes that, and it is the load-bearing half.
NOT_YET_IMPLEMENTED: Final[frozenset[str]] = frozenset(
    {
        "waddleai_assist",
        "saml_sso",
        "external_kms",
        "advanced_analytics",
        "whitelabel",
        "byok_ai",
    }
)


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


def _hostname(raw: str) -> str:
    """Reduce a configured URL or ``host[:port]`` to a bare lowercase host."""
    candidate = raw.strip()
    if not candidate:
        return ""
    # urlsplit puts a bare "portal.example.com" in .path, not .netloc, so a
    # scheme-relative prefix is added when none is present.
    if "//" not in candidate:
        candidate = f"//{candidate}"
    try:
        return (urlsplit(candidate).hostname or "").lower()
    except ValueError:
        return ""


def configured_host() -> str:
    """The host this deployment is CONFIGURED to answer on. Never a header.

    This function is the reason the paywall is not one ``curl -H 'Host:
    …'`` away from being disabled.

    It used to read ``request.host``. In a licensing threat model the
    adversary IS the operator: they control their own ingress and can reach
    the pod directly, so a ``Host`` header is a value the party being
    charged supplies about themselves. Any self-hosted deployment could send
    ``Host: x.penguincloud.io`` and take the domain bypass — every licensed
    feature entitled, every tier gate passed, the Enterprise limits table
    resolved — with nothing in the request log to distinguish it from a
    legitimate managed deployment.

    Configuration is not attacker-controlled in the same way: ``BASE_URL``
    is set by whoever deploys the chart, is visible in the manifest, and
    cannot be varied per request. Reading it here means the bypass answers
    the same way for every caller, which is what makes it auditable.

    Empty when nothing is configured, which fails closed — an unconfigured
    deployment is not exempt.
    """
    for key in HOST_CONFIG_KEYS:
        host = _hostname(os.getenv(key, ""))
        if host:
            return host
    return ""


def current_host_is_license_exempt() -> bool:
    """True when this deployment is configured on an exempt domain.

    Deliberately NOT request-scoped. It answers identically inside a
    request, in a background task and at startup, because the answer comes
    from configuration rather than from whoever happens to be calling. A
    request-scoped bypass is one a caller can ask for.
    """
    host = configured_host()
    if not host:
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
        log.warning("feature_entitlement_check_failed", feature=feature_name, exc_info=True)
        return False


async def dev_mode_entitles() -> bool:
    """True when ``--dev`` is active and therefore widens entitlement.

    This is the ONE place dev mode reaches the licensing decision, and it
    has to exist for the flag to mean anything at all. Before it, nothing
    consulted :func:`app.devmode.is_active`: ``--dev`` appeared to work only
    because dev mode's domain condition happens to call the same
    ``host_is_license_exempt`` the licence bypass does, so on every domain
    where dev mode COULD activate, everything was already unlocked without
    it — and therefore without the single-user cap, the WARN log or the
    banner that are the whole point of the mode.

    Imported inside the function because :mod:`app.devmode` imports this
    module for the domain matcher; a module-level import would be circular.
    """
    from . import devmode

    return await devmode.is_active()


async def is_feature_entitled(feature_name: str) -> bool:
    """True when this deployment may run ``feature_name``.

    Three independent grants, checked cheapest first: the configured-domain
    exemption, active dev mode, then the licence itself.
    """
    if current_host_is_license_exempt():
        return True
    if await dev_mode_entitles():
        return True
    return await asyncio.to_thread(is_feature_entitled_blocking, feature_name)


def upgrade_required(feature: str, required_tier: str, current_tier: str) -> UpgradeRequired:
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
