"""Product-descriptor manifest schema — the console renderer's data contract.

Phase 8, Design §3. A manifest is the ONE reviewable, statically checkable
document that tells the (future) generic webui renderer and the ``pcli``
CLI everything they need to draw a product's screens: which resources exist,
what columns they have, which actions are real, and where the data comes
from. Approach B from the design (committed manifests + a subtract-only
live overlay) — never a live-computed document, never something a product
publishes about itself. See the design doc §2 for why C (products publish
their own manifest) is rejected: it would cross the trust boundary
:mod:`app.adapters.base` exists to enforce.

Every class here is ``@dataclass(slots=True, frozen=True)``. Frozen because a
manifest is composed once, at import time, and never mutated — the overlay in
:mod:`app.console_manifests` builds a NEW manifest via
:func:`apply_capabilities_overlay` rather than mutating the committed one, so
"what shipped in the PR" and "what a request received" can always be diffed.
Collections are ``tuple[...]`` rather than ``list``/``dict`` for the same
reason: a frozen dataclass with a mutable field is not actually immutable,
just inconvenient to mutate.

Fail-closed, per Design §11.1
==============================
Two layers of refusal, deliberately split by what each layer can check on
its own:

1. **Structural** — enforced in every ``__post_init__`` below, so an invalid
   manifest cannot even be *constructed*. These are the rules that need no
   knowledge of a specific adapter: a required companion field missing for a
   cell kind, an unrecognised ``absent_as`` spelling, a proxy-transport
   resource declaring a typed mutation it has nowhere to send.
2. **Adapter-aware** — :func:`validate_manifest`, called once at import time
   by each product's own ``manifest.py`` (see ``adapters/gough/manifest.py``)
   immediately after building its ``ConsoleManifest``. These are the checks
   that need the adapter's own declared surface: is this read path actually
   in ``route_allowlist``, is this action verb one ``perform_action`` really
   implements, does this column name a field the adapter marked sensitive.

Both layers raise rather than warn. A manifest that fails either check is a
manifest that never registers — see :data:`MANIFEST_REGISTRY` in
:mod:`app.adapters.__init__` (added alongside the Gough manifest) for where
"never registers" becomes "the console never serves it, not even degraded".
There is no silent-partial-load path: a manifest either satisfies every rule
below and is servable, or it raises at import and the deployment fails to
start with the offending manifest's name in the traceback — which is the
loud failure Design §11.1 asks for, not "a menu of 403s" a caller has to
discover one click at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .base import RouteRule


class _RouteSourceAdapter(Protocol):
    """The minimal class-level shape :func:`validate_manifest` reads.

    Deliberately narrower than :class:`~app.adapters.base.Adapter` — that
    Protocol also requires a dozen async methods no real adapter's CLASS
    OBJECT (as opposed to an instance) carries meaningfully, and this
    function never instantiates one. Every real adapter (``GoughAdapter``
    et al.) already satisfies this structurally via ``PRODUCT_TYPE`` and
    ``route_allowlist``, and so can a minimal test fake — see
    ``test_manifest_schema.py``'s ``_FakeAdapter``.
    """

    PRODUCT_TYPE: str
    route_allowlist: list[RouteRule]


__all__ = [
    "MANIFEST_VERSION",
    "MIN_MANIFEST_VERSION",
    "MAX_MANIFEST_VERSION",
    "CELL_KINDS",
    "ManifestError",
    "CellSpec",
    "EnumStyle",
    "BooleanLabels",
    "FieldAlias",
    "ColumnSpec",
    "ListSpec",
    "DetailSpec",
    "RelationshipSpec",
    "FormField",
    "FormSpec",
    "ActionSpec",
    "DeleteSpec",
    "ResourceDescriptor",
    "NavItem",
    "NavSpec",
    "OperationsSpec",
    "MetricsSpec",
    "ExtensionSlot",
    "ConsoleManifest",
    "validate_manifest",
    "apply_capabilities_overlay",
]

#: The renderer-contract version this module implements. Bumped only on a
#: schema change (a field added/removed/retyped in a way the renderer must
#: know about), never on a manifest's own content changing.
MANIFEST_VERSION: Final[int] = 1

#: Oldest/newest ``manifest_version`` this build of the schema will serve.
#: Design §3.4: below MIN is refused explicitly (a named error, never an
#: empty screen); above MAX degrades to read-only with a banner rather than
#: taking a working product offline for a cosmetic addition. Both bounds are
#: consumed by the serving route in :mod:`app.console_manifests`, not by
#: this module — a manifest's own ``manifest_version`` is just data here.
MIN_MANIFEST_VERSION: Final[int] = 1
MAX_MANIFEST_VERSION: Final[int] = 1

#: The CLOSED set of cell kinds a :class:`ColumnSpec` may declare. Closed
#: deliberately — Design §3.4 says an unrecognised cell kind must fall back
#: to ``text`` at the RENDERER, never render blank; that fallback is only a
#: safe default because the server-side set here never silently grows to
#: include something the renderer has not shipped support for. Adding a
#: kind is a schema-version-bump decision, not a per-manifest one.
CELL_KINDS: Final[frozenset[str]] = frozenset(
    {
        "text",
        "enum_badge",
        "tags",
        "number",
        "bytes",
        "money",
        "timestamp",
        "boolean",
        "link",
        "count",
    }
)

#: ``absent_as`` values that are not the ``literal:<text>`` form. Design
#: §3.3: required on every non-string column, because a missing value and a
#: real zero/empty are different facts a dashboard has been wrong about
#: before (a missing billing summary rendered as ``0.00``; a null
#: ``scope_id`` rendered as a dash instead of "Everyone").
_ABSENT_AS_FIXED: Final[frozenset[str]] = frozenset({"dash", "zero"})

_LITERAL_PREFIX: Final[str] = "literal:"

#: Pagination styles a :class:`ListSpec` may declare. Mirrors
#: :class:`app.adapters.base.Page` — ``offset`` (page number),
#: ``cursor`` (opaque cursor, ``Page.total`` typically absent), or ``none``
#: for a collection with no pagination at all.
_PAGINATION_STYLES: Final[frozenset[str]] = frozenset({"offset", "cursor", "none"})

#: Scopes an :class:`ActionSpec` or :class:`DeleteSpec` may require. Mirrors
#: :data:`app.adapters.base.RouteRule`'s read/manage split — see
#: "Per-product scopes" in that module.
_REQUIRES_VALUES: Final[frozenset[str]] = frozenset({"read", "manage"})

#: Slot kinds an :class:`ExtensionSlot` may declare. Design §4.1 — a slot is
#: a NAME the console resolves against a lazily-imported registry, never
#: code, never an expression string.
_EXTENSION_SLOT_KINDS: Final[frozenset[str]] = frozenset(
    {"detail_tab", "list_header", "page", "cell"}
)

#: Design §4.1: "Budget <=2 slots per product as an acceptance criterion.
#: Without a budget, 'escape hatch' becomes 'bespoke again, with extra
#: steps'." Enforced in :meth:`ConsoleManifest.__post_init__`.
_MAX_EXTENSIONS_PER_PRODUCT: Final[int] = 2


class ManifestError(ValueError):
    """A manifest is malformed, or fails adapter-aware conformance.

    A :class:`ValueError` subclass on purpose: code that reasonably wraps
    manifest construction in ``except ValueError`` already catches this,
    while ``except ManifestError`` narrows to exactly this failure class.
    Every raise site names the manifest's ``product_type`` and the precise
    resource/column/action at fault — "manifest invalid" with no coordinates
    sends the reader back through the whole file to find it.
    """


def _require_absent_as(cell: CellSpec, absent_as: str | None) -> None:
    """Enforce Design §3.3: ``absent_as`` is required on every non-text column.

    ``None`` is the one value that reads as "the author forgot", so it is
    refused for anything except ``text`` (a string column's absence and its
    empty-string value already look identical on the wire, so silence is
    harmless there and nowhere else).
    """
    if cell.kind == "text":
        return
    if absent_as is None:
        raise ManifestError(
            f"ColumnSpec with cell kind {cell.kind!r} must declare absent_as "
            f"('dash', 'zero', or 'literal:<text>') — silence about how a "
            f"missing value renders is not a safe default, see Design §3.3"
        )
    if absent_as in _ABSENT_AS_FIXED:
        return
    if absent_as.startswith(_LITERAL_PREFIX) and len(absent_as) > len(_LITERAL_PREFIX):
        return
    raise ManifestError(f"absent_as {absent_as!r} is not 'dash', 'zero', or 'literal:<text>'")


@dataclass(slots=True, frozen=True)
class EnumStyle:
    """One ``enum_badge`` value -> style-name mapping, e.g. ``("healthy", "success")``.

    A named object rather than a bare 2-tuple: pydantic/quart-schema renders
    a fixed-length tuple as a JSON Schema ``prefixItems`` array with no
    sibling ``items``, which ``spectral``'s ``array-items`` rule (run over
    ``openapi/v1.yaml`` in CI) refuses — a real, caught-in-review defect,
    not a hypothetical one. An object with named fields sidesteps the whole
    class of problem and is more self-documenting besides.
    """

    value: str
    style: str


@dataclass(slots=True, frozen=True)
class BooleanLabels:
    """Display text for a ``boolean`` cell's two states."""

    true_label: str
    false_label: str


