"""Scale and structure limits — the paywall, under the new tier model.

"The paywall gates scale and structure, not features"
=====================================================
Every tier gets every module with full features. A single free user
experiences the whole product; what the licence buys is room to grow —
more tenants, more teams, more delegated admins — plus a short premium
list (SSO, whitelabel, KMS, audit, BYOK AI) handled by
:mod:`app.licensing`.

Nothing here may ever produce a locked or crippled module. If a change to
this file would make a *capability* unavailable rather than a *count*
unavailable, it belongs in ``FEATURE_MIN_TIER``, not here.

Two rules that shape the code
=============================
1. **Enforcement is a hard block.** The over-limit action — the 2nd team,
   the 11th tenant admin, the 2nd tenant below Enterprise, the 1001st
   object on Free — is REFUSED, with an upgrade prompt. Never a soft
   warning, never a silent cap that quietly drops the write. The refusal
   carries ``required_tier`` so the UI can name the upgrade rather than
   telling the operator "no".
2. **The numbers are defaults, not constants.** A licence may raise or
   lower any of them per deployment, so every limit is read from the
   licence payload with the table below as a fallback. Hardcoding them
   would make a negotiated contract unimplementable without a redeploy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields
from typing import Any, Final

import structlog
from penguin_dal.quart_ext import get_db

from . import licensing

log = structlog.get_logger()

#: Sentinel for "no limit". -1 rather than None or a huge int so it survives
#: a JSON round trip through the licence payload and compares uniformly.
UNLIMITED: Final[int] = -1


@dataclass(slots=True, frozen=True)
class TierLimits:
    """Every numeric wall for one tier.

    Field names are the dimension names used throughout this module and in
    the ``/api/v1/features`` response, so a limit cannot be published under
    one name and enforced under another.
    """

    #: Platform-role admins (``users.role == "admin"``), deployment-wide.
    global_admins: int
    #: Delegated tenant admins (``tenant_members.role == "admin"``) per
    #: tenant. The tenant OWNER is not one of these — every tenant has an
    #: owner by construction, so counting them would make Free's limit of 0
    #: unsatisfiable and no tenant could exist at all.
    tenant_admins: int
    #: Tenants in the deployment.
    tenants: int
    #: Teams in the deployment.
    teams: int
    #: Managed objects. See :func:`count_objects` for what counts and why.
    objects: int


#: Fallbacks, straight from the commercial table. Overridden per deployment
#: by the licence payload — see :func:`resolve_limits`.
DEFAULT_TIER_LIMITS: Final[dict[str, TierLimits]] = {
    licensing.TIER_COMMUNITY: TierLimits(
        global_admins=1,
        tenant_admins=0,
        tenants=1,
        teams=1,
        objects=1000,
    ),
    licensing.TIER_PROFESSIONAL: TierLimits(
        global_admins=1,
        tenant_admins=10,
        tenants=1,
        teams=UNLIMITED,
        objects=UNLIMITED,
    ),
    licensing.TIER_ENTERPRISE: TierLimits(
        global_admins=UNLIMITED,
        tenant_admins=UNLIMITED,
        tenants=UNLIMITED,
        teams=UNLIMITED,
        objects=UNLIMITED,
    ),
}

#: Dimension -> the key the licence payload publishes an override under.
LICENSE_LIMIT_KEYS: Final[dict[str, str]] = {
    "global_admins": "max_global_admins",
    "tenant_admins": "max_tenant_admins",
    "tenants": "max_tenants",
    "teams": "max_teams",
    "objects": "max_objects",
}

#: Human wording for each dimension, used in the refusal message. Kept beside
#: the limits so a new dimension cannot ship with a blank error.
DIMENSION_LABELS: Final[dict[str, str]] = {
    "global_admins": "global administrators",
    "tenant_admins": "delegated tenant administrators",
    "tenants": "tenants",
    "teams": "teams",
    "objects": "managed objects",
}

#: Dimension names, derived from the dataclass so the three tables above
#: cannot drift from it silently (tests assert all four agree).
DIMENSIONS: Final[tuple[str, ...]] = tuple(
    field.name for field in fields(TierLimits)
)


def _coerce_limit(raw: Any) -> int | None:
    """Narrow a licence-payload value to a limit, or None if unusable.

    A malformed override is IGNORED in favour of the tier default rather
    than being treated as zero or as unlimited. Both of those readings are
    wrong in a way the operator cannot see: zero locks the deployment out
    of its own product, unlimited hands away the paywall.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= UNLIMITED else None
    return None


def limits_for_tier(
    tier: str, payload_limits: dict[str, Any] | None = None
) -> TierLimits:
    """Resolve the effective limits for a tier, applying payload overrides.

    An unrecognised tier resolves to the NARROWEST table entry, never the
    widest: "we do not know what this licence is" must not read as
    "unlimited everything".
    """
    base = DEFAULT_TIER_LIMITS.get(tier, DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY])
    if not payload_limits:
        return base

    overrides: dict[str, int] = {}
    for dimension, key in LICENSE_LIMIT_KEYS.items():
        value = _coerce_limit(payload_limits.get(key))
        if value is not None:
            overrides[dimension] = value

    if not overrides:
        return base
    return TierLimits(
        **{
            dimension: overrides.get(dimension, getattr(base, dimension))
            for dimension in DIMENSIONS
        }
    )


