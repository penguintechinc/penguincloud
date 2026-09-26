"""Nest's console manifest — the third of the core-3 products, Phase 8 convergence.

Built from :mod:`app.adapters.nest.adapter`, :mod:`app.adapters.nest.mapping`
and :mod:`app.adapters.nest.routes` directly, importing their constants
rather than re-typing them — the same discipline ``adapters/gough/manifest.py``
and ``adapters/tobogganing/manifest.py`` hold to, for the same reason: a
re-typed path, kind or envelope key is exactly how a manifest and its adapter
drift apart.

Column field names are Nest's OWN raw wire keys
=================================================
Every read in this schema version — list AND detail — goes through the byte
proxy regardless of a resource's ``transport`` (see
:class:`~app.adapters.manifest.ResourceDescriptor`'s docstring), so column
``field`` names here are the RAW JSON keys the ``*Record.to_dict()`` methods
in ``~/code/nest/apps/api/models.py`` actually emit — verified by reading
that sibling checkout directly, the same convention Nest's own
``adapters/nest/mapping.py`` module docstring already holds to — never the
portal's normalised :class:`~app.adapters.base.Resource` fields, and never
guessed from ``handlers/*.py`` request-side field names, which Nest's own
create/read asymmetry (see :data:`~app.adapters.nest.mapping.CREATE_FIELD_ALIASES`)
already proves can differ from the response shape.

Four resources, three transports
=================================
* ``database`` (Nest's DataResource) — ``transport="typed"``: the only kind
  with typed create/delete/action dispatch (``resources_api.py``/
  ``operations_api.py``), matching :meth:`NestAdapter.create_resource` /
  :meth:`~.adapter.NestAdapter.delete_resource` /
  :meth:`~.adapter.NestAdapter.perform_action`, none of which is kind-gated
  beyond ``_require_kind``, so all three are equally real for the other
  three kinds too — but this manifest declares typed mutation ONLY where a
  reviewable UI need exists (create/snapshot/restore/introspect/migrate/delete
  all correspond to a real hand-written affordance in
  ``services/webui/.../nest/Database*.tsx``). Declaring a create/delete/action
  surface for ``search_pool``/``snapshot``/``protection_policy`` with no
  screen to verify it against would be exactly the kind of unreviewed
  widening Design §2's Approach B exists to prevent.
* ``search_pool`` — ``transport="proxy"``: read-only here (list + detail,
  ``search-pools/<name>`` is a real ``GET`` route — verified at
  ``~/code/nest/apps/api/app.py:392``), no typed mutation declared for the
  same "no screen to verify against" reason as above.
* ``snapshot`` / ``protection_policy`` — ``transport="proxy"``,
  ``item_path=None``: Nest registers ``GET`` on the collection and
  ``DELETE`` on the item for both (``app.py:340-378``) but no item-level
  ``GET`` for either — confirmed by the same route dump used to verify
  ``search_pool``'s. ``NEST_ROUTE_ALLOWLIST`` admits no item rule for
  either kind, matching :attr:`NestAdapter._DETAIL_KINDS` excluding both.
  This is the ``biome_groups``/``blockpage_route`` precedent: a resource
  Nest genuinely has no single-item read for, not an omission to close
  later.

No hand-written screen exists for ``search_pool``, ``snapshot`` or
``protection_policy`` anywhere in ``services/webui/.../nest/`` (confirmed by
listing that directory: only ``database``/billing/usage/operations files
exist). Their columns are therefore derived from the verified wire shape
alone (``~/code/nest/apps/api/models.py``'s ``SearchPoolRecord``,
``VolumeSnapshotRecord``, ``DataProtectionPolicyRecord`` ``to_dict()``
methods) rather than from a screen to mirror — the same evidentiary
standard ``adapters/tobogganing/manifest.py`` used for ``blockpage_route``.
None of the three is a nav item, matching that same precedent: a resource
this adapter serves server-side that no screen has ever rendered stays
declared-but-unlinked rather than inventing a nav entry nothing asked for.
``snapshot`` additionally never needs one — it is reachable from
``database``'s own detail drawer via :class:`~app.adapters.manifest.RelationshipSpec`
(see ``_DATABASE`` below).

Pagination is per-kind, verified against the real handlers, not assumed
uniform: ``list_data_resources`` (``handlers/dataresource.py:24-26``) reads
real ``limit``/``offset`` query params and slices server-side, so
``database`` declares ``pagination="offset"``. ``list_search_pools``,
``list_snapshots`` and ``list_protection_policies`` (``handlers/searchpool.py``,
``handlers/protection.py``) read no query parameters at all and always
return the tenant's whole collection — matching Tobogganing's own
"paginates nothing" finding — so all three declare ``pagination="none"``.

``phase`` and ``healthState`` stay ``text``, not ``enum_badge``
==================================================================
``databaseColumns.tsx``'s own ``PHASE_STYLES`` maps four values (``Ready``,
``Failed``, ``Pending``, ``Provisioning``) with a neutral fallback for
anything else — but ``~/code/nest/apps/api/models.py``'s own field comment
gives the real vocabulary in LOWERCASE (``pending | provisioning | ready |
failed | deleting``), and the mock store (``store/store.py``,
``store/sql_store.py``) only ever WRITES the literal ``"Pending"`` — no code
path in this checkout ever produces ``"Ready"``, ``"Failed"`` or
``"Provisioning"`` in any casing. Declaring an ``EnumStyle`` mapping here
would be encoding a vocabulary this P1 implementation cannot be observed to
emit, for a casing convention its own docstring and its own store already
disagree about. ``healthState`` is worse: ``databaseColumns.tsx`` colours it
by a case-INSENSITIVE two-way predicate (`` value.toLowerCase() ===
"healthy" `` -> green, every other truthy value -> red, absent -> dash) —
not an exact-match enumeration ``EnumStyle`` can express at all, and not a
real ``bool`` either (``boolean`` cell kind needs an actual boolean, and
``health_state`` is a string). ``text`` is the only honest cell kind for
either column; the colour is lost, the displayed text is not.

Nest-convergence finding on ``OperationsSpec.mode="watch"`` — see the
Session report for the full statement (not repeated in code): the generic
``useManifestOperationWatch`` hook polls ``GET /operations/{kind}/{id}``
using the RESOURCE's own kind (``"database"``, per that hook's own
docstring), while :meth:`NestAdapter.get_operation` requires
``kind in OPERATION_KINDS`` (``{"operation"}``, :data:`~.mapping.OP_KIND`)
and raises :class:`~app.adapter_errors.AdapterCapabilityError` for anything
else — so wiring the frontend hook to this resource as-is 501s. This module
still declares ``mode="watch"`` because the BACKEND capability
(``get_operation`` is real) is what :class:`~app.adapters.manifest.OperationsSpec`
states; reconciling the hook's ``kind`` parameter is frontend-stage work,
not a manifest authoring choice.
"""