@dataclass(slots=True, frozen=True)
class CellSpec:
    """How one column's value is rendered — a CLOSED union, see :data:`CELL_KINDS`.

    Only the fields a given ``kind`` actually uses are meaningful; the rest
    stay at their default. Validated together so a ``money`` cell with no
    ``currency_field`` or a ``link`` cell with no ``to_kind`` fails at
    manifest construction, not when a renderer tries to draw the first row.
    """

    kind: str
    #: ``enum_badge`` — see :class:`EnumStyle`.
    styles: tuple[EnumStyle, ...] = ()
    #: ``number`` — the unit label (``"MB"``, ``"cores"``).
    unit: str | None = None
    #: ``money`` — the field on the SAME row carrying the currency code.
    currency_field: str | None = None
    #: ``timestamp`` — render relative ("2h ago") instead of absolute.
    relative: bool = False
    #: ``boolean`` — see :class:`BooleanLabels`.
    labels: BooleanLabels | None = None
    #: ``link`` — the resource kind and id field the value navigates to.
    to_kind: str | None = None
    id_field: str | None = None

    def __post_init__(self) -> None:
        """Refuse an unknown kind or a kind missing its required companion."""
        if self.kind not in CELL_KINDS:
            raise ManifestError(
                f"CellSpec kind {self.kind!r} is not in the closed set "
                f"{sorted(CELL_KINDS)} — see CELL_KINDS in this module"
            )
        if self.kind == "enum_badge" and not self.styles:
            raise ManifestError("CellSpec kind 'enum_badge' requires non-empty styles")
        if self.kind == "money" and not self.currency_field:
            raise ManifestError("CellSpec kind 'money' requires currency_field")
        if self.kind == "boolean" and self.labels is None:
            raise ManifestError("CellSpec kind 'boolean' requires labels")
        if self.kind == "link" and (not self.to_kind or not self.id_field):
            raise ManifestError("CellSpec kind 'link' requires to_kind and id_field")


