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
    "FIELD_TYPES",
    "ManifestError",
    "CellSpec",
    "EnumStyle",
    "BooleanLabels",
    "FieldAlias",
    "ColumnSpec",
    "EnvelopeSpec",
    "ListSpec",
    "ItemPathSpec",
    "DetailSpec",
    "RelationshipSpec",
    "SelectOption",
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
#:
#: Bumped to 2 for the four gaps the generic renderer's falsification test
#: found (see this module's other docstrings for each): ``ListSpec`` retypes
#: ``envelope_key: str`` to ``envelope: EnvelopeSpec``; ``ResourceDescriptor``
#: gains ``item_path``; ``FormField.options`` retypes from ``tuple[str, ...]``
#: to ``tuple[SelectOption, ...]`` and ``field_type`` becomes a closed union;
#: ``OperationsSpec`` gains ``cancel_allowed``/``show_logs``. Every one of
#: these is a field the renderer must know about, not a manifest's own
#: content changing — exactly what this constant exists to signal.
MANIFEST_VERSION: Final[int] = 2

#: Oldest/newest ``manifest_version`` this build of the schema will serve.
#: Design §3.4: below MIN is refused explicitly (a named error, never an
#: empty screen); above MAX degrades to read-only with a banner rather than
#: taking a working product offline for a cosmetic addition. Both bounds are
#: consumed by the serving route in :mod:`app.console_manifests`, not by
#: this module — a manifest's own ``manifest_version`` is just data here.
#:
#: Both raised to 2 alongside :data:`MANIFEST_VERSION`: this module's
#: dataclasses no longer accept schema v1's shape (``ListSpec.envelope_key``
#: does not exist as a field any more), so a v1 manifest cannot even be
#: constructed against this build — MIN=2 states that fact rather than
#: leaving it implicit in a constructor signature.
MIN_MANIFEST_VERSION: Final[int] = 2
MAX_MANIFEST_VERSION: Final[int] = 2

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

