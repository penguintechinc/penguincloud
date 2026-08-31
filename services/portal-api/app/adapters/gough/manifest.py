"""Gough's console manifest — the first proof of the Design §3 schema.

Built from :mod:`app.adapters.gough.adapter` and :mod:`app.adapters.gough.routes`
directly, importing their constants rather than re-typing them, for the same
reason ``test_gough_webui_paths.py`` exists: a re-typed path string is exactly
how a trailing slash goes missing.

Scope for Phase 8 Step 3 — a schema finding, not a shortcut
=============================================================
Four of Gough's five resource kinds are declared here: ``nodes``, ``biomes``,
``biome_groups``, ``agents``. **``clusters`` is deliberately excluded**, and
that is the schema finding this module surfaces:

* Gough has no ``GET /api/v1/clusters`` collection — :class:`ListSpec`
  cannot describe it, and Design §4 (the ceiling) already anticipates a
  resource with no list endpoint.
* Worse, a cluster's single-item GET is NOT at ``{collection}/{id}`` — it is
  ``/api/v1/clusters/{id}/lxd/status``, an irregular shape this schema
  version has no field for (:class:`~app.adapters.manifest.ResourceDescriptor`
  declares ``list`` and column/action specs, never a standalone item path).
  Fabricating a ``list.path_bytes`` for clusters to satisfy the dataclass
  would either be a lie (a collection endpoint that 404s) or would silently
  invent a "detail path = list path + id" convention this schema does NOT
  promise anywhere else — see the "detail path" paragraph in
  :class:`~app.adapters.manifest.ResourceDescriptor`'s docstring, which is
  the same trailing-slash-shaped trap ``biome_groups`` already lives next
  to (``/api/v1/biomes/groups`` has no trailing slash; ``{path}{id}``
  concatenation would silently produce ``/api/v1/biomes/groups42``).

Clusters therefore stay unreachable through the generic renderer for now.
The honest fix is a schema addition (an explicit, separately-declared item
path template) or an :class:`~app.adapters.manifest.ExtensionSlot` page —
either is future work, not something to guess at here.

``biome_groups`` is a declared resource but NOT a nav item, matching a fact
already established by ``tests/api/test_gough_webui_paths.py``: "the adapter
also addresses ``biome_groups`` server-side, which no screen requests." The
manifest agrees with the webui's actual behaviour rather than inventing a
screen nothing has ever asked for.

``transport`` is ``"typed"`` for all four included resources. Every read in
this schema version goes through the byte proxy regardless of ``transport``
(see :class:`~app.adapters.manifest.ResourceDescriptor`'s docstring) — the
field here answers "does this resource have typed mutation backing"
(``resources_api.py`` create/delete, ``operations_api.py`` actions), and all
four do: nodes (delete, deploy/evacuate/reject), biomes (create, delete,
upgrade), biome_groups (create, delete), agents (suspend/resume). None is
mutation-free, so none qualifies for ``"proxy"`` under this schema's rule
that a proxy-transport resource may declare no typed mutation at all.

Column field names are Gough's OWN raw JSON keys (``mapping.py``'s
documented reads), not the portal's normalised :class:`~app.adapters.base.Resource`
fields — Design §6.4: for a proxied read, the manifest IS the type contract,
and what the browser receives is Gough's own envelope, unmapped.

Create-form field sets below are intentionally minimal (``name`` only) and
NOT verified against Gough's own request validation, which lives in a
different repository this worktree does not check out. Flagged rather than
guessed at further — widening a create form is cheap; a field that silently
never validates is not.
"""

from __future__ import annotations

from typing import Final

from ..manifest import (
    ActionSpec,
    BooleanLabels,
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    DeleteSpec,
    DetailSpec,
    EnvelopeSpec,
    FormField,
    FormSpec,
    ItemPathSpec,
    ListSpec,
    MetricsSpec,
    NavItem,
    NavSpec,
    OperationsSpec,
    ResourceDescriptor,
    validate_manifest,
)
from .adapter import _ACTIONS, _COLLECTION_ROUTES, _COLLECTIONS, _ITEM_KEYS, GoughAdapter