from __future__ import annotations

from typing import Final

from ..base import TENANT_PLACEHOLDER
from ..manifest import (
    ActionSpec,
    BooleanLabels,
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    DeleteSpec,
    DetailSpec,
    EnvelopeSpec,
    ExtensionSlot,
    FieldAlias,
    FormField,
    FormSpec,
    ItemPathSpec,
    ListSpec,
    NavItem,
    NavSpec,
    OperationsSpec,
    RelationshipSpec,
    ResourceDescriptor,
    SelectOption,
    validate_manifest,
)
from .adapter import _ACTIONS, NestAdapter
from .mapping import (
    COLLECTION_ENVELOPE_KEYS,
    CREATE_FIELD_ALIASES,
    KIND_DATABASE,
    KIND_PROTECTION_POLICY,
    KIND_SEARCH_POOL,
    KIND_SNAPSHOT,
)
from .routes import (
    COLLECTION_DATA_RESOURCES,
    COLLECTION_PROTECTION_POLICIES,
    COLLECTION_SEARCH_POOLS,
    COLLECTION_SNAPSHOTS,
    tenant_path,
)

__all__ = ["NEST_MANIFEST"]

#: Only ``database`` declares any action verb — see the module docstring for
#: why the other three kinds stay action-free despite the adapter's
#: ``perform_action`` not being kind-gated for them.
_ACTION_VERBS: Final[dict[str, frozenset[str]]] = {KIND_DATABASE: frozenset(_ACTIONS)}

