"""Tobogganing's console manifest — Phase 8 Step 4, the read surface only.

Built from :mod:`app.adapters.tobogganing.mapping` and
:mod:`app.adapters.tobogganing.routes` directly, importing their constants
rather than re-typing them, for the same reason ``adapters/gough/manifest.py``
does: a re-typed path or kind string is exactly how the manifest and the
adapter drift apart.

Scope for Phase 8 Step 4 — the read surface only, by design
=============================================================
This module declares all six of :data:`~app.adapters.tobogganing.mapping.RESOURCE_KINDS`
(``sdwan_client``, ``sdwan_cluster``, ``wireguard_peer``, ``block_page``,
``blockpage_route``, ``swg_policy``) — every kind the adapter serves — but
every one of them is **list + columns only**. No resource here declares
``actions``, ``create``, or ``delete``, and the manifest declares no
``operations`` or ``metrics`` block. That is not an oversight to close later
in this same PR; it is what :meth:`TobogganingAdapter.capabilities` actually
answers (``["health", "list_resources", "get_resource"]``, see
``adapter.py``'s module docstring, "No operations") plus a deliberate scope
cut: the SASE authoring mutations (block-page publish/preview, the SWG
policy ``PUT``) are proxied rather than typed, and wiring the renderer's
``FormSpec``/``ActionSpec`` path for a proxied mutation is a separate,
still-being-finalised piece of work — not something to guess at here.

``transport`` is ``"proxy"`` for all six resources — the honest value per
:class:`~app.adapters.manifest.ResourceDescriptor`'s own docstring
("``transport == 'proxy'`` means 'no typed mutation backing'"). None of these
six kinds has typed create/delete dispatch through ``resources_api.py``, or
an operation-starting action through ``operations_api.py``: the adapter
exposes no ``create_resource``, ``delete_resource``, or ``perform_action``
capability at all.

Every resource declares ``item_path=None`` — not a placeholder, a fact
:meth:`TobogganingAdapter.get_resource`'s own docstring states outright:
"Tobogganing serves no item route for any of these kinds ... this filters
the collection rather than requesting a path that would 404". Confirmed
independently by :data:`~app.adapters.tobogganing.routes.TOBOGGANING_ROUTE_ALLOWLIST`,
which admits a ``GET`` rule for each of the six *collection* paths and for
none of their would-be item paths. A resource with ``item_path=None`` never
renders a detail view (``ManifestResourceDetail.tsx`` gates on
``resource.item_path !== null``) — the honest outcome for a product whose
"detail" is really just filtering the same list response the table already
has, which this schema version has no field to express.

Every ``list`` is ``pagination="none"``. Not a default: Tobogganing
"paginates nothing" (``adapter.py``'s ``list_resources`` docstring) — every
list handler returns the tenant's whole collection in one response, with no
``page``/``limit`` query parameter on the user plane anywhere. The typed
adapter slices a page portal-side after the fact, but ``ListSpec.path_bytes``
describes the RAW byte-proxied ``GET``, which always returns the complete,
unpaginated array — the same shape Gough's own bare ``biome_groups``/
``agents`` resources declare.

Column field names are Tobogganing's OWN raw JSON keys — the same fields
:mod:`.types` (``services/webui/.../tobogganing/types.ts``) and each
hand-written ``*Columns.tsx`` file already read — not the portal's
normalised :class:`~app.adapters.base.Resource` fields. Design §6.4: for a
proxied read, the manifest IS the type contract.

``blockpage_route`` is declared but deliberately NOT a nav item
=================================================================
Matches the precedent :mod:`app.adapters.gough.manifest` already set for
``biome_groups``: the adapter addresses this kind server-side
(``list_resources(blockpage_route)`` is real, ``PATH_BLOCKPAGE_ROUTES`` is
allowlisted), but **no hand-written screen in
``services/webui/.../tobogganing/`` has ever requested it** — there is no
``blockpageRouteColumns.tsx``, no route-rendering table anywhere in that
directory, confirmed by grepping the whole package. Its two columns
(``id``, ``pattern``) are therefore NOT derived from a screen to mirror —
there is none — but from :data:`~app.adapters.tobogganing.mapping.NAME_FIELDS`,
whose ``KIND_BLOCKPAGE_ROUTE`` entry (``("pattern", "route", "id")``) is the
only documented evidence of this kind's raw shape in this worktree. ``id``
is used as ``id_field`` on the same basis every other kind uses it: it is
the first candidate :func:`~app.adapters.tobogganing.mapping._identifier`
tries for every kind, unconditionally. Widening this beyond two columns
would be inventing fields no committed source names.
"""