__all__ = ["GOUGH_MANIFEST"]

#: Verbs :meth:`GoughAdapter.perform_action` really implements, per resource
#: kind — the frozenset form :func:`~app.adapters.manifest.validate_manifest`
#: takes. Derived from ``_ACTIONS`` rather than re-declared, so a verb added
#: to the adapter and forgotten here fails LOUDLY (an
#: :class:`~app.adapters.manifest.ActionSpec` whose ``verb`` this manifest
#: does not also add would be the wrong direction of drift — the manifest can
#: only ever be a SUBSET of what the adapter really does, and conformance
#: checks that subset relationship at import time).
_ACTION_VERBS: Final[dict[str, frozenset[str]]] = {
    kind: frozenset(verbs) for kind, verbs in _ACTIONS.items()
}

#: Resource kinds whose LIST route wraps its array inside Gough's outer
#: ``data`` envelope (``_helpers.envelope_success``). Verified by reading
#: Gough's own source at ``~/code/gough`` — NOT guessed by analogy:
#:
#: * ``list_nodes`` (``api/nodes.py``) and ``list_biomes`` (``api/biomes.py``)
#:   both ``return envelope_success({...})``, so the wire body is
#:   ``{"status": "success", "data": {"nodes"|"biomes": [...]}, "meta": {...}}``.
#: * ``list_biome_groups`` (also ``api/biomes.py``, the SAME module as
#:   ``list_biomes``) returns ``jsonify({"groups": [...], "total": ...})``
#:   directly — bare, no envelope, despite living beside the enveloped
#:   ``biomes`` route. Assuming it followed its neighbour would have been
#:   wrong; this set exists so nothing has to assume.
#: * ``list_agents`` (``api/agents.py``) likewise returns bare
#:   ``jsonify({"agents": [...], "count": ...})``.
_ENVELOPED_KINDS: Final[frozenset[str]] = frozenset({"nodes", "biomes"})

#: Per-kind :class:`~app.adapters.manifest.EnvelopeSpec` key path, handed to
#: :func:`~app.adapters.manifest.validate_manifest` as ``envelope_paths`` —
#: derived from :data:`_ITEM_KEYS` and :data:`_ENVELOPED_KINDS` rather than
#: hand-typed per resource, so the two tables cannot silently drift apart.
_ENVELOPE_PATHS: Final[dict[str, tuple[str, ...]]] = {
    kind: (("data", item_key) if kind in _ENVELOPED_KINDS else (item_key,))
    for kind, item_key in _ITEM_KEYS.items()
}

# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------

#: Phase 8 Step 8 alignment: byte-for-byte the same field set, order, and
#: labels as the hand-written ``nodeColumns.tsx`` -- proven by
#: ``ManifestResourceScreen.equivalence.test.tsx``. Schema v1's columns here
#: (``id``, ``created_at``) were never rendered by ``NodesPage`` at all, and
#: the manifest omitted ``hardware_tags``, which it does render -- a content
#: gap in the original Step 3 authoring, not a deliberate improvement, so it
#: is closed here rather than defended.
_NODES_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    # Gough nodes have no `status` field -- `state` is the lifecycle column.
    # Left as `text` rather than `enum_badge`: this worktree does not check
    # out Gough's own source, so the real state vocabulary is unverified and
    # a fabricated style mapping would be worse than a plain string.
    ColumnSpec(field="state", label="State", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="posture", label="Posture", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="ipv4", label="IPv4", cell=CellSpec(kind="text"), absent_as="dash"),
    # `nodeColumns.tsx`'s own `tags` column -- an empty (but present) array
    # is ALSO absent, matching the hand-written page's `tags.length === 0 ->
    # absent` precedent (see `manifestCells.tsx`'s `tags` renderer).
    ColumnSpec(
        field="hardware_tags",
        label="Tags",
        cell=CellSpec(kind="tags"),
        absent_as="dash",
        sortable=False,
    ),
)