#: Per-kind :class:`~app.adapters.manifest.EnvelopeSpec` key path, handed to
#: :func:`~app.adapters.manifest.validate_manifest` as ``envelope_paths`` —
#: derived from :data:`~app.adapters.nest.mapping.COLLECTION_ENVELOPE_KEYS`
#: rather than hand-typed per resource, so the two tables cannot silently
#: drift apart. Every entry is a bare single key: none of Nest's four list
#: handlers wraps its array inside an outer ``data`` key (verified by
#: reading ``handlers/dataresource.py``, ``handlers/searchpool.py`` and
#: ``handlers/protection.py`` directly).
_ENVELOPE_PATHS: Final[dict[str, tuple[str, ...]]] = {
    kind: (key,) for kind, key in COLLECTION_ENVELOPE_KEYS.items()
}

# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------

#: Byte-for-byte the same field set, order, and labels as the hand-written
#: ``databaseColumns.tsx``. See the module docstring for why ``phase`` and
#: ``healthState`` are ``text`` rather than ``enum_badge``.
_DATABASE_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="phase", label="Phase", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="healthState", label="Health", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="resourceType", label="Type", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(
        field="storageClass",
        label="Storage class",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="sizeGi",
        label="Size",
        cell=CellSpec(kind="number", unit="GiB"),
        absent_as="dash",
    ),
)

#: Byte-for-byte the same field set, order, labels, defaults and options as
#: the hand-written ``databaseColumns.tsx``'s ``databaseFields``. The portal
#: names (``resourceType``, ``storageClass``) are used deliberately, not
#: Nest's wire names (``type``, ``class``) — see :data:`FieldAlias` below and
#: ``databaseColumns.tsx``'s own comment: posting the wire names directly
#: would still work, but posting what a row just READ is what exercises the
#: alias path rather than depending on the operator to know the asymmetry.
#: The eight ``resourceType`` options are Nest's own ``valid_types`` set
#: (``handlers/dataresource.py``); anything outside it 400s
#: ``nest.dataresource.invalid_type``.
_DATABASE_FORM_FIELDS: Final[tuple[FormField, ...]] = (
    FormField(name="name", label="Name", required=True),
    FormField(
        name="resourceType",
        label="Resource type",
        field_type="select",
        required=True,
        default_value="postgres",
        options=(
            SelectOption(value="postgres", label="PostgreSQL"),
            SelectOption(value="keyvalue", label="Key/value"),
            SelectOption(value="search", label="Search"),
            SelectOption(value="object", label="Object store"),
            SelectOption(value="pvc/block", label="Block volume"),
            SelectOption(value="pvc/file", label="File volume"),
            SelectOption(value="nfs", label="NFS"),
            SelectOption(value="iscsi", label="iSCSI"),
        ),
    ),
    FormField(name="storageClass", label="Storage class"),
    FormField(name="namespace", label="Namespace", default_value="default"),
)

#: :data:`~app.adapters.nest.mapping.CREATE_FIELD_ALIASES`'s
#: ``database`` entry, restated as :class:`FieldAlias` — imported from the
#: same table :meth:`NestAdapter.create_resource` calls through
#: :func:`~app.adapters.nest.mapping.to_create_payload`, so a wire-name
#: change there cannot silently leave this form posting the old alias.
_DATABASE_FIELD_ALIASES: Final[tuple[FieldAlias, ...]] = tuple(
    FieldAlias(portal_name=portal_name, product_name=wire_name)
    for portal_name, wire_name in CREATE_FIELD_ALIASES[KIND_DATABASE].items()
)