from __future__ import annotations

from typing import Final

from ..manifest import (
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    EnvelopeSpec,
    ListSpec,
    NavItem,
    NavSpec,
    ResourceDescriptor,
    validate_manifest,
)
from .adapter import TobogganingAdapter
from .mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_BLOCK_PAGE,
    KIND_BLOCKPAGE_ROUTE,
    KIND_SDWAN_CLIENT,
    KIND_SDWAN_CLUSTER,
    KIND_SWG_POLICY,
    KIND_WIREGUARD_PEER,
)
from .routes import (
    PATH_BLOCKPAGE_PAGES,
    PATH_BLOCKPAGE_ROUTES,
    PATH_SDWAN_CLIENTS,
    PATH_SDWAN_CLUSTERS,
    PATH_SWG_POLICY,
    PATH_WIREGUARD_PEERS,
)

__all__ = ["TOBOGGANING_MANIFEST"]

#: No verb any resource here declares an action for — the adapter offers no
#: ``perform_action`` capability at all (see the module docstring). Passed
#: to :func:`validate_manifest` anyway, empty, so the call shape matches
#: every other registered manifest's rather than special-casing "none".
_ACTION_VERBS: Final[dict[str, frozenset[str]]] = {}

#: Per-kind :class:`~app.adapters.manifest.EnvelopeSpec` key path, handed to
#: :func:`~app.adapters.manifest.validate_manifest` as ``envelope_paths``.
#: Derived from :data:`~app.adapters.tobogganing.mapping.COLLECTION_ENVELOPE_KEYS`
#: rather than hand-typed per resource, so the two tables cannot silently
#: drift apart. Every entry is a BARE single key — never ``("data", ...)`` —
#: :class:`~app.adapters.tobogganing.responses.TobogganingResponse.items`
#: reads ``self.data[key]`` directly off the top-level decoded body, with no
#: enveloping ``data``/``meta`` wrapper around the array for any of these six
#: kinds (verified by reading ``responses.py`` itself, not assumed from
#: Gough's differently-shaped wire format).
_ENVELOPE_PATHS: Final[dict[str, tuple[str, ...]]] = {
    kind: (key,) for kind, key in COLLECTION_ENVELOPE_KEYS.items()
}

# ---------------------------------------------------------------------------
# sdwan_client
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``clientColumns.tsx``. ``status``/``type`` stay ``text`` rather than
#: ``enum_badge`` even though ``clientColumns.tsx`` DOES carry a real
#: ``STATUS_STYLES`` colour map — matching Gough's own precedent
#: (``adapters/gough/manifest.py``'s ``_NODES_COLUMNS`` comment) of never
#: fabricating an ``EnumStyle`` mapping for a renderer whose closed style
#: vocabulary (``success``/``warning``/``danger``/``info``/``neutral``, see
#: ``manifestCells.tsx``) does not correspond 1:1 with the hand-written
#: page's own six-colour Tailwind palette. The rendered TEXT is identical
#: either way; only the colour would differ, and an unverified colour
#: mapping is worse than a plain string.
_SDWAN_CLIENT_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="status", label="Status", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="type", label="Type", cell=CellSpec(kind="text"), absent_as="dash"),
    # An unassigned client (no cluster yet) is a real, expected state an
    # operator opens this page to find — not a layout fault. `absent_as`
    # renders it as a plain dash, matching `optionalCell`'s own behaviour.
    ColumnSpec(field="cluster_id", label="Cluster", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="last_seen", label="Last seen", cell=CellSpec(kind="text"), absent_as="dash"),
)

_SDWAN_CLIENT: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_SDWAN_CLIENT,
    label="Client",
    plural_label="Clients",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=_SDWAN_CLIENT_COLUMNS,
    empty_state="No SD-WAN clients enrolled yet.",
    error_state="Unable to load SD-WAN clients.",
    list=ListSpec(
        path_bytes=PATH_SDWAN_CLIENTS,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_SDWAN_CLIENT]),
        pagination="none",
    ),
    item_path=None,  # no item route for any Tobogganing kind -- see module docstring
)