_NODES: Final[ResourceDescriptor] = ResourceDescriptor(
    kind="nodes",
    label="Node",
    plural_label="Nodes",
    id_field="id",
    name_field="name",
    transport="typed",
    columns=_NODES_COLUMNS,
    empty_state="No nodes enrolled yet.",
    error_state="Unable to load nodes.",
    list=ListSpec(
        path_bytes=_COLLECTION_ROUTES["nodes"],
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS["nodes"]),
        pagination="cursor",
    ),
    # Item-route base is `_COLLECTIONS["nodes"]` ("/api/v1/nodes", no
    # trailing slash) -- NOT `_COLLECTION_ROUTES["nodes"]` ("/api/v1/nodes/",
    # the LIST path) -- see `ItemPathSpec`'s docstring for why the two
    # differ and why conflating them is the trap this field exists to close.
    item_path=ItemPathSpec(prefix=_COLLECTIONS["nodes"], sample_id="1"),
    detail=DetailSpec(tabs=("Overview", "Tags", "Biomes")),
    actions=(
        ActionSpec(
            verb="deploy",
            label="Deploy",
            variant="primary",
            requires="manage",
            confirm="Deploy a biome to this node?",
            starts_operations=True,
        ),
        ActionSpec(
            verb="evacuate",
            label="Evacuate",
            variant="danger",
            requires="manage",
            confirm="Evacuate all biomes from this node?",
        ),
        ActionSpec(
            verb="reject",
            label="Reject",
            variant="danger",
            requires="manage",
            confirm="Reject this node from the fleet? This cannot be undone.",
        ),
    ),
    create=None,  # nodes are discovered from hardware, never portal-created
    delete=DeleteSpec(confirm="Decommission this node? This cannot be undone.", requires="manage"),
)

# ---------------------------------------------------------------------------
# biomes
# ---------------------------------------------------------------------------

#: Phase 8 Step 8 alignment: byte-for-byte the same field set, order, and
#: labels as the hand-written ``biomeColumns.tsx``. Two real mismatches
#: closed here, not just a reshuffle:
#:
#: * The field was ``biome_type`` (label "Type"); the webui screen reads and
#:   renders ``biome_kind`` (label "Kind"). Both are genuine raw keys Gough's
#:   own ``mapping.py`` reads (see that module's ``map_biome``), but only
#:   ``biome_kind`` is what any screen has ever shown an operator -- pointing
#:   the manifest at ``biome_type`` would have reproduced a column the
#:   hand-written page does not have and MISSED the one it does.
#: * ``is_active``'s labels were ``"Active"``/``"Inactive"`` with
#:   ``absent_as="literal:Unknown"``; ``biomeColumns.tsx`` renders lowercase
#:   ``"active"``/``"inactive"`` and a plain dash (`absent`) for a null value,
#:   never the word "Unknown".
_BIOMES_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="is_active",
        label="Active",
        cell=CellSpec(
            kind="boolean", labels=BooleanLabels(true_label="active", false_label="inactive")
        ),
        absent_as="dash",
    ),
    ColumnSpec(field="biome_kind", label="Kind", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(
        field="workload_type",
        label="Workload",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    ColumnSpec(field="version", label="Version", cell=CellSpec(kind="text"), absent_as="dash"),
)

_BIOMES: Final[ResourceDescriptor] = ResourceDescriptor(
    kind="biomes",
    label="Biome",
    plural_label="Biomes",
    id_field="id",
    name_field="name",
    transport="typed",
    columns=_BIOMES_COLUMNS,
    empty_state="No biomes defined yet.",
    error_state="Unable to load biomes.",
    list=ListSpec(
        path_bytes=_COLLECTION_ROUTES["biomes"],
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS["biomes"]),
        pagination="cursor",
    ),
    item_path=ItemPathSpec(prefix=_COLLECTIONS["biomes"], sample_id="1"),
    detail=DetailSpec(tabs=("Overview", "Eligibility")),
    actions=(
        ActionSpec(
            verb="upgrade",
            label="Upgrade",
            variant="primary",
            requires="manage",
            confirm="Upgrade this biome?",
            starts_operations=True,
        ),
    ),
    create=FormSpec(
        fields=(FormField(name="name", label="Name", required=True),),
        submit_label="Create Biome",
    ),
    delete=DeleteSpec(
        confirm="Delete this biome? Nodes running it will need reassignment.",
        requires="manage",
    ),
)