_DATABASE: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_DATABASE,
    label="Database",
    plural_label="Databases",
    id_field="name",
    name_field="name",
    transport="typed",
    columns=_DATABASE_COLUMNS,
    empty_state="No databases provisioned yet.",
    error_state="Unable to load databases.",
    list=ListSpec(
        path_bytes=tenant_path(TENANT_PLACEHOLDER, COLLECTION_DATA_RESOURCES),
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_DATABASE]),
        pagination="offset",
    ),
    item_path=ItemPathSpec(
        prefix=tenant_path(TENANT_PLACEHOLDER, COLLECTION_DATA_RESOURCES),
        sample_id="sample-db",
    ),
    # "Snapshots" comes from `relationships` below, and "Health" from the
    # `detail_tab` extension slot in NEST_MANIFEST.extensions -- neither tab
    # is expressed here (`ManifestResourceDetail.tsx` derives Overview from
    # `columns` and appends relationship/extension tabs itself; `tabs` below
    # is documentation of the resulting drawer, matching Gough's own
    # `_NODES`/`_BIOMES` precedent of naming tabs it does not itself render).
    detail=DetailSpec(tabs=("Overview", "Health", "Snapshots")),
    # Confirm copy is byte-exact with `databaseActions.ts`'s own `message()`
    # strings (snapshot/restore/migrate) with `{name}` standing in for the
    # per-row interpolation `ManifestResourceDetail.tsx` performs -- see
    # `ActionSpec.confirm`'s docstring. `introspect` has no hand-written
    # button (`databaseActions.ts`'s own comment: "It stays available
    # through the adapter" -- deliberately not surfaced by the current
    # screen), so its label/confirm are authored here from
    # `introspect_imported_resource`'s own docstring
    # (`~/code/nest/apps/api/app.py:297-303`, "Introspect an imported
    # DataResource") rather than mirrored from a UI that does not offer it.
    # `requires` splits on Nest's OWN scope requirement for each route
    # (`app.py:282-309`): snapshot/restore/migrate need
    # `nest:dataresource:write`, introspect needs only
    # `nest:dataresource:read` -- the least-privilege portal-side split that
    # fact supports.
    actions=(
        ActionSpec(
            verb="snapshot",
            label="Snapshot",
            variant="primary",
            requires="manage",
            confirm=(
                'Take a point-in-time snapshot of "{name}". The resource stays '
                "online; the snapshot is charged as stored capacity until it is "
                "deleted."
            ),
            starts_operations=True,
        ),
        ActionSpec(
            verb="restore",
            label="Restore",
            variant="danger",
            requires="manage",
            confirm=(
                'Restore "{name}" from its most recent backup. Nest restores '
                "side-by-side by default, so this provisions a NEW resource "
                "rather than overwriting this one — but it consumes capacity "
                "and takes time."
            ),
            starts_operations=True,
        ),
        ActionSpec(
            verb="introspect",
            label="Introspect",
            variant="primary",
            requires="read",
            confirm=(
                'Introspect "{name}" to produce a schema report for this '
                "imported resource. This does not modify the resource."
            ),
            starts_operations=True,
        ),
        ActionSpec(
            verb="migrate",
            label="Migrate to managed",
            variant="danger",
            requires="manage",
            confirm=(
                'Migrate "{name}" to Nest-managed storage. This moves the '
                "underlying data and cannot be reversed from the portal."
            ),
            starts_operations=True,
        ),
    ),
    create=FormSpec(
        fields=_DATABASE_FORM_FIELDS,
        submit_label="Create",
        field_aliases=_DATABASE_FIELD_ALIASES,
    ),
    # No edit: `DatabaseDialogs.tsx`'s own comment states Nest exposes no
    # update route for a data-resource -- changing one is `migrate`, an
    # operation-starting action, not a field edit.
    edit=None,
    # Confirm copy is byte-exact with `DatabaseDialogs.tsx`'s own
    # `DeleteConfirmDialog` message.
    delete=DeleteSpec(
        confirm=(
            'Deleting "{name}" destroys the resource and its data. Snapshots '
            "taken from it are not removed and remain billable."
        ),
        requires="manage",
    ),
    # The Snapshots detail tab: every VolumeSnapshot's `sourcePVC` names the
    # DataResource it was taken from, and `database.id_field` ("name") IS the
    # value `sourcePVC` holds -- see `mapping.py`'s `to_resource` and
    # `RelationshipChildTab.tsx`'s own docstring for the exact edge.
    relationships=(RelationshipSpec(child_kind=KIND_SNAPSHOT, parent_field="sourcePVC"),),
)

