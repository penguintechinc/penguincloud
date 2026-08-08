"""Network-discovery fingerprints, kept out of the adapter contract.

Discovery asks a different question from the Adapter protocol: not "how do I
talk to this product on behalf of a tenant" but "does something on this
host:port look like this product at all". It runs before any connection
exists, so there is no ``AdapterContext``, no credential, and no tenant —
none of the things an adapter is built around.

Modelling it as class attributes on the adapters (the pre-v2 arrangement)
made every adapter carry ``DISCOVERY_PORTS``/``DISCOVERY_SIGNATURES``
whether or not it was ever discoverable, and made a typed Adapter protocol
impossible: the registry's value type had to be a concrete base class with
those attributes rather than the protocol. Splitting it out is what lets the
registry hold ``type[Adapter]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

__all__ = ["DiscoveryProfile", "DISCOVERY_PROFILES"]


@dataclass(slots=True, frozen=True)
class DiscoveryProfile:
    """How to recognise one product on the network.

    Attributes:
        product_type: Registry key this profile identifies.
        display_name: Human-facing name for a discovered candidate.
        ports: Ports probed for this product.
        health_endpoint: Path probed on each port.
        signatures: Case-insensitive substrings looked for in the response
            body or ``Server`` header. A match promotes a candidate from
            "something answered" to "this is probably that product".
    """

    product_type: str
    display_name: str
    ports: tuple[int, ...]
    health_endpoint: str = "/healthz"
    signatures: tuple[str, ...] = field(default_factory=tuple)


#: Profiles for products with a v2 adapter. Planned products are absent on
#: purpose: discovering a product the portal cannot then manage offers the
#: operator a connection that would fail at the first proxied call.
DISCOVERY_PROFILES: Final[dict[str, DiscoveryProfile]] = {
    "gough": DiscoveryProfile(
        product_type="gough",
        display_name="Gough",
        ports=(8080, 8443),
        signatures=("gough",),
    ),
    "nest": DiscoveryProfile(
        product_type="nest",
        display_name="Nest",
        ports=(8080, 8443),
        signatures=("nest", "nestdata"),
    ),
    "tobogganing": DiscoveryProfile(
        product_type="tobogganing",
        display_name="Tobogganing",
        ports=(8080, 8443),
        signatures=("tobogganing",),
    ),
}
