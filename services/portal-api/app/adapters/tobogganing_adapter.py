"""Tobogganing adapter — v2, health-only.

Phase 3 lands the contract and the deny-by-default proxy; Tobogganing's
resource operations are a Phase 4 task. Everything beyond health and
capabilities raises AdapterCapabilityError (501) rather than returning an
empty result that would read as "nothing there".
"""

from __future__ import annotations

from .base import HealthOnlyAdapter, RouteRule

__all__ = ["TobogganingAdapter"]


class TobogganingAdapter(HealthOnlyAdapter):
    """Tobogganing networking adapter (health + capabilities only)."""

    PRODUCT_TYPE: str = "tobogganing"
    DISPLAY_NAME: str = "Tobogganing"

    #: Deny-by-default: only these exact routes are proxied. Both are
    #: read-only liveness surfaces, so products:read is the correct floor —
    #: a viewer may confirm a product is up without holding manage rights.
    route_allowlist: list[RouteRule] = [
        # Two explicit literal rules rather than one `^/health(z)?\Z`.
        # The registry-wide id check is a POSITIVE check: every
        # non-literal segment must be string-equal to an approved id
        # shape. An optional-literal group is neither a plain literal
        # nor an id, so it would need the checker to classify regex
        # shapes heuristically — and a checker that has to guess is
        # the thing that let `[^/]+` through. Spelling both out keeps
        # the rule exact and the check mechanical.
        RouteRule("GET", r"^/health\Z", "products:read"),
        RouteRule("GET", r"^/healthz\Z", "products:read"),
        RouteRule("GET", r"^/capabilities\Z", "products:read"),
    ]