# ---------------------------------------------------------------------------
# search_pool
# ---------------------------------------------------------------------------

#: No hand-written screen exists for this kind (see the module docstring) --
#: derived from ``SearchPoolRecord.to_dict()``
#: (``~/code/nest/apps/api/models.py:161-170``), the only documented
#: evidence of this kind's wire shape. ``tenantCount``/``replicas`` are
#: plain scalar integers Nest already reports, not arrays to count -- the
#: same "number, not count" distinction Tobogganing's own
#: ``client_count`` column draws.
_SEARCH_POOL_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="phase", label="Phase", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(field="endpoint", label="Endpoint", cell=CellSpec(kind="text"), absent_as="dash"),
    ColumnSpec(
        field="tenantCount",
        label="Tenants",
        cell=CellSpec(kind="number"),
        absent_as="zero",
    ),
    ColumnSpec(field="replicas", label="Replicas", cell=CellSpec(kind="number"), absent_as="zero"),
    ColumnSpec(field="version", label="Version", cell=CellSpec(kind="text"), absent_as="dash"),
)

_SEARCH_POOL: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_SEARCH_POOL,
    label="Search Pool",
    plural_label="Search Pools",
    id_field="name",
    name_field="name",
    transport="proxy",
    columns=_SEARCH_POOL_COLUMNS,
    empty_state="No search pools defined yet.",
    error_state="Unable to load search pools.",
    list=ListSpec(
        path_bytes=tenant_path(TENANT_PLACEHOLDER, COLLECTION_SEARCH_POOLS),
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_SEARCH_POOL]),
        pagination="none",
    ),
    # `GET /search-pools/<name>` is a real route
    # (`~/code/nest/apps/api/app.py:392`) -- see the module docstring.
    item_path=ItemPathSpec(
        prefix=tenant_path(TENANT_PLACEHOLDER, COLLECTION_SEARCH_POOLS),
        sample_id="sample-pool",
    ),
)

# ---------------------------------------------------------------------------
# snapshot -- declared, deliberately NOT a nav item (see module docstring)
# ---------------------------------------------------------------------------

#: ``sourcePVC`` is deliberately NOT a column: it is the parent-edge field
#: `RelationshipSpec.parent_field` reads directly off the row (never
#: requires a declared column to do so -- see `RelationshipChildTab.tsx`),
#: and every row reachable through the one place this kind is ever shown
#: (`database`'s own Snapshots tab) shares the identical value, which
#: `DatabaseTabs.tsx`'s own hand-written `SnapshotsTab` also never renders
#: as a column. ``readyToUse``/``creationTime``/``sizeBytes`` mirror that
#: same hand-written tab's content exactly: ready/pending text,
#: the verbatim ISO string (never a relative timestamp -- the same
#: `last_heartbeat`/`updated_at` finding Gough's and Tobogganing's own
#: manifests already document), and a human byte size.
_SNAPSHOT_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="readyToUse",
        label="Ready",
        cell=CellSpec(
            kind="boolean", labels=BooleanLabels(true_label="ready", false_label="pending")
        ),
        absent_as="dash",
    ),
    ColumnSpec(field="sizeBytes", label="Size", cell=CellSpec(kind="bytes"), absent_as="dash"),
    ColumnSpec(field="creationTime", label="Created", cell=CellSpec(kind="text"), absent_as="dash"),
)

_SNAPSHOT: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_SNAPSHOT,
    label="Snapshot",
    plural_label="Snapshots",
    id_field="name",
    name_field="name",
    transport="proxy",
    columns=_SNAPSHOT_COLUMNS,
    empty_state="No snapshots taken yet.",
    error_state="Unable to load snapshots.",
    list=ListSpec(
        path_bytes=tenant_path(TENANT_PLACEHOLDER, COLLECTION_SNAPSHOTS),
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_SNAPSHOT]),
        pagination="none",
    ),
    # No item GET route -- see the module docstring.
    item_path=None,
)

# ---------------------------------------------------------------------------
# protection_policy -- declared, deliberately NOT a nav item
# ---------------------------------------------------------------------------