# ---------------------------------------------------------------------------
# sdwan_cluster
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``clusterColumns.tsx``. ``client_count`` uses cell kind ``number`` rather
#: than ``count``: it is already a scalar integer the product reports
#: directly, not an array whose length needs counting (contrast Gough's
#: ``biome_groups.biomes``, a real array) — but the two kinds render
#: identically for a plain number, and ``number`` states the actual shape.
#: ``absent_as="dash"`` is safe for the zero-vs-missing distinction
#: ``clusterColumns.tsx``'s own comment calls out: :func:`renderCell` in
#: ``manifestCells.tsx`` only treats ``null``/``undefined`` as absent, so a
#: real ``0`` renders as ``"0"`` and only a genuinely missing count renders
#: the dash — matching the hand-written page's own behaviour exactly.
_SDWAN_CLUSTER_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="status", label="Status", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="region", label="Region", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(
        field="datacenter", label="Datacenter", cell=CellSpec(kind="text"), absent_as="dash"
    ),
    ColumnSpec(
        field="client_count",
        label="Clients",
        cell=CellSpec(kind="number"),
        absent_as="dash",
    ),
)

_SDWAN_CLUSTER: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_SDWAN_CLUSTER,
    label="Cluster",
    plural_label="Clusters",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=_SDWAN_CLUSTER_COLUMNS,
    empty_state="No SD-WAN clusters defined yet.",
    error_state="Unable to load SD-WAN clusters.",
    list=ListSpec(
        path_bytes=PATH_SDWAN_CLUSTERS,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_SDWAN_CLUSTER]),
        pagination="none",
    ),
    item_path=None,
)

# ---------------------------------------------------------------------------
# wireguard_peer
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``peerColumns.tsx``. A WireGuard peer has NO ``id`` field at all
#: (``types.ts``'s own docstring: "identified by ``node_id``") — so unlike
#: every other kind here, ``id_field`` is ``node_id``, not ``id``. There is
#: also no separate name-ish field: ``node_id`` doubles as both identity and
#: display name, matching what the hand-written table's first ("Node")
#: column already shows. ``sortable=False`` on ``public_key`` mirrors
#: ``peerColumns.tsx``'s own explicit ``sortable: false``.
_WIREGUARD_PEER_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="node_id", label="Node", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="public_key",
        label="Public key",
        cell=CellSpec(kind="text"),
        sortable=False,
        absent_as="dash",
    ),
    ColumnSpec(field="ip_address", label="Tunnel IP", cell=CellSpec(kind="text"), absent_as="dash"),
)

_WIREGUARD_PEER: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_WIREGUARD_PEER,
    label="Peer",
    plural_label="WireGuard Peers",
    id_field="node_id",
    name_field="node_id",
    transport="proxy",
    columns=_WIREGUARD_PEER_COLUMNS,
    empty_state="No WireGuard peers enrolled yet.",
    error_state="Unable to load WireGuard peers.",
    list=ListSpec(
        path_bytes=PATH_WIREGUARD_PEERS,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_WIREGUARD_PEER]),
        pagination="none",
    ),
    item_path=None,
)

# ---------------------------------------------------------------------------
# block_page
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``blockPageColumns.tsx``. ``updated_at`` stays ``text``, not
#: ``timestamp``: ``blockPageColumns.tsx`` renders it via plain
#: ``optionalCell`` (the raw ISO string verbatim), never a relative "2h ago"
#: -- the same ``last_heartbeat`` finding Gough's own ``_AGENTS_COLUMNS``
#: comment already documents for an identical case. ``markdown`` is
#: deliberately NOT a column, matching the hand-written screen's own stated
#: reason: it is the full page source and belongs in a drawer, not a table
#: cell that would either truncate it or wreck row height -- and this schema
#: version has no drawer/detail surface for this resource regardless (see
#: the module docstring on ``item_path=None``).
_BLOCK_PAGE_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="status", label="Status", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="version", label="Version", cell=CellSpec(kind="number"), absent_as="dash"),
    ColumnSpec(
        field="updated_by", label="Updated by", cell=CellSpec(kind="text"), absent_as="dash"
    ),
    ColumnSpec(field="updated_at", label="Updated", cell=CellSpec(kind="text"), absent_as="dash"),
)

_BLOCK_PAGE: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_BLOCK_PAGE,
    label="Block Page",
    plural_label="Block Pages",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=_BLOCK_PAGE_COLUMNS,
    empty_state="No block pages defined yet.",
    error_state="Unable to load block pages.",
    list=ListSpec(
        path_bytes=PATH_BLOCKPAGE_PAGES,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_BLOCK_PAGE]),
        pagination="none",
    ),
    item_path=None,  # publish/preview/PUT are a deliberate follow-up, not this PR
)

# ---------------------------------------------------------------------------
# blockpage_route -- declared, deliberately NOT a nav item (see module docstring)
# ---------------------------------------------------------------------------

