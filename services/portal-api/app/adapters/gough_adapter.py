"""Gough adapter — v2, health-only.

Phase 3 lands the contract and the deny-by-default proxy; Gough's
resource operations are a Phase 4 task. Everything beyond health and
capabilities raises AdapterCapabilityError (501) rather than returning an
empty result that would read as "nothing there".
"""

from __future__ import annotations

from .base import HealthOnlyAdapter, RouteRule

__all__ = ["GoughAdapter"]


class GoughAdapter(HealthOnlyAdapter):
    """Gough hypervisor adapter (health + capabilities only)."""

    PRODUCT_TYPE: str = "gough"
    DISPLAY_NAME: str = "Gough"

    #: Deny-by-default: only these exact routes are proxied. Both are
    #: read-only liveness surfaces, so products:read is the correct floor —
    #: a viewer may confirm a product is up without holding manage rights.
    route_allowlist: list[RouteRule] = [
        RouteRule("GET", r"^/health(z)?\Z", "products:read"),
        RouteRule("GET", r"^/capabilities\Z", "products:read"),
    ]