def resolve_limits_blocking() -> TierLimits:
    """The effective limits for this deployment, blocking."""
    try:
        info = licensing.get_client().validate()
        return limits_for_tier(info.tier, dict(info.limits))
    except Exception:
        log.warning("quota_limit_resolution_failed", exc_info=True)
        return DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY]


async def resolve_limits() -> TierLimits:
    """The effective limits for this deployment, off the event loop.

    A PenguinTech-managed domain gets the Enterprise table for the same
    reason it skips entitlement checks: it is billed separately, and the
    bypass must be domain-based only (general.md).

    Active ``--dev`` gets it too — "all premium features unlocked" includes
    the structures the paywall gates, or a single evaluating user could not
    try multi-tenancy at all. Its own single-user cap is unaffected: that
    cap lives in :mod:`app.devmode` and is not one of these dimensions.
    """
    if licensing.current_host_is_license_exempt():
        return DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
    if await licensing.dev_mode_entitles():
        return DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
    return await asyncio.to_thread(resolve_limits_blocking)


def minimum_tier_for(dimension: str, wanted: int) -> str | None:
    """The narrowest DEFAULT tier whose limit admits ``wanted``, else None.

    Used only to name an upgrade in a refusal. It reads the default table
    rather than the deployment's overridden limits on purpose: telling an
    operator "Enterprise allows this" must reflect what the product sells,
    not what their own licence happens to have been tuned to.
    """
    for tier in licensing.TIER_ORDER:
        limit = getattr(DEFAULT_TIER_LIMITS[tier], dimension, 0)
        if limit == UNLIMITED or wanted <= limit:
            return tier
    return None


async def count_tenants() -> int:
    """Tenants in the deployment."""
    db = get_db()
    return int(await db(db.tenants.id > 0).count())


async def count_teams() -> int:
    """Teams in the deployment."""
    db = get_db()
    return int(await db(db.teams.id > 0).count())


async def count_global_admins() -> int:
    """Users holding the platform ``admin`` role."""
    db = get_db()
    return int(await db(db.users.role == "admin").count())


async def count_tenant_admins() -> int:
    """Delegated tenant admins across the DEPLOYMENT.

    Deployment-wide, like every other dimension in the table. It was counted
    per-tenant, which reads the same only because tenants are themselves
    capped at 1 below Enterprise. The moment a licence raises ``max_tenants``
    on its own — a supported override, since every limit is
    licence-configurable — a per-tenant count sells 10×N delegated admins
    under a limit published as 10. The two dimensions must not silently
    multiply.

    ``owner`` is deliberately excluded. Every tenant has exactly one by
    construction, so counting owners would make the Free tier's limit of 0
    unsatisfiable — no tenant could be created at all, which is a locked
    module rather than a scale wall and is exactly what the tier model
    forbids. A tenant admin is the DELEGATED authority the licence sells.
    """
    db = get_db()
    return int(await db(db.tenant_members.role == "admin").count())


async def count_objects() -> int:
    """Managed objects, for the Free tier's 1,000 object quota.

    **An object is one product connection.** "Object" is not defined
    anywhere for this product, so this is a decision, recorded here and
    flagged for confirmation rather than assumed:

    * A product connection is the portal's unit of managed inventory — one
      registered product endpoint. It is the only operator-created resource
      that grows unboundedly with actual use, which is what a 1,000-item
      quota is shaped for.
    * Tenants, teams and admins are NOT counted. Each already has its own
      explicit wall in the table above, so folding them in would gate one
      action twice and, worse, make the object quota unreachable in
      practice: a Free deployment is capped at 1 tenant and 1 team, so
      those can contribute at most 2 toward 1,000.
    * Users are NOT counted. Non-admin members are unlimited at every tier
      by design, and a quota that counted them would silently reintroduce
      the user cap the tier model deliberately removes.

    **This wall is unlikely ever to bind on this product, and that is said
    here so nobody mistakes it for protection.** A Free deployment is capped
    at 1 tenant and 1 team, and a single tenant realistically registers a
    handful of product connections — not a thousand. The walls that actually
    bite here are ``tenants``, ``teams`` and the two admin dimensions. This
    one is enforced because the commercial table names it and because a
    deployment CAN in principle register connections without limit inside
    its one tenant; it is not load-bearing, and no design should assume it
    is doing work it is not. A gate that exists but never fires is fine when
    it is documented as such and dangerous when it is mistaken for a
    control.
    """
    db = get_db()
    return int(await db(db.product_connections.id > 0).count())


#: The status every scale wall answers with. 402 Payment Required rather
#: than 403: this is not an authorization decision.
SCALE_REFUSAL_STATUS: Final[int] = 402


class QuotaExceeded(RuntimeError):
    """Raised by the model-layer backstop when a limit would be breached."""