#: NOT derived from a hand-written screen -- none exists for this kind (see
#: the module docstring). Derived instead from
#: :data:`~app.adapters.tobogganing.mapping.NAME_FIELDS`'s
#: ``KIND_BLOCKPAGE_ROUTE`` entry (``("pattern", "route", "id")``), the only
#: documented evidence of this kind's raw shape in this worktree. Kept
#: deliberately minimal -- two columns, both independently evidenced --
#: rather than widened with invented fields.
_BLOCKPAGE_ROUTE_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="id", label="ID", cell=CellSpec(kind="text")),
    ColumnSpec(field="pattern", label="Pattern", cell=CellSpec(kind="text"), absent_as="dash"),
)

_BLOCKPAGE_ROUTE: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_BLOCKPAGE_ROUTE,
    label="Block Page Route",
    plural_label="Block Page Routes",
    id_field="id",
    name_field="pattern",
    transport="proxy",
    columns=_BLOCKPAGE_ROUTE_COLUMNS,
    empty_state="No block-page routes defined yet.",
    error_state="Unable to load block-page routes.",
    list=ListSpec(
        path_bytes=PATH_BLOCKPAGE_ROUTES,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_BLOCKPAGE_ROUTE]),
        pagination="none",
    ),
    item_path=None,
)

# ---------------------------------------------------------------------------
# swg_policy
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``swgPolicyColumns.tsx``. ``action`` stays ``text`` for the same
#: enum_badge-avoidance reason as ``sdwan_client.status`` above. One
#: documented remaining gap, not fixed here -- matching precisely how
#: Gough's own ``_AGENTS_COLUMNS`` names its ``hostname`` fallback gap:
#: ``swgPolicyColumns.tsx``'s ``scope_id`` column renders "Everyone" when
#: ``scope_id`` is absent AND ``row.scope === "tenant"`` -- a value computed
#: from a SECOND field on the same row. This schema has no field for
#: "compute this cell from a different field when absent"; a plain
#: field-to-cell binding cannot express it, so a genuinely missing
#: ``scope_id`` renders a dash here instead of "Everyone".
_SWG_POLICY_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="category", label="Category", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="action", label="Action", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="scope", label="Scope", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="scope_id", label="Applies to", cell=CellSpec(kind="text"), absent_as="dash"),
)

_SWG_POLICY: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_SWG_POLICY,
    label="SWG Policy",
    plural_label="SWG Policies",
    id_field="id",
    name_field="category",
    transport="proxy",
    columns=_SWG_POLICY_COLUMNS,
    empty_state="No SWG policies defined yet.",
    error_state="Unable to load SWG policies.",
    list=ListSpec(
        path_bytes=PATH_SWG_POLICY,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_SWG_POLICY]),
        pagination="none",
    ),
    item_path=None,  # the swg PUT is a deliberate follow-up, not this PR
)

# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

TOBOGGANING_MANIFEST: Final[ConsoleManifest] = ConsoleManifest(
    manifest_version=2,
    product_type=TobogganingAdapter.PRODUCT_TYPE,
    display_name=TobogganingAdapter.DISPLAY_NAME,
    nav=NavSpec(
        items=(
            NavItem(kind=KIND_SDWAN_CLIENT, label="Clients"),
            NavItem(kind=KIND_SDWAN_CLUSTER, label="Clusters"),
            NavItem(kind=KIND_WIREGUARD_PEER, label="WireGuard Peers"),
            NavItem(kind=KIND_BLOCK_PAGE, label="Block Pages"),
            NavItem(kind=KIND_SWG_POLICY, label="SWG Policy"),
        )
    ),
    resources=(
        _SDWAN_CLIENT,
        _SDWAN_CLUSTER,
        _WIREGUARD_PEER,
        _BLOCK_PAGE,
        _BLOCKPAGE_ROUTE,
        _SWG_POLICY,
    ),
    # No operations block: the adapter has no async operations at all (see
    # the module docstring, "No operations" in adapter.py) -- declaring one
    # here with cancel_allowed/show_logs=False would still be honest, but a
    # missing block states the same fact more plainly than an empty one.
    operations=None,
    # No metrics tile: "metrics_summary" is not among the capabilities
    # TobogganingAdapter.capabilities() reports.
    metrics=None,
    extensions=(),
)

# Fail closed at import time -- Design §11.1. A manifest that does not pass
# this refuses to load; nothing downstream ever sees a partially-valid one.
validate_manifest(
    TOBOGGANING_MANIFEST,
    TobogganingAdapter,
    action_verbs=_ACTION_VERBS,
    sensitive_fields=frozenset(),  # TobogganingAdapter declares no SENSITIVE_FIELDS
    envelope_paths=_ENVELOPE_PATHS,
    supports_cancel=False,
    supports_operation_logs=False,
)