# ---------------------------------------------------------------------------
# biome_groups -- declared, deliberately NOT a nav item (see module docstring)
# ---------------------------------------------------------------------------

_BIOME_GROUPS_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="id", label="ID", cell=CellSpec(kind="text")),
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="description",
        label="Description",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    # `biomes` is always a list (possibly empty) per mapping.py's map_biome_group
    # -- absence and an empty membership both mean "nothing in it" here, unlike
    # the money/dash distinction, so `zero` rather than `dash` is the honest
    # absent_as for a count derived from an array.
    ColumnSpec(field="biomes", label="Members", cell=CellSpec(kind="count"), absent_as="zero"),
    ColumnSpec(
        field="created_at",
        label="Created",
        cell=CellSpec(kind="timestamp", relative=True),
        absent_as="dash",
    ),
)

_BIOME_GROUPS: Final[ResourceDescriptor] = ResourceDescriptor(
    kind="biome_groups",
    label="Biome Group",
    plural_label="Biome Groups",
    id_field="id",
    name_field="name",
    transport="typed",
    columns=_BIOME_GROUPS_COLUMNS,
    empty_state="No biome groups defined yet.",
    error_state="Unable to load biome groups.",
    list=ListSpec(
        path_bytes=_COLLECTION_ROUTES["biome_groups"],
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS["biome_groups"]),
        pagination="none",
    ),
    # `_COLLECTIONS["biome_groups"]` and `_COLLECTION_ROUTES["biome_groups"]`
    # happen to be the SAME string ("/api/v1/biomes/groups", no trailing
    # slash on either) -- the one case among these four where list path and
    # item-route base coincide. Still declared via `_COLLECTIONS`, never
    # `_COLLECTION_ROUTES`, so this line stays correct if that coincidence
    # ever stops holding.
    item_path=ItemPathSpec(prefix=_COLLECTIONS["biome_groups"], sample_id="1"),
    detail=DetailSpec(tabs=("Overview",)),
    actions=(),
    create=FormSpec(
        fields=(FormField(name="name", label="Name", required=True),),
        submit_label="Create Biome Group",
    ),
    delete=DeleteSpec(confirm="Delete this biome group?", requires="manage"),
)

# ---------------------------------------------------------------------------
# agents
# ---------------------------------------------------------------------------