@dataclass(slots=True, frozen=True)
class ColumnSpec:
    """One column of a resource's list/detail table."""

    field: str
    label: str
    cell: CellSpec
    sortable: bool = False
    #: Required for every non-``text`` cell kind — see :data:`CELL_KINDS`
    #: and :func:`_require_absent_as`.
    absent_as: str | None = None

    def __post_init__(self) -> None:
        """Refuse an empty field/label and a missing/malformed absent_as."""
        if not self.field:
            raise ManifestError("ColumnSpec.field must not be empty")
        if not self.label:
            raise ManifestError(f"ColumnSpec {self.field!r} must declare a label")
        _require_absent_as(self.cell, self.absent_as)


@dataclass(slots=True, frozen=True)
class ListSpec:
    """Where a resource's collection lives and how it paginates.

    ``path_bytes`` MUST be byte-equal to the adapter's own route constant
    (e.g. ``app.adapters.gough.adapter._COLLECTION_ROUTES[kind]``), trailing
    slash included — see the module docstring on
    ``tests/api/test_gough_webui_paths.py`` for the defect this exists to
    prevent. Never re-type this string; import the constant.
    """

    path_bytes: str
    #: Key inside the product's own JSON envelope holding the array — this
    #: is the ONLY declared shape a proxied read has, per Design §6.4.
    envelope_key: str
    pagination: str = "cursor"

    def __post_init__(self) -> None:
        """Refuse a relative path or an unrecognised pagination style."""
        if not self.path_bytes.startswith("/"):
            raise ManifestError(
                f"ListSpec.path_bytes {self.path_bytes!r} must be an absolute "
                f"path (start with '/') — it is matched against the proxy "
                f"allowlist and built as the adapter's own route constant"
            )
        if not self.envelope_key:
            raise ManifestError("ListSpec.envelope_key must not be empty")
        if self.pagination not in _PAGINATION_STYLES:
            raise ManifestError(
                f"ListSpec.pagination {self.pagination!r} is not one of "
                f"{sorted(_PAGINATION_STYLES)}"
            )


