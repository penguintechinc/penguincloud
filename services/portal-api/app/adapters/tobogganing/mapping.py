"""Map Tobogganing's payloads onto the portal's contract-v2 shapes.

The collection envelope table is the load-bearing part of this module.

Tobogganing has NO shared collection envelope
=============================================
Every list route names its rows differently, and **nothing anywhere in the
product answers ``items``**:

===================================== ================
route                                 envelope key
===================================== ================
``GET /api/v1/clusters/``             ``clusters``
``GET /api/v1/sdwan/clients``         ``clients``
``GET /api/v1/sdwan/clusters``        ``clusters``
``GET /api/v1/sdwan/wireguard/peers`` ``peers``
``GET /api/v1/sase/blockpages/pages`` ``pages``
``GET /api/v1/sase/blockpages/routes````routes``
``GET /api/v1/sase/swg/policy``       ``policies``
===================================== ================

This is the defect Phase 4N shipped against Nest, where four kinds were decoded
as ``items`` and three of them rendered as permanently empty — with the UI
stating it to the operator as fact ("No snapshots have been taken"). Had this
adapter assumed ``items``, **every** Tobogganing table would have been empty,
with nothing failing anywhere.

So the table below is not transcribed: ``tests/api/test_tobogganing_envelopes.py``
reads the key each route's registered handler actually emits — out of a live
boot of Tobogganing, or the vendored copy of one — and asserts this table
matches. A rename in the product is a red build, not a blank screen.

:func:`envelope_key` raises for an unknown kind rather than defaulting. A kind
whose envelope nobody looked up must fail loudly at the call site; defaulting to
``items`` is precisely how a collection decodes as empty forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from ..base import Resource

__all__ = [
    "KIND_SDWAN_CLIENT",
    "KIND_SDWAN_CLUSTER",
    "KIND_WIREGUARD_PEER",
    "KIND_BLOCK_PAGE",
    "KIND_BLOCKPAGE_ROUTE",
    "KIND_SWG_POLICY",
    "RESOURCE_KINDS",
    "COLLECTION_ENVELOPE_KEYS",
    "PREVIEW_HTML_KEY",
    "KIND_LIST_ROUTES",
    "NAME_FIELDS",
    "envelope_key",
    "parse_timestamp",
    "to_resource",
]

#: Portal-facing resource kinds. These are the portal's vocabulary, not the
#: product's — the UI calls the screens Clients, Clusters, Peers, Block Pages.
KIND_SDWAN_CLIENT: Final[str] = "sdwan_client"
KIND_SDWAN_CLUSTER: Final[str] = "sdwan_cluster"
KIND_WIREGUARD_PEER: Final[str] = "wireguard_peer"
KIND_BLOCK_PAGE: Final[str] = "block_page"
KIND_BLOCKPAGE_ROUTE: Final[str] = "blockpage_route"
KIND_SWG_POLICY: Final[str] = "swg_policy"

RESOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        KIND_SDWAN_CLIENT,
        KIND_SDWAN_CLUSTER,
        KIND_WIREGUARD_PEER,
        KIND_BLOCK_PAGE,
        KIND_BLOCKPAGE_ROUTE,
        KIND_SWG_POLICY,
    }
)

#: The key each kind's rows arrive under. Graded against the product's own
#: handlers — see the module docstring.
COLLECTION_ENVELOPE_KEYS: Final[dict[str, str]] = {
    KIND_SDWAN_CLIENT: "clients",
    KIND_SDWAN_CLUSTER: "clusters",
    KIND_WIREGUARD_PEER: "peers",
    KIND_BLOCK_PAGE: "pages",
    KIND_BLOCKPAGE_ROUTE: "routes",
    KIND_SWG_POLICY: "policies",
}

#: The ``"METHOD /path"`` each kind is listed from, so the table above can be
#: bound to the route the product really serves rather than to this comment.
#: ``tests/api/test_tobogganing_envelopes.py`` looks each one up in the derived
#: envelope table and asserts the key matches.
KIND_LIST_ROUTES: Final[dict[str, str]] = {
    KIND_SDWAN_CLIENT: "GET /api/v1/sdwan/clients",
    KIND_SDWAN_CLUSTER: "GET /api/v1/sdwan/clusters",
    KIND_WIREGUARD_PEER: "GET /api/v1/sdwan/wireguard/peers",
    KIND_BLOCK_PAGE: "GET /api/v1/sase/blockpages/pages",
    KIND_BLOCKPAGE_ROUTE: "GET /api/v1/sase/blockpages/routes",
    KIND_SWG_POLICY: "GET /api/v1/sase/swg/policy",
}

#: Which field carries a human-readable name, per kind. Tobogganing is not
#: consistent about this: clusters and block pages have ``name``, clients do
#: not, and a WireGuard peer is identified by its public key. Falling back to
#: the id is honest; inventing "Unnamed" is not.
NAME_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    KIND_SDWAN_CLIENT: ("name", "hostname", "client_id", "id"),
    KIND_SDWAN_CLUSTER: ("name", "cluster_id", "id"),
    KIND_WIREGUARD_PEER: ("name", "node_id", "public_key", "id"),
    KIND_BLOCK_PAGE: ("name", "id"),
    KIND_BLOCKPAGE_ROUTE: ("pattern", "route", "id"),
    KIND_SWG_POLICY: ("name", "category", "id"),
}

#: The key the block-page preview's rendered HTML arrives under.
#:
#: NOT part of :data:`COLLECTION_ENVELOPE_KEYS` and not covered by the derived
#: table: ``tests/api/tobogganing_route_source.py`` records list-shaped
#: collection envelopes only, and this is a scalar in a two-key response
#: (``{"html": ..., "variables": ...}``,
#: ``hub_api/modules/sase/security/blockpages/api.py:371-374``). So this
#: constant's link to the product is a CITED SOURCE LINE rather than a derived
#: assertion — one link weaker than the six collection keys, recorded here so
#: nobody reads the whole module as equally machine-checked.
#:
#: It exists so the webui has something to be pinned against:
#: ``preview.html ?? ""`` renders a blank white iframe for a renamed key, and
#: "this draft renders to nothing" is a plausible thing for an operator to
#: believe.
PREVIEW_HTML_KEY: Final[str] = "html"

#: Keys that ride alongside a collection rather than being one. Mirrors the
#: derivation in ``tests/api/tobogganing_route_source.py``; asserted equal there
#: so the two cannot drift.
ENVELOPE_SIDECAR_KEYS: Final[frozenset[str]] = frozenset(
    {"meta", "total", "count", "version", "timestamp", "tenant"}
)


def envelope_key(kind: str) -> str:
    """Return the key a kind's rows arrive under.

    Raises:
        KeyError: for a kind with no declared key. Deliberately not a default
            of ``"items"`` — a new kind whose envelope nobody looked up would
            then decode as empty forever, which is the defect this table
            replaces. Tobogganing does not use ``items`` for anything.
    """
    return COLLECTION_ENVELOPE_KEYS[kind]


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse one of Tobogganing's ISO-8601 timestamps, tolerating absence.

    Returns ``None`` rather than raising: a missing or unparseable timestamp
    should degrade one column of one row, not fail the whole list. Naive
    values are read as UTC, which is what the product emits
    (``datetime.now(timezone.utc).isoformat()``).
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _display_name(kind: str, row: dict[str, Any]) -> str:
    """First populated name-ish field for a kind, else the id."""
    for candidate in NAME_FIELDS.get(kind, ("name", "id")):
        value = row.get(candidate)
        if isinstance(value, str) and value:
            return value
    identifier = row.get("id")
    return str(identifier) if identifier is not None else ""


def _identifier(kind: str, row: dict[str, Any]) -> str:
    """The row's stable id, tolerating the product's per-kind id field."""
    for candidate in ("id", "client_id", "cluster_id", "node_id", "public_key"):
        value = row.get(candidate)
        if value not in (None, ""):
            return str(value)
    return ""


def to_resource(kind: str, row: dict[str, Any]) -> Resource:
    """Convert one Tobogganing row into a contract-v2 :class:`Resource`.

    ``status`` is carried verbatim rather than normalised — collapsing a
    product's lifecycle states loses the distinction an operator opened the
    dashboard to see. Everything not modelled by a named contract field is left
    in ``metadata`` rather than dropped.
    """
    known = {"id", "name", "status", "created_at", "updated_at"}
    status = row.get("status")
    return Resource(
        id=_identifier(kind, row),
        kind=kind,
        name=_display_name(kind, row),
        status=str(status) if isinstance(status, str | int) else None,
        created_at=parse_timestamp(row.get("created_at")),
        updated_at=parse_timestamp(row.get("updated_at")),
        metadata={key: value for key, value in row.items() if key not in known},
    )