#: The CLOSED set of field types a :class:`FormField` may declare. Byte-exact
#: with react-libs' own ``FieldType`` union
#: (``~/code/penguin-libs/packages/react-libs/src/components/FormBuilder/
#: types.ts``), verified by inspecting that checkout directly rather than
#: trusting the backend's own prior claim to mirror it (schema v1's
#: ``FormField`` docstring said it did; it did not — see :class:`FormField`).
#: Closed for the same reason :data:`CELL_KINDS` is: a manifest naming a
#: ``field_type`` react-libs' ``FormBuilder`` does not recognise would pass
#: schema-v1 validation and then be silently unrenderable — a "renders
#: blank" failure identical to the one :data:`CELL_KINDS` already guards
#: against for columns, now closed for form fields too.
FIELD_TYPES: Final[frozenset[str]] = frozenset(
    {
        "text",
        "email",
        "password",
        "number",
        "textarea",
        "select",
        "checkbox",
        "radio",
        "date",
        "time",
        "datetime-local",
        "tel",
        "url",
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
    """One column of a resource's list/detail table.

    ``fallback_fields`` is a schema generalisation from the Gough
    convergence (Phase 8 Step 5): ``agentColumns.tsx``'s ``hostname`` column
    renders ``String(value || row.agent_id || row.id)`` — the FIRST
    non-null of a chain of fields on the same row, not a single
    ``field`` binding. A plain ``field`` cannot express that fallback
    chain, and it is not Gough-specific (any product whose primary display
    field is sometimes absent needs the same "fall back to the id" idiom),
    so it is a column-level list here rather than a one-off on
    :class:`ResourceDescriptor`.
    """

    field: str
    label: str
    cell: CellSpec
    sortable: bool = False
    #: Required for every non-``text`` cell kind — see :data:`CELL_KINDS`
    #: and :func:`_require_absent_as`.
    absent_as: str | None = None
    #: Additional field names to try, in order, when ``field`` is null —
    #: the renderer shows the first non-null of ``[field, *fallback_fields]``.
    #: Each entry is validated the same way ``field`` is validated against
    #: an adapter's sensitive-field set: refused, never silently hidden, by
    #: :func:`validate_manifest`.
    fallback_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse an empty field/label, a malformed absent_as, or a non-identifier fallback."""
        if not self.field:
            raise ManifestError("ColumnSpec.field must not be empty")
        if not self.label:
            raise ManifestError(f"ColumnSpec {self.field!r} must declare a label")
        _require_absent_as(self.cell, self.absent_as)
        for fallback in self.fallback_fields:
            if not fallback or not fallback.isidentifier():
                raise ManifestError(
                    f"ColumnSpec {self.field!r}: fallback_fields entry {fallback!r} "
                    f"must be a plain identifier, not a computed expression or path"
                )


@dataclass(slots=True, frozen=True)
class EnvelopeSpec:
    """The exact unwrap path from a proxied collection's RAW body to its array.

    Schema v2 finding: a single ``envelope_key`` string cannot express
    Gough's real wire shapes. ``keys`` is the ordered sequence of keys to
    descend through the raw HTTP body the BROWSER receives via the byte
    proxy (not the adapter's own already-unwrapped ``GoughResponse`` —
    those are different documents; see
    :mod:`app.adapters.gough.responses`'s module docstring) to reach the
    item array:

    * ``("data", "nodes")`` for Gough nodes — ``list_nodes`` answers via
      ``_helpers.envelope_success``, which wraps the array inside an outer
      ``data`` key: ``{"status": "success", "data": {"nodes": [...]},
      "meta": {...}}``.
    * ``("groups",)`` for Gough biome_groups — BARE, despite
      ``list_biome_groups`` living in the same blueprint MODULE as
      ``list_biomes``. It answers ``jsonify({"groups": [...], "total":
      ...})`` directly, never ``envelope_success``. Verified by reading
      Gough's own source (``services/api-manager/app/api/biomes.py``) at
      ``~/code/gough``, not guessed by analogy with the enveloped
      ``biomes`` route it sits beside — that analogy is exactly the trap
      this field exists to close off.

    Never derive one resource's envelope from a sibling's shape. Two
    resources declared in the same source module can answer differently,
    and only the product's own handler code says which.
    """

    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        """Refuse an empty path or a path containing an empty key."""
        if not self.keys:
            raise ManifestError(
                "EnvelopeSpec.keys must not be empty — declare at least the "
                "final array key, e.g. ('agents',) for a bare response or "
                "('data', 'nodes') for one wrapped in an outer 'data' key"
            )
        if any(not key for key in self.keys):
            raise ManifestError(f"EnvelopeSpec.keys must not contain an empty key: {self.keys!r}")


@dataclass(slots=True, frozen=True)
class ItemPathSpec:
    """The item-level route for one resource — distinct from ``list.path_bytes``.

    Schema v2 finding: the renderer cannot safely derive an item path from
    ``list.path_bytes`` by string-munging. Gough's own item-route base
    (``_COLLECTIONS[kind]``, no trailing slash) and its LIST route
    (``_COLLECTION_ROUTES[kind]``, used by :attr:`ListSpec.path_bytes`) are
    DIFFERENT strings for three of four resources — ``biome_groups``' list
    route (``/api/v1/biomes/groups``, no trailing slash) and item-route
    base (also ``/api/v1/biomes/groups``, also no trailing slash) happen to
    be identical, while nodes/biomes/agents' list routes carry a trailing
    slash their item-route bases do not. Concatenating ``list.path_bytes``
    directly with an id therefore works for three resources and silently
    produces ``/api/v1/biomes/groups42`` for the fourth — the exact defect
    named in ``adapters/gough/manifest.py``'s module docstring. This class
    exists so the renderer never has to make that derivation at all.

    ``prefix`` is byte-equal to the adapter's own item-route base constant
    (e.g. ``app.adapters.gough.adapter._COLLECTIONS[kind]``) — never
    re-typed; import the constant. The real item path for one id is always
    ``f"{prefix}/{id}"``: ``prefix`` never carries a trailing slash, and an
    id is never embedded inside it.

    ``sample_id`` is a representative id matching the SHAPE of a real id for
    this resource (e.g. ``"1"`` for an integer id, a real UUID string for a
    UUID id) — used ONLY by :func:`validate_manifest` to prove
    ``f"{prefix}/{sample_id}"`` is admitted by the adapter's own
    ``route_allowlist``, the same proof :func:`validate_manifest` already
    performs for ``list.path_bytes``. It is never rendered and never sent
    to the product; it is a probe value, not data.
    """

    prefix: str
    sample_id: str

    def __post_init__(self) -> None:
        """Refuse a relative prefix, a trailing slash, or an empty sample id."""
        if not self.prefix.startswith("/"):
            raise ManifestError(
                f"ItemPathSpec.prefix {self.prefix!r} must be an absolute path " f"(start with '/')"
            )
        if self.prefix.endswith("/"):
            raise ManifestError(
                f"ItemPathSpec.prefix {self.prefix!r} must not end with '/' — "
                f"the item path is built as f'{{prefix}}/{{id}}', so a "
                f"trailing slash here would double up"
            )
        if not self.sample_id:
            raise ManifestError("ItemPathSpec.sample_id must not be empty")


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
    #: The unwrap path from the raw proxied body to the item array — see
    #: :class:`EnvelopeSpec`. Schema v2 retypes this from a bare
    #: ``envelope_key: str`` (Design §6.4's claim that a single key was "the
    #: ONLY declared shape a proxied read has" — false of Gough's own wire
    #: responses, see :class:`EnvelopeSpec`'s docstring).
    envelope: EnvelopeSpec
    pagination: str = "cursor"

    def __post_init__(self) -> None:
        """Refuse a relative path or an unrecognised pagination style."""
        if not self.path_bytes.startswith("/"):
            raise ManifestError(
                f"ListSpec.path_bytes {self.path_bytes!r} must be an absolute "
                f"path (start with '/') — it is matched against the proxy "
                f"allowlist and built as the adapter's own route constant"
            )
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
class SelectOption:
    """One selectable choice — mirrors react-libs' own ``SelectOption`` exactly.

    ``value`` is ``str`` here even though react-libs types it
    ``string | number``: nothing in this schema has a numeric select option
    yet, and widening to ``str | int`` is a decision to make when a real one
    shows up, not before.
    """

    value: str
    label: str
    disabled: bool = False

    def __post_init__(self) -> None:
        """Refuse an unvalued or unlabelled option."""
        if not self.value:
            raise ManifestError("SelectOption.value must not be empty")
        if not self.label:
            raise ManifestError(f"SelectOption {self.value!r} must declare a label")


@dataclass(slots=True, frozen=True)
class FormField:
    """One field of a create form — a real react-libs ``FieldConfig``, not a lookalike.

    Schema v2 finding: schema v1's docstring here claimed to mirror
    ``@penguintechinc/react-libs``' "``FormField`` shape closely enough to
    serialise straight into it" — unverified at the time, per that
    docstring, and wrong on inspection of the actual checkout
    (``~/code/penguin-libs/packages/react-libs/src/components/FormBuilder/
    types.ts``):

    1. react-libs exports NO data type named ``FormField`` at all —
       ``FormField`` there is a React component
       (``React.FC<FormFieldProps>``). The data shape a caller actually
       builds is ``FieldConfig``, consumed as ``FormConfig.fields:
       FieldConfig[]``. This class keeps the name ``FormField`` anyway —
       unlike its TypeScript mirror (``ManifestFormField`` in
       ``manifestTypes.ts``), there is no Python symbol it would collide
       with, so the rename that file needed is not needed here.
    2. ``field_type`` is now closed (:data:`FIELD_TYPES`, byte-exact with
       react-libs' own ``FieldType`` union) rather than free text — a
       manifest naming a type ``FormBuilder`` does not recognise used to
       pass validation and then be silently unrenderable; refused at
       construction instead.
    3. ``options`` is ``tuple[SelectOption, ...]``, matching
       ``FieldConfig.options: SelectOption[]`` — NOT the bare
       ``tuple[str, ...]`` schema v1 shipped, which cannot express a
       value/label split (react-libs' ``SelectOption`` always has both) and
       would need a synthetic ``options.map(o => ({value: o, label: o}))``
       mapping step at the renderer that does not exist anywhere.
    4. ``default_value`` renames schema v1's ``default`` to match react-libs'
       own ``defaultValue`` — cheap, but a real field name a caller would
       otherwise get wrong binding this to ``FormBuilder``.
    """

    name: str
    label: str
    field_type: str = "text"
    required: bool = False
    placeholder: str | None = None
    options: tuple[SelectOption, ...] = ()
    default_value: str | None = None

    def __post_init__(self) -> None:
        """Refuse an unnamed field, an unknown type, or select/radio with no options."""
        if not self.name:
            raise ManifestError("FormField.name must not be empty")
        if not self.label:
            raise ManifestError(f"FormField {self.name!r} must declare a label")
        if self.field_type not in FIELD_TYPES:
            raise ManifestError(
                f"FormField {self.name!r}: field_type {self.field_type!r} is not in "
                f"react-libs' closed FieldType union {sorted(FIELD_TYPES)} — "
                f"FormBuilder would refuse it at the type level"
            )
        if self.field_type in ("select", "radio") and not self.options:
            raise ManifestError(
                f"FormField {self.name!r}: field_type {self.field_type!r} requires "
                f"non-empty options"
            )


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
    r"""One non-CRUD verb offered on a resource row.

    ``starts_operations`` is the field :func:`validate_manifest` and Design
    §3.3 both key off: an action that starts pollable work returns
    ``ActionResult.operations``, which is unreachable through the byte
    proxy by construction, so the owning :class:`ResourceDescriptor` MUST
    be ``transport == "typed"`` whenever any of its actions sets this True.

    ``confirm`` MAY contain the literal token ``{name}`` — the renderer
    substitutes it with the acted-on row's ``name_field`` value before
    display. Gough convergence finding (Phase 8 Step 5): ``NodesPage``'s
    confirm copy is ``f"{action.confirmation} This affects node
    \"{selected.name}\"."`` — a per-row fact a manifest string, composed
    once at import time, cannot embed directly. ``{name}`` is the one
    substitution this schema authorises; no other braced token is
    interpreted (a manifest containing one renders it verbatim).
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

    ``transport`` governs the TYPED-MUTATION surface (create/edit/delete,
    and whether an operation-starting action is reachable), never reads.
    Every read in this schema version — list AND detail — goes through the
    byte proxy; that is the only read path this codebase has (see
    ``app/resources_api.py``'s module docstring: "Reads are not here").
    ``transport == "proxy"`` means "no typed mutation backing": this schema
    version declares no mechanism for a proxy-transport resource to carry a
    typed create/edit/delete, or an action whose result the portal must
    interpret (``starts_operations=True``) — both enforced below. A
    proxy-transport resource MAY still declare a plain action reachable
    through the ordinary allowlisted proxy POST (Gough's own
    ``evacuate``/``reject``/``suspend``/``resume`` all qualify).

    ``edit`` (:class:`FormSpec` or ``None``) is the exact parallel of
    ``create`` for an update: same dataclass, same field-level validation
    (``FormField.field_type`` closed to :data:`FIELD_TYPES`,
    select/radio requiring options), just posted against the existing row
    instead of a new one. Gough convergence finding (Phase 8 Step 5):
    ``BiomesPage`` opens the SAME ``FormModalBuilder`` for both "New biome"
    and "Edit biome", so a manifest resource with editable rows needs a
    form to describe here — schema v2 had no field for this at all, only
    ``create``.

    ``list`` is ``None`` for a resource with no collection endpoint at all
    (Gough's ``clusters`` — see ``adapters/gough/manifest.py`` for why it is
    NOT expressed as a ``ResourceDescriptor`` in this step; a schema finding,
    not a workaround). Schema v1 left the item path undeclared entirely — "a
    resource descriptor that DOES declare list is assumed reachable at
    ``{list.path_bytes}{id}`` by nothing in THIS module — that derivation is
    deliberately not attempted here." Schema v2 closes that gap explicitly:
    ``item_path`` (:class:`ItemPathSpec` or ``None``) is the resource's own
    declared item route, never derived by concatenating ``list.path_bytes``
    with an id — see :class:`ItemPathSpec`'s docstring for the exact defect
    that derivation produces. ``None`` means "this resource genuinely has no
    item endpoint" (Gough's ``clusters``, whose single-item route is the
    irregular ``/api/v1/clusters/{id}/lxd/status``, not
    ``{collection}/{id}``, would be the case in point — clusters stays
    unexpressed as a resource in this schema version regardless) — an
    explicit fact a manifest states, never a default a caller's omission
    falls into.
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
    item_path: ItemPathSpec | None = None
    detail: DetailSpec = field(default_factory=DetailSpec)
    actions: tuple[ActionSpec, ...] = ()
    create: FormSpec | None = None
    edit: FormSpec | None = None
    delete: DeleteSpec | None = None
    relationships: tuple[RelationshipSpec, ...] = ()

    def __post_init__(self) -> None:
        """Enforce every adapter-independent invariant Design §11.1 needs.

        Raises on: an empty identity field, an unrecognised transport, no
        columns, empty state copy, a duplicate column field, a
        ``proxy``-transport resource declaring ``create``/``edit``/``delete``
        (this schema has no typed-mutation dispatch for a proxy-transport
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
        if self.transport == "proxy" and (self.create or self.edit or self.delete):
            raise ManifestError(
                f"ResourceDescriptor {self.kind!r}: transport is 'proxy' but declares "
                f"create/edit/delete — this schema version has no typed-mutation "
                f"dispatch for a proxy-transport resource; set transport='typed' if it "
                f"really has one"
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
    """Presence + display config for the product's operations panel.

    Schema v2 finding: schema v1 carried only ``label`` and
    ``poll_interval_seconds``, so ``ManifestResourceScreen`` had no field to
    read a real capability from and always rendered a READ-ONLY panel
    (``cancelAllowed: false``, ``showLogs: false``) regardless of what the
    product actually supports — see ``useManifestOperations.ts``'s module
    doc for that gap named precisely. ``cancel_allowed``/``show_logs`` close
    it, matching the webui's own ``OperationsPanelSpec`` socket
    (``components/kit/operationsPanelTypes.ts``) field for field; ``title``
    and ``pollIntervalMs`` there are already served by ``label`` and
    ``poll_interval_seconds`` × 1000, and ``testIdPrefix`` is computed by
    the renderer per resource, not carried on the manifest.

    Both new fields are checked by :func:`validate_manifest` against the
    caller-supplied ``supports_cancel``/``supports_operation_logs`` —
    ``True`` here is a claim about the adapter's real behaviour, not a
    display preference, so an adapter with no cancellable operation kind
    must refuse a manifest that claims one exists, the same way an unknown
    action verb already refuses to load.
    """

    label: str = "Operations"
    poll_interval_seconds: int = 5
    #: Whether a live (non-terminal) operation offers a Cancel control.
    cancel_allowed: bool = False
    #: Whether an operation row offers a "Show logs" disclosure.
    show_logs: bool = False

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
    envelope_paths: Mapping[str, tuple[str, ...]] | None = None,
    supports_cancel: bool = False,
    supports_operation_logs: bool = False,
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
    * a resource's ``item_path`` (:class:`ItemPathSpec`) whose
      ``f"{prefix}/{sample_id}"`` no GET rule in
      ``adapter_cls.route_allowlist`` admits — the same proof as
      ``list.path_bytes``, schema v2's new item-path field;
    * an :class:`ActionSpec` whose ``verb`` is not in ``action_verbs`` for
      that resource kind (an unknown verb refuses to load — distinct from
      Design §3.4's client-side "hide it", which handles a renderer older
      than a valid manifest, not an invalid one);
    * a :class:`ColumnSpec` naming a field — via ``field`` OR
      ``fallback_fields`` — in ``sensitive_fields`` (refused, never hidden
      — Design §3.3's ``databaseColumns.tsx`` finding);
    * a resource's ``list.envelope`` disagreeing with the ``envelope_paths``
      entry for its kind, when the caller declares one — schema v2's
      envelope check, see :class:`EnvelopeSpec`;
    * ``manifest.operations.cancel_allowed`` or ``.show_logs`` being
      ``True`` while the caller's ``supports_cancel``/
      ``supports_operation_logs`` says the adapter offers no such
      capability — schema v2's operations-honesty check;
    * ``manifest.product_type`` disagreeing with the adapter's own
      ``PRODUCT_TYPE``.

    ``adapter_cls`` is typed against :class:`_RouteSourceAdapter`, a
    deliberately narrower Protocol than
    :class:`~app.adapters.base.Adapter` — this function reads only class-
    level ``PRODUCT_TYPE``/``route_allowlist`` and never instantiates or
    calls an adapter method, so requiring the full async Protocol would be
    an unrelated widening.

    ``action_verbs``, ``sensitive_fields``, ``envelope_paths``,
    ``supports_cancel`` and ``supports_operation_logs`` are all supplied by
    the caller rather than read off ``adapter_cls`` directly: none is part
    of the :class:`~app.adapters.base.Adapter` Protocol today (widening it
    would force every OTHER registered adapter — Nest, Tobogganing, the
    generic fallback — to declare attributes they have no present need for,
    for the sake of one product's manifest). Gough's own module-level
    ``_ACTIONS``, ``SENSITIVE_FIELDS``, ``_ENVELOPE_PATHS`` and
    ``SUPPORTS_OPERATION_CANCEL``/``SUPPORTS_OPERATION_LOGS`` are the source
    of truth this function is handed; see ``adapters/gough/manifest.py``.

    ``envelope_paths`` defaults to ``None`` (no check performed) rather than
    an empty mapping raising for every kind — the same "supplied only when
    the adapter has something non-trivial to say" idiom
    ``sensitive_fields`` already uses; a kind absent from a non-``None``
    mapping is likewise skipped, not refused, since the caller may only have
    verified some of its resources' wire shapes.
    """
    adapter_product_type = adapter_cls.PRODUCT_TYPE
    if manifest.product_type != adapter_product_type:
        raise ManifestError(
            f"manifest product_type {manifest.product_type!r} does not match "
            f"adapter_cls.PRODUCT_TYPE {adapter_product_type!r}"
        )

    allowlist = adapter_cls.route_allowlist

    if manifest.operations is not None:
        if manifest.operations.cancel_allowed and not supports_cancel:
            raise ManifestError(
                f"{manifest.product_type}: operations.cancel_allowed=True but "
                f"{adapter_cls.__name__} declares no cancellable operation kind "
                f"(supports_cancel=False) — a manifest may not promise a Cancel "
                f"control the adapter cannot honour"
            )
        if manifest.operations.show_logs and not supports_operation_logs:
            raise ManifestError(
                f"{manifest.product_type}: operations.show_logs=True but "
                f"{adapter_cls.__name__} declares no log stream "
                f"(supports_operation_logs=False) — a manifest may not promise a "
                f"Show logs control the adapter cannot honour"
            )

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
            if envelope_paths is not None and resource.kind in envelope_paths:
                expected = envelope_paths[resource.kind]
                if resource.list.envelope.keys != expected:
                    raise ManifestError(
                        f"{manifest.product_type}/{resource.kind}: list.envelope.keys "
                        f"{resource.list.envelope.keys!r} does not match the adapter's "
                        f"own real wire shape {expected!r} — a manifest may not "
                        f"declare an unwrap path the product's own response does not "
                        f"have"
                    )

        if resource.item_path is not None:
            item_path = f"{resource.item_path.prefix}/{resource.item_path.sample_id}"
            if not any(rule.matches("GET", item_path) for rule in allowlist):
                raise ManifestError(
                    f"{manifest.product_type}/{resource.kind}: item_path "
                    f"{item_path!r} is not admitted by any GET rule in "
                    f"{adapter_cls.__name__}.route_allowlist — a manifest may not "
                    f"declare an item path the adapter's proxy allowlist refuses"
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
            for fallback in column.fallback_fields:
                if fallback in sensitive_fields:
                    raise ManifestError(
                        f"{manifest.product_type}/{resource.kind}: column "
                        f"{column.field!r} fallback_fields names a field "
                        f"{adapter_cls.__name__} marks sensitive ({fallback!r}) — "
                        f"refused, not hidden, per Design §3.3"
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
    ``get_resource``       every resource's ``item_path`` is dropped (None)
    ``create_resource``    every resource's ``create`` is dropped (None)
    ``update_resource``    every resource's ``edit`` is dropped (None)
    ``delete_resource``    every resource's ``delete`` is dropped (None)
    ``perform_action``     every resource's ``actions`` is emptied
    ``metrics_summary``    ``manifest.metrics`` is dropped (None)
    ``list_operations``    ``manifest.operations`` is dropped (None)
    ``cancel_operation``   ``operations.cancel_allowed`` forced False
    ``operation_logs``     ``operations.show_logs`` forced False
    =====================  ===============================================

    Nav items left pointing at a now-list-less resource are dropped from
    ``nav.items`` in the same pass, so the returned manifest still satisfies
    :meth:`ConsoleManifest.__post_init__`'s nav/resource agreement — this
    function reconstructs (not mutates) every level it touches, so the
    result is itself a valid, re-checkable :class:`ConsoleManifest`.
    """
    caps = frozenset(capabilities)
    drop_list = "list_resources" not in caps
    drop_item_path = "get_resource" not in caps
    drop_create = "create_resource" not in caps
    drop_edit = "update_resource" not in caps
    drop_delete = "delete_resource" not in caps
    drop_actions = "perform_action" not in caps
    drop_cancel = "cancel_operation" not in caps
    drop_logs = "operation_logs" not in caps

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
                item_path=None if drop_item_path else resource.item_path,
                detail=resource.detail,
                actions=() if drop_actions else resource.actions,
                create=None if drop_create else resource.create,
                edit=None if drop_edit else resource.edit,
                delete=None if drop_delete else resource.delete,
                relationships=resource.relationships,
            )
        )

    listable_kinds = {r.kind for r in new_resources if r.list is not None}
    new_nav = NavSpec(
        items=tuple(item for item in manifest.nav.items if item.kind in listable_kinds)
    )

    new_operations: OperationsSpec | None = None
    if "list_operations" in caps and manifest.operations is not None:
        new_operations = OperationsSpec(
            label=manifest.operations.label,
            poll_interval_seconds=manifest.operations.poll_interval_seconds,
            cancel_allowed=False if drop_cancel else manifest.operations.cancel_allowed,
            show_logs=False if drop_logs else manifest.operations.show_logs,
        )

    return ConsoleManifest(
        manifest_version=manifest.manifest_version,
        product_type=manifest.product_type,
        display_name=manifest.display_name,
        nav=new_nav,
        resources=tuple(new_resources),
        operations=new_operations,
        metrics=None if "metrics_summary" not in caps else manifest.metrics,
        extensions=manifest.extensions,
    )