#: No hand-written screen exists for this kind either -- derived from
#: ``DataProtectionPolicyRecord.to_dict()``
#: (``~/code/nest/apps/api/models.py:135-144``), kept plain ``text``
#: throughout for the same "no screen to mirror" reason
#: ``_BLOCKPAGE_ROUTE_COLUMNS`` stays minimal in Tobogganing's own manifest.
_PROTECTION_POLICY_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="snapshotSchedule",
        label="Snapshot schedule",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="backupSchedule",
        label="Backup schedule",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="destination", label="Destination", cell=CellSpec(kind="text"), absent_as="dash"
    ),
    ColumnSpec(
        field="lastSnapshot",
        label="Last snapshot",
        cell=CellSpec(kind="text"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="lastBackup", label="Last backup", cell=CellSpec(kind="text"), absent_as="dash"
    ),
)

_PROTECTION_POLICY: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_PROTECTION_POLICY,
    label="Protection Policy",
    plural_label="Protection Policies",
    id_field="name",
    name_field="name",
    transport="proxy",
    columns=_PROTECTION_POLICY_COLUMNS,
    empty_state="No protection policies defined yet.",
    error_state="Unable to load protection policies.",
    list=ListSpec(
        path_bytes=tenant_path(TENANT_PLACEHOLDER, COLLECTION_PROTECTION_POLICIES),
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_PROTECTION_POLICY]),
        pagination="none",
    ),
    # No item GET route -- see the module docstring.
    item_path=None,
)

# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

NEST_MANIFEST: Final[ConsoleManifest] = ConsoleManifest(
    manifest_version=2,
    product_type=NestAdapter.PRODUCT_TYPE,
    display_name=NestAdapter.DISPLAY_NAME,
    # Only `database` is a nav item -- `search_pool`/`snapshot`/
    # `protection_policy` have no hand-written screen (see module docstring);
    # `snapshot` additionally never needs one, being reachable only through
    # `database`'s own Snapshots detail tab.
    nav=NavSpec(items=(NavItem(kind=KIND_DATABASE, label="Databases"),)),
    resources=(_DATABASE, _SEARCH_POOL, _SNAPSHOT, _PROTECTION_POLICY),
    # `mode="watch"`: `get_operation` is real, `list_operations` is not (see
    # `adapter.py`'s own module docstring, "Operations"). See the module
    # docstring's Nest-convergence finding for the frontend `kind` gap this
    # does NOT paper over.
    operations=OperationsSpec(label="Operations", poll_interval_seconds=5, mode="watch"),
    # No metrics tile: "metrics_summary" is not among the capabilities
    # NestAdapter.capabilities() reports -- billing/cost data is its own
    # `page` extension slot instead (see `extensions` below).
    metrics=None,
    # Exactly two slots -- Design §4.1's per-product budget.
    # `page`/"billing": `BillingPage.tsx` already exists as a hand-written
    # screen (cost-report/summary, usage) with no generic-manifest
    # equivalent in this schema version.
    # `detail_tab`/"health": `DatabaseTabs.tsx`'s own Health tab is free-prose
    # health-probe detail (`healthMessage` can be long) a plain `FactList`
    # column set already covers reasonably well via `_DATABASE_COLUMNS`, but
    # `healthLastCheck`/`externalProvider`/`externalEndpoint`/`externalRegion`
    # are NOT declared as top-level columns (over-wide for the list table),
    # so the detail_tab slot is what surfaces them -- resolved against
    # `database`, matching `DatabaseTabs.tsx`'s own tab of that name exactly.
    extensions=(
        ExtensionSlot(slot="page", id="billing", label="Billing"),
        ExtensionSlot(slot="detail_tab", id="health", resource=KIND_DATABASE, label="Health"),
    ),
)

# Fail closed at import time -- Design §11.1. A manifest that does not pass
# this refuses to load; nothing downstream ever sees a partially-valid one.
validate_manifest(
    NEST_MANIFEST,
    NestAdapter,
    action_verbs=_ACTION_VERBS,
    sensitive_fields=frozenset(),  # NestAdapter declares no SENSITIVE_FIELDS
    envelope_paths=_ENVELOPE_PATHS,
    supports_cancel=False,
    supports_operation_logs=False,
)
