"""Generic adapter — health only, for products with no bespoke adapter.

The fallback for a connection whose ``product_type`` the portal has no
specific integration for. It can answer "is this endpoint alive" and nothing
else, deliberately:

* Its ``route_allowlist`` is EMPTY, so the proxy forwards nothing through it.
  A generic adapter cannot know which of an unknown product's routes are
  safe to expose or what scope each should require, and a permissive default
  here would turn "product type we do not recognise" into an open relay to
  an arbitrary internal URL with a stored credential attached.
* Every resource operation raises AdapterCapabilityError (501). There is no
  contract to implement against.

Adding real functionality for a product means giving it its own adapter and
registry entry, not widening this one.
"""

from __future__ import annotations

from .base import HealthOnlyAdapter, RouteRule

__all__ = ["GenericAdapter"]


class GenericAdapter(HealthOnlyAdapter):
    """Health-only fallback adapter for unrecognised product types."""

    PRODUCT_TYPE: str = "generic"
    DISPLAY_NAME: str = "Generic Product"

    #: Empty by construction — see the module docstring. Not an oversight,
    #: and not a placeholder to be filled in later.
    route_allowlist: list[RouteRule] = []