@dataclass(slots=True, frozen=True)
class DetailSpec:
    """Tab layout for a resource's detail view. Empty means a single pane."""

    tabs: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class RelationshipSpec:
    """A parent/child edge between two resource kinds in this manifest."""

    child_kind: str
    parent_field: str

    def __post_init__(self) -> None:
        """Refuse an empty edge — a relationship naming nothing is a no-op bug."""
        if not self.child_kind or not self.parent_field:
            raise ManifestError("RelationshipSpec requires both child_kind and parent_field")


@dataclass(slots=True, frozen=True)
class FormField:
    """One field of a create form.

    Mirrors ``@penguintechinc/react-libs``' ``FormField`` shape closely
    enough to serialise straight into it; the renderer step is what proves
    the fields line up exactly. Kept intentionally minimal for Step 3, since
    nothing consumes this yet — see the module docstring.
    """

    name: str
    label: str
    field_type: str = "text"
    required: bool = False
    placeholder: str | None = None
    options: tuple[str, ...] = ()
    default: str | None = None

    def __post_init__(self) -> None:
        """Refuse an unnamed field."""
        if not self.name:
            raise ManifestError("FormField.name must not be empty")
        if not self.label:
            raise ManifestError(f"FormField {self.name!r} must declare a label")


@dataclass(slots=True, frozen=True)
class FieldAlias:
    """One portal-facing -> product-facing form field rename. See :class:`FormSpec`."""

    portal_name: str
    product_name: str


@dataclass(slots=True, frozen=True)
class FormSpec:
    """A create form: its fields, and the rename a create payload needs.

    ``field_aliases`` is Design §3.3's Nest finding: a create handler that
    *reads* ``type``/``class`` but *serialises* ``resourceType``/
    ``storageClass`` needs the portal-facing name mapped to the
    product-facing one, or a form posting what it read gets a 400.
    """

    fields: tuple[FormField, ...]
    submit_label: str
    field_aliases: tuple[FieldAlias, ...] = ()

    def __post_init__(self) -> None:
        """Refuse an empty form and an empty submit label."""
        if not self.fields:
            raise ManifestError("FormSpec.fields must not be empty")
        if not self.submit_label:
            raise ManifestError("FormSpec.submit_label must not be empty")