#: Phase 8 Step 8 alignment: byte-for-byte the same field set, order, and
#: labels as the hand-written ``agentColumns.tsx``. ``agent_id``,
#: ``capabilities`` and ``enrolled_at`` columns are dropped -- no screen has
#: ever rendered them (`agent_id` is the row's identity, addressed via
#: `id_field`/`item_path`, not a visible column). ``last_heartbeat`` changes
#: from a relative `timestamp` cell to plain `text`: `agentColumns.tsx`
#: renders the raw ISO string verbatim (`String(value)`), never "2h ago" --
#: rendering it as a relative timestamp would be a real content difference,
#: not a formatting nicety.
#:
#: One documented remaining gap, not fixed here: `agentColumns.tsx`'s
#: `hostname` column falls back to `agent_id` then the row id when
#: `hostname` is falsy (`String(value || row.agent_id || row.id)`). This
#: schema has no field for "compute this cell from a different field when
#: absent" -- a plain field-to-cell binding cannot express it, so a genuinely
#: missing `hostname` renders a dash here instead of falling back. See the
#: Step 8 report.
_AGENTS_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="hostname", label="Hostname", cell=CellSpec(kind="text")),
    # Real status vocabulary unverified (see module docstring) -- `text`,
    # not a fabricated `enum_badge` style mapping.
    ColumnSpec(field="status", label="Status", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(
        field="ip_address", label="IP address", cell=CellSpec(kind="text"), absent_as="dash"
    ),
    ColumnSpec(
        field="last_heartbeat",
        label="Last heartbeat",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
)

_AGENTS: Final[ResourceDescriptor] = ResourceDescriptor(
    kind="agents",
    label="Agent",
    plural_label="Agents",
    id_field="agent_id",
    name_field="hostname",
    transport="typed",
    columns=_AGENTS_COLUMNS,
    empty_state="No agents enrolled yet.",
    error_state="Unable to load agents.",
    list=ListSpec(
        path_bytes=_COLLECTION_ROUTES["agents"],
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS["agents"]),
        pagination="none",
    ),
    # Agent ids are UUIDs (`_UUID_ID` in routes.py) -- the sample must have
    # that SHAPE for the allowlist probe in validate_manifest to mean
    # anything; an int-shaped sample would falsely pass by accident.
    item_path=ItemPathSpec(
        prefix=_COLLECTIONS["agents"], sample_id="11111111-1111-1111-1111-111111111111"
    ),
    detail=DetailSpec(tabs=("Overview",)),
    actions=(
        ActionSpec(
            verb="suspend",
            label="Suspend",
            variant="danger",
            requires="manage",
            confirm="Suspend this agent?",
        ),
        ActionSpec(
            verb="resume",
            label="Resume",
            variant="primary",
            requires="manage",
        ),
    ),
    create=None,  # agents are enrolled by the product's own key-exchange handshake
    delete=None,  # gough exposes no agent delete route
)

# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

GOUGH_MANIFEST: Final[ConsoleManifest] = ConsoleManifest(
    manifest_version=2,
    product_type=GoughAdapter.PRODUCT_TYPE,
    display_name=GoughAdapter.DISPLAY_NAME,
    nav=NavSpec(
        items=(
            NavItem(kind="nodes", label="Nodes"),
            NavItem(kind="biomes", label="Biomes"),
            NavItem(kind="agents", label="Agents"),
        )
    ),
    resources=(_NODES, _BIOMES, _BIOME_GROUPS, _AGENTS),
    # cancel_allowed/show_logs=True is honest, not aspirational: Gough's own
    # hand-written OperationsPanel.tsx (pages/products/gough/OperationsPanel.tsx)
    # already declares both True, and list_operations() only ever surfaces
    # OP_DEPLOYMENT rows (see that method's docstring) -- the one operation
    # kind cancel_operation and operation_logs both actually implement.
    operations=OperationsSpec(
        label="Operations", poll_interval_seconds=5, cancel_allowed=True, show_logs=True
    ),
    metrics=MetricsSpec(label="Fleet Metrics"),
    extensions=(),
)

# Fail closed at import time -- Design §11.1. A manifest that does not pass
# this refuses to load; nothing downstream ever sees a partially-valid one.
validate_manifest(
    GOUGH_MANIFEST,
    GoughAdapter,
    action_verbs=_ACTION_VERBS,
    sensitive_fields=GoughAdapter.SENSITIVE_FIELDS,
    envelope_paths=_ENVELOPE_PATHS,
    supports_cancel=GoughAdapter.SUPPORTS_OPERATION_CANCEL,
    supports_operation_logs=GoughAdapter.SUPPORTS_OPERATION_LOGS,
)