#: Dimension -> the counter that measures it, for the model-layer backstop.
_BACKSTOP_COUNTERS: Final[dict[str, str]] = {
    "tenants": "count_tenants",
    "teams": "count_teams",
    "tenant_admins": "count_tenant_admins",
}


async def assert_within(dimension: str) -> None:
    """Backstop beneath every write that consumes ``dimension``.

    The routes above answer a clean 402 with an upgrade prompt; this exists
    because a limit enforced at only *some* call sites is not a limit. It is
    the same pattern ``devmode.assert_user_creation_allowed`` already
    applies to the single-user cap, and it is here because this branch
    shipped exactly that gap: ``POST /api/v1/auth/register`` created a
    personal team through ``models.create_team`` with nothing metering it,
    so every self-service registration walked past the Free tier's limit of
    one team and nothing raised, logged or failed.

    A future route, a seed script or a background job that inserts without
    asking now gets an exception rather than a silent breach. An exception
    out of a view is a 500, which is worse UX than a 402 and much better
    than a quota that is not enforced — the loud failure is the point.
    """
    counter = _BACKSTOP_COUNTERS.get(dimension)
    if counter is None:  # pragma: no cover - programming error
        raise KeyError(f"no backstop counter for dimension {dimension!r}")

    limits = await resolve_limits()
    limit = getattr(limits, dimension)
    if limit == UNLIMITED:
        return

    # Resolved through the module namespace, not captured at import, so a
    # test (or a future decorator) that replaces a counter is honoured here
    # exactly as it is at the routes.
    counter_fn: Any = globals()[counter]
    current = int(await counter_fn())
    if current + 1 > limit:
        log.error(
            "quota_backstop_refused",
            dimension=dimension,
            current=current,
            limit=limit,
            detail="a write path reached the model layer without metering",
        )
        raise QuotaExceeded(
            f"this deployment is licensed for {limit} "
            f"{DIMENSION_LABELS.get(dimension, dimension)}"
        )


def scale_refusal_body(
    *,
    error: str,
    message: str,
    dimension: str,
    limit: int,
    current: int,
    current_tier: str,
    required_tier: str | None,
) -> dict[str, Any]:
    """The ONE body shape every scale wall answers with.

    Built here, and by :func:`app.devmode.user_creation_refusal`, so a
    client has one refusal to parse instead of one per wall. The dev-mode
    single-user cap is a scale wall too — it refuses the second user because
    the deployment has outgrown what it is licensed for — and it used to
    answer 403 with a body sharing no keys with this one, so the upgrade UI
    had to special-case it and an operator reading logs saw two unrelated
    failures for one class of problem.

    ``error`` still names the specific cause: same shape, same status,
    different reason, which is what lets a client branch on the reason
    without re-learning the shape.
    """
    return {
        "error": error,
        "message": message,
        "dimension": dimension,
        "limit": limit,
        "current": current,
        "current_tier": current_tier,
        # Null rather than absent when no tier lifts it: the key is always
        # present so a client never reads absence as a default.
        "required_tier": required_tier,
    }


async def quota_refusal(
    dimension: str, current: int, adding: int = 1
) -> tuple[dict[str, Any], int] | None:
    """The 402 body when a limit refuses the write, else None.

    402 Payment Required rather than 403: this is a scale wall, not an
    authorization decision. Keeping them on different statuses means a
    client (and an operator reading a log) can tell "you may not do this"
    apart from "you have outgrown this plan", which are opposite problems
    with opposite remedies. The body reuses the shape ``require_feature``
    answers, so the UI renders one upgrade prompt for both.
    """
    limits = await resolve_limits()
    limit = getattr(limits, dimension)
    if limit == UNLIMITED or (current + adding) <= limit:
        return None

    tier = await licensing.resolve_tier()
    upgrade = minimum_tier_for(dimension, current + adding)
    label = DIMENSION_LABELS.get(dimension, dimension)

    # An upgrade that is not STRICTLY above the current tier is not an
    # upgrade. It arises when a licence LOWERS a limit below its tier
    # default: the default table still admits the write, so
    # minimum_tier_for names the tier the deployment is already on, and the
    # operator is told to "upgrade to community". In that case the binding
    # constraint is the deployment's own contract, not the plan, and the
    # honest answer is that no tier lifts it — contact sales.
    if upgrade is not None and licensing.TIER_ORDER.index(
        upgrade
    ) <= licensing.TIER_ORDER.index(tier):
        upgrade = None

    log.warning(
        "quota_limit_refused",
        dimension=dimension,
        current=current,
        limit=limit,
        tier=tier,
    )

    return (
        scale_refusal_body(
            error="quota_exceeded",
            message=(
                f"This deployment is licensed for {limit} {label}; "
                + (
                    f"the {upgrade} tier raises that limit."
                    if upgrade
                    else "contact sales to raise this limit."
                )
            ),
            dimension=dimension,
            limit=limit,
            current=current,
            current_tier=tier,
            required_tier=upgrade,
        ),
        SCALE_REFUSAL_STATUS,
    )