@dataclass(slots=True, frozen=True)
class ActionSpec:
    """One non-CRUD verb offered on a resource row.

    ``starts_operations`` is the field :func:`validate_manifest` and Design
    §3.3 both key off: an action that starts pollable work returns
    ``ActionResult.operations``, which is unreachable through the byte
    proxy by construction, so the owning :class:`ResourceDescriptor` MUST
    be ``transport == "typed"`` whenever any of its actions sets this True.
    """

    verb: str
    label: str
    variant: str = "default"
    requires: str = "manage"
    confirm: str | None = None
    starts_operations: bool = False
    form: FormSpec | None = None
    #: Row-level enable predicate: ``field`` must be one of ``in_values``.
    #: Both empty means always enabled.
    enabled_when_field: str | None = None
    enabled_when_in: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse an empty verb, an invalid scope, and a half-declared predicate."""
        if not self.verb:
            raise ManifestError("ActionSpec.verb must not be empty")
        if not self.label:
            raise ManifestError(f"ActionSpec {self.verb!r} must declare a label")
        if self.requires not in _REQUIRES_VALUES:
            raise ManifestError(
                f"ActionSpec {self.verb!r} requires {self.requires!r}, "
                f"not one of {sorted(_REQUIRES_VALUES)}"
            )
        if bool(self.enabled_when_field) != bool(self.enabled_when_in):
            raise ManifestError(
                f"ActionSpec {self.verb!r}: enabled_when_field and "
                f"enabled_when_in must be declared together or not at all"
            )


@dataclass(slots=True, frozen=True)
class DeleteSpec:
    """Delete affordance for a resource. ``confirm`` is mandatory copy."""

    confirm: str
    requires: str = "manage"

    def __post_init__(self) -> None:
        """Refuse a silent delete button and an invalid scope."""
        if not self.confirm:
            raise ManifestError("DeleteSpec.confirm must not be empty")
        if self.requires not in _REQUIRES_VALUES:
            raise ManifestError(
                f"DeleteSpec requires {self.requires!r}, not one of " f"{sorted(_REQUIRES_VALUES)}"
            )


@dataclass(slots=True, frozen=True)
class ResourceDescriptor:
    """One resource kind: its shape, its columns, and how it is reached.

    ``transport`` governs the TYPED-MUTATION surface (create/delete, and
    whether an operation-starting action is reachable), never reads. Every
    read in this schema version — list AND detail — goes through the byte
    proxy; that is the only read path this codebase has (see
    ``app/resources_api.py``'s module docstring: "Reads are not here").
    ``transport == "proxy"`` means "no typed mutation backing": this schema
    version declares no mechanism for a proxy-transport resource to carry a
    typed create/delete, or an action whose result the portal must
    interpret (``starts_operations=True``) — both enforced below. A
    proxy-transport resource MAY still declare a plain action reachable
    through the ordinary allowlisted proxy POST (Gough's own
    ``evacuate``/``reject``/``suspend``/``resume`` all qualify).

    ``list`` is ``None`` for a resource with no collection endpoint at all
    (Gough's ``clusters`` — see ``adapters/gough/manifest.py`` for why it is
    NOT expressed as a ``ResourceDescriptor`` in this step; a schema finding,
    not a workaround). A resource descriptor that DOES declare ``list`` is
    assumed reachable at ``{list.path_bytes}{id}`` by nothing in THIS
    module — that derivation is deliberately not attempted here; see the
    same docstring.
    """

    kind: str
    label: str
    plural_label: str
    id_field: str
    name_field: str
    transport: str
    columns: tuple[ColumnSpec, ...]
    empty_state: str
    error_state: str
    list: ListSpec | None = None
    detail: DetailSpec = field(default_factory=DetailSpec)
    actions: tuple[ActionSpec, ...] = ()
    create: FormSpec | None = None
    delete: DeleteSpec | None = None
    relationships: tuple[RelationshipSpec, ...] = ()

    def __post_init__(self) -> None:
        """Enforce every adapter-independent invariant Design §11.1 needs.

        Raises on: an empty identity field, an unrecognised transport, no
        columns, empty state copy, a duplicate column field, a
        ``proxy``-transport resource declaring ``create``/``delete`` (this
        schema has no typed-mutation dispatch for a proxy-transport
        resource), OR — Design §3.3's named rule, checked exactly as
        written rather than folded into a broader ban — any action with
        ``starts_operations=True`` on a resource that is not
        ``transport == "typed"``. A proxy-transport resource MAY still
        declare a plain (non-operation-starting) action: Gough's own
        ``evacuate``/``reject``/``suspend``/``resume`` are all ALSO
        reachable through the plain proxy allowlist (only ``deploy`` and
        ``upgrade`` are excluded from it, for exactly this reason), so
        forbidding every action on ``proxy`` would be stricter than the
        product this manifest describes actually is.
        """
        if not self.kind:
            raise ManifestError("ResourceDescriptor.kind must not be empty")
        if self.transport not in ("proxy", "typed"):
            raise ManifestError(
                f"ResourceDescriptor {self.kind!r}: transport {self.transport!r} "
                f"is not 'proxy' or 'typed'"
            )
        if not self.id_field or not self.name_field:
            raise ManifestError(
                f"ResourceDescriptor {self.kind!r} must declare id_field and name_field"
            )
        if not self.columns:
            raise ManifestError(f"ResourceDescriptor {self.kind!r} must declare columns")
        if not self.empty_state or not self.error_state:
            raise ManifestError(
                f"ResourceDescriptor {self.kind!r} must declare empty_state and error_state"
            )
        seen_fields = {column.field for column in self.columns}
        if len(seen_fields) != len(self.columns):
            raise ManifestError(f"ResourceDescriptor {self.kind!r} has duplicate column fields")
        if self.transport == "proxy" and (self.create or self.delete):
            raise ManifestError(
                f"ResourceDescriptor {self.kind!r}: transport is 'proxy' but declares "
                f"create/delete — this schema version has no typed-mutation dispatch "
                f"for a proxy-transport resource; set transport='typed' if it really "
                f"has one"
            )
        for action in self.actions:
            if action.starts_operations and self.transport != "typed":
                raise ManifestError(
                    f"ResourceDescriptor {self.kind!r}: action {action.verb!r} sets "
                    f"starts_operations=True but transport is {self.transport!r}, not "
                    f"'typed' — ActionResult.operations is unreachable through the byte "
                    f"proxy by construction (Design §3.3)"
                )


@dataclass(slots=True, frozen=True)
class NavItem:
    """One entry in the product's nav menu."""

    kind: str
    label: str
    icon: str | None = None


@dataclass(slots=True, frozen=True)
class NavSpec:
    """The product's nav menu, derived into ``MENU_ITEM_ROUTES`` by the console.

    Deliberately no non-empty check here: :func:`apply_capabilities_overlay`
    can legitimately reconstruct one with zero items when a live connection's
    ``capabilities()`` has dropped every listable resource, and that must
    degrade the served manifest to "no nav", not raise and take the whole
    tenant's console response down with it. A COMMITTED manifest with an
    empty nav is still a reviewable-in-PR authoring choice, not a structural
    impossibility this module needs to police.
    """

    items: tuple[NavItem, ...]


@dataclass(slots=True, frozen=True)
class OperationsSpec:
    """Presence + display config for the product's operations panel."""

    label: str = "Operations"
    poll_interval_seconds: int = 5

    def __post_init__(self) -> None:
        """Refuse a non-positive poll interval — zero or negative never terminates sanely."""
        if self.poll_interval_seconds <= 0:
            raise ManifestError("OperationsSpec.poll_interval_seconds must be positive")


@dataclass(slots=True, frozen=True)
class MetricsSpec:
    """Presence + display config for the product's metrics tile."""

    label: str = "Metrics"


@dataclass(slots=True, frozen=True)
class ExtensionSlot:
    """A named escape hatch — Design §4.1. NEVER carries code, only a name.

    The console resolves ``"{product_type}.{id}"`` against a
    lazily-imported registry in ``components/extensions/``; a slot with no
    matching registry entry degrades to a generic fallback, per Design §3.4.
    """

    slot: str
    id: str
    label: str
    resource: str | None = None
    position: int = 0

    def __post_init__(self) -> None:
        """Refuse an unrecognised slot kind or an unnamed slot."""
        if self.slot not in _EXTENSION_SLOT_KINDS:
            raise ManifestError(
                f"ExtensionSlot.slot {self.slot!r} is not one of "
                f"{sorted(_EXTENSION_SLOT_KINDS)}"
            )
        if not self.id:
            raise ManifestError("ExtensionSlot.id must not be empty")


@dataclass(slots=True, frozen=True)
class ConsoleManifest:
    """The complete descriptor for one product's console screens.

    Composed once, at import time, by each product's own ``manifest.py``
    (never assembled from live data — see the module docstring). Immediately
    passed to :func:`validate_manifest` by its own module before being
    exposed via :data:`app.adapters.MANIFEST_REGISTRY` — an invalid manifest
    therefore fails at import, not at the first request that reaches it.
    """

    manifest_version: int
    product_type: str
    display_name: str
    nav: NavSpec
    resources: tuple[ResourceDescriptor, ...]
    operations: OperationsSpec | None = None
    metrics: MetricsSpec | None = None
    extensions: tuple[ExtensionSlot, ...] = ()

    def __post_init__(self) -> None:
        """Enforce whole-manifest invariants: versioning, uniqueness, nav/resource agreement.

        The nav check is the one worth naming: Design §3.4 says an unknown
        resource kind must be hidden from nav rather than rendering a link
        to nothing — enforced here as a load-time refusal instead, because a
        manifest that ships a broken nav link was never reviewed correctly
        and there is no reason to wait for a user to find the 404.
        """
        if self.manifest_version < 1:
            raise ManifestError("ConsoleManifest.manifest_version must be >= 1")
        if not self.product_type:
            raise ManifestError("ConsoleManifest.product_type must not be empty")
        if not self.resources:
            raise ManifestError(f"{self.product_type}: ConsoleManifest.resources must not be empty")
        kinds = {resource.kind for resource in self.resources}
        if len(kinds) != len(self.resources):
            raise ManifestError(f"{self.product_type}: duplicate resource kinds in manifest")
        for item in self.nav.items:
            resource = self.resource(item.kind)
            if resource is None:
                raise ManifestError(
                    f"{self.product_type}: nav item {item.kind!r} names a resource "
                    f"kind this manifest does not declare"
                )
            if resource.list is None:
                raise ManifestError(
                    f"{self.product_type}: nav item {item.kind!r} points at a resource "
                    f"with no list endpoint — nothing for the nav link to open"
                )
        if len(self.extensions) > _MAX_EXTENSIONS_PER_PRODUCT:
            raise ManifestError(
                f"{self.product_type}: {len(self.extensions)} extension slots exceeds "
                f"the Design §4.1 budget of {_MAX_EXTENSIONS_PER_PRODUCT} per product"
            )

    def resource(self, kind: str) -> ResourceDescriptor | None:
        """Look up one resource descriptor by kind, or None."""
        for resource in self.resources:
            if resource.kind == kind:
                return resource
        return None


def validate_manifest(
    manifest: ConsoleManifest,
    adapter_cls: type[_RouteSourceAdapter],
    *,
    action_verbs: Mapping[str, frozenset[str]],
    sensitive_fields: frozenset[str] = frozenset(),
) -> None:
    """Adapter-aware conformance — Design §11.1's second fail-closed layer.

    Called once, at import time, by each product's own ``manifest.py``
    immediately after building its :class:`ConsoleManifest` (see
    ``adapters/gough/manifest.py``). Raises :class:`ManifestError` — never
    returns a warning — for:

    * a resource's ``list.path_bytes`` that no GET rule in
      ``adapter_cls.route_allowlist`` admits (the manifest must refuse to
      load rather than render a menu of 403s, per Design §11.1's own
      example);
    * an :class:`ActionSpec` whose ``verb`` is not in ``action_verbs`` for
      that resource kind (an unknown verb refuses to load — distinct from
      Design §3.4's client-side "hide it", which handles a renderer older
      than a valid manifest, not an invalid one);
    * a :class:`ColumnSpec` naming a field in ``sensitive_fields`` (refused,
      never hidden — Design §3.3's ``databaseColumns.tsx`` finding);
    * ``manifest.product_type`` disagreeing with the adapter's own
      ``PRODUCT_TYPE``.

    ``adapter_cls`` is typed against :class:`_RouteSourceAdapter`, a
    deliberately narrower Protocol than
    :class:`~app.adapters.base.Adapter` — this function reads only class-
    level ``PRODUCT_TYPE``/``route_allowlist`` and never instantiates or
    calls an adapter method, so requiring the full async Protocol would be
    an unrelated widening.

    ``action_verbs`` and ``sensitive_fields`` are supplied by the caller
    rather than read off ``adapter_cls`` directly: neither is part of the
    :class:`~app.adapters.base.Adapter` Protocol today (widening it would
    force every OTHER registered adapter — Nest, Tobogganing, the generic
    fallback — to declare attributes they have no present need for, for the
    sake of one product's manifest). Gough's own module-level ``_ACTIONS``
    and (currently empty) ``SENSITIVE_FIELDS`` are the source of truth this
    function is handed; see ``adapters/gough/manifest.py``.
    """
    adapter_product_type = adapter_cls.PRODUCT_TYPE
    if manifest.product_type != adapter_product_type:
        raise ManifestError(
            f"manifest product_type {manifest.product_type!r} does not match "
            f"adapter_cls.PRODUCT_TYPE {adapter_product_type!r}"
        )

    allowlist = adapter_cls.route_allowlist

    for resource in manifest.resources:
        if resource.list is not None:
            path = resource.list.path_bytes
            if not any(rule.matches("GET", path) for rule in allowlist):
                raise ManifestError(
                    f"{manifest.product_type}/{resource.kind}: list.path_bytes "
                    f"{path!r} is not admitted by any GET rule in "
                    f"{adapter_cls.__name__}.route_allowlist — a manifest may not "
                    f"declare a read path the adapter's proxy allowlist refuses"
                )

        allowed_verbs = action_verbs.get(resource.kind, frozenset())
        for action in resource.actions:
            if action.verb not in allowed_verbs:
                raise ManifestError(
                    f"{manifest.product_type}/{resource.kind}: action verb "
                    f"{action.verb!r} is not one {adapter_cls.__name__} implements "
                    f"for this kind (known: {sorted(allowed_verbs)}) — an unknown "
                    f"verb must refuse to load, not render a dead button"
                )
            # Defense in depth, not exercised by a test for the same reason
            # it is unreachable to one: ResourceDescriptor.__post_init__
            # already refuses a starts_operations action on a non-"typed"
            # resource, so no manifest built through this module's own
            # dataclasses can ever make this condition True. Kept in case a
            # future caller builds a ResourceDescriptor by some other means.
            if action.starts_operations and resource.transport != "typed":  # pragma: no branch
                raise ManifestError(
                    f"{manifest.product_type}/{resource.kind}: action "
                    f"{action.verb!r} sets starts_operations=True but the resource "
                    f"is transport={resource.transport!r} — ActionResult.operations "
                    f"is unreachable through the byte proxy by construction"
                )  # pragma: no cover

        for column in resource.columns:
            if column.field in sensitive_fields:
                raise ManifestError(
                    f"{manifest.product_type}/{resource.kind}: column {column.field!r} "
                    f"names a field {adapter_cls.__name__} marks sensitive — refused, "
                    f"not hidden, per Design §3.3"
                )


def apply_capabilities_overlay(
    manifest: ConsoleManifest, capabilities: list[str]
) -> ConsoleManifest:
    """Subtract-only live overlay — Design §2, Approach B's other half.

    ``capabilities`` is the adapter's own :meth:`Adapter.capabilities`
    answer for the LIVE connection. This function may only REMOVE what the
    committed manifest declares; it can never add a resource, column, or
    action the manifest itself did not review and ship. That is the
    property the design recommends B specifically for: "nothing renderable
    was not reviewed."

    Mapping from a missing capability to what gets stripped:

    =====================  ===============================================
    missing capability     effect
    =====================  ===============================================
    ``list_resources``     every resource's ``list`` is dropped (None)
    ``create_resource``    every resource's ``create`` is dropped (None)
    ``delete_resource``    every resource's ``delete`` is dropped (None)
    ``perform_action``     every resource's ``actions`` is emptied
    ``metrics_summary``    ``manifest.metrics`` is dropped (None)
    ``list_operations``    ``manifest.operations`` is dropped (None)
    =====================  ===============================================

    Nav items left pointing at a now-list-less resource are dropped from
    ``nav.items`` in the same pass, so the returned manifest still satisfies
    :meth:`ConsoleManifest.__post_init__`'s nav/resource agreement — this
    function reconstructs (not mutates) every level it touches, so the
    result is itself a valid, re-checkable :class:`ConsoleManifest`.
    """
    caps = frozenset(capabilities)
    drop_list = "list_resources" not in caps
    drop_create = "create_resource" not in caps
    drop_delete = "delete_resource" not in caps
    drop_actions = "perform_action" not in caps

    new_resources: list[ResourceDescriptor] = []
    for resource in manifest.resources:
        new_resources.append(
            ResourceDescriptor(
                kind=resource.kind,
                label=resource.label,
                plural_label=resource.plural_label,
                id_field=resource.id_field,
                name_field=resource.name_field,
                transport=resource.transport,
                columns=resource.columns,
                empty_state=resource.empty_state,
                error_state=resource.error_state,
                list=None if drop_list else resource.list,
                detail=resource.detail,
                actions=() if drop_actions else resource.actions,
                create=None if drop_create else resource.create,
                delete=None if drop_delete else resource.delete,
                relationships=resource.relationships,
            )
        )

    listable_kinds = {r.kind for r in new_resources if r.list is not None}
    new_nav = NavSpec(
        items=tuple(item for item in manifest.nav.items if item.kind in listable_kinds)
    )

    return ConsoleManifest(
        manifest_version=manifest.manifest_version,
        product_type=manifest.product_type,
        display_name=manifest.display_name,
        nav=new_nav,
        resources=tuple(new_resources),
        operations=None if "list_operations" not in caps else manifest.operations,
        metrics=None if "metrics_summary" not in caps else manifest.metrics,
        extensions=manifest.extensions,
    )
