"""``GET /api/v1/features`` — what this deployment has turned on, for the UI.

Replaces a build-time seam. ``featureGates.ts`` shipped a hardcoded
all-false map with a ``VITE_ENABLE_PRODUCTS`` env override, which meant
enabling a product for a customer was a rebuild of the frontend image, and
the browser's idea of what was on could differ from the portal's with
nothing reporting the disagreement. One authoritative answer, computed
where the flags and the licence actually live.

Authenticated on purpose
========================
The response enumerates every product the portal integrates and every
licensed capability — a map of the commercial surface. It is not secret,
but it is not something to publish to an unauthenticated caller either, for
the same reason the full OpenAPI document is gated (backend.md).

The response DTO names every key unconditionally
================================================
``flags`` carries an entry for every declared flag, never a sparse map of
"the on ones". A client that has to treat an absent key as false cannot
distinguish "off" from "the response was not the shape I expected" — the
absent-key-renders-as-none defect this repo has already shipped once. The
webui's decoder throws on a missing key, which only works if this side
promises they are all present.
"""

from __future__ import annotations

from dataclasses import asdict as dataclass_asdict
from dataclasses import dataclass
from typing import Any

from quart import Blueprint
from quart_schema import validate_response

from . import devmode, flags, licensing, quotas
from .middleware import auth_required, get_current_user

features_bp = Blueprint("features", __name__)


@dataclass(slots=True, frozen=True)
class FeaturesResponse:
    """Everything the UI needs to decide what to render.

    An explicit DTO rather than a dict: the response schema is enforced
    field by field, so nothing added to the flag or licensing modules for
    internal use can start being published by accident.
    """

    #: Every declared flag, by feature name (unnamespaced), always complete.
    flags: dict[str, bool]
    #: The licensed tier: community | professional | enterprise.
    tier: str
    #: Every tier, narrowest first, so the UI need not re-derive ordering.
    tiers: list[str]
    #: Licensed feature -> minimum tier. Lets the UI name the upgrade
    #: required instead of hardcoding a second copy of the tier map.
    licensed_features: dict[str, str]
    #: True when ``--dev`` is ACTIVE (all three conditions hold), which is
    #: what the persistent UI banner renders on. Re-evaluated per request:
    #: a deployment that grows past one user stops reporting it.
    dev_mode: bool
    #: How many users dev mode permits, so the banner can say so.
    dev_mode_max_users: int
    #: Effective scale/structure limits by dimension, ``-1`` meaning
    #: unlimited. Published so the UI can show "1 of 1 tenants" BEFORE the
    #: operator hits a 402, and because a licence may raise or lower any of
    #: them per deployment — a hardcoded client copy would be wrong for
    #: exactly the customers who negotiated a different number.
    limits: dict[str, int]


@features_bp.route("/features", methods=["GET"])
@auth_required
@validate_response(FeaturesResponse)
async def get_features() -> tuple[Any, int]:
    """Report flag state, licensed tier and dev-mode status for this caller.

    Flags are evaluated against the authenticated user as the PostHog
    ``distinct_id``, so a percentage rollout is stable per person rather
    than per request.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    distinct_id = str(user["id"])

    return (
        FeaturesResponse(
            flags=await flags.evaluate_all(distinct_id),
            tier=await licensing.resolve_tier(),
            tiers=list(licensing.TIER_ORDER),
            licensed_features=dict(licensing.FEATURE_MIN_TIER),
            dev_mode=await devmode.is_active(),
            dev_mode_max_users=devmode.MAX_DEV_MODE_USERS,
            limits=dataclass_asdict(await quotas.resolve_limits()),
        ),
        200,
    )
