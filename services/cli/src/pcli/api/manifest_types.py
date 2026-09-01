"""Wire-shape mirrors of `app.adapters.manifest`'s `ConsoleManifest` schema.

Parses exactly what `GET /api/v1/console/manifests` publishes (see
`openapi/v1.yaml`'s `ProductManifestEntry`/`ConsoleManifest`/
`ResourceDescriptor`/`ColumnSpec`/... schemas) into `@dataclass(slots=True)`
objects pcli's renderer and command-discovery layer both read.

Deliberately NOT the same classes as `app.adapters.manifest`'s own
(frozen, richer) dataclasses -- pcli only ever receives the JSON-serialised
form over HTTP, so it parses that wire shape directly rather than importing
a backend-internal module. Every parser here is tolerant of an unknown
extra key (forwards-compatible with a manifest_version this build predates,
per `ConsoleManifest.manifest_version`'s own MIN/MAX-bounds contract) and
raises `ManifestError` -- never a bare `KeyError`/`TypeError` -- on a
missing REQUIRED key, so a malformed response fails with a message naming
what pcli expected instead of an opaque traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import ManifestError


def _require(body: dict[str, Any], key: str, context: str) -> Any:
    """Read a required wire field, raising a named `ManifestError` if absent."""
    try:
        return body[key]
    except KeyError as exc:
        raise ManifestError(f"{context}: missing required field {key!r}") from exc


@dataclass(slots=True, frozen=True)
class BooleanLabels:
    """Display text for a `boolean` cell's two states."""

    true_label: str
    false_label: str

    @classmethod
    def from_wire(cls, body: dict[str, Any] | None) -> BooleanLabels | None:
        """Parse a `BooleanLabels`, or return None if the wire value was null."""
        if body is None:
            return None
        return cls(true_label=body["true_label"], false_label=body["false_label"])


@dataclass(slots=True, frozen=True)
class EnumStyle:
    """One `enum_badge` value -> style-name mapping."""

    value: str
    style: str


@dataclass(slots=True, frozen=True)
class CellSpec:
    """How one column's value is rendered -- mirrors `app.adapters.manifest.CellSpec`."""

    kind: str
    unit: str | None = None
    relative: bool = False
    currency_field: str | None = None
    to_kind: str | None = None
    id_field: str | None = None
    labels: BooleanLabels | None = None
    styles: tuple[EnumStyle, ...] = field(default_factory=tuple)

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> CellSpec:
        """Parse a `CellSpec` from its wire dict."""
        return cls(
            kind=_require(body, "kind", "CellSpec"),
            unit=body.get("unit"),
            relative=bool(body.get("relative", False)),
            currency_field=body.get("currency_field"),
            to_kind=body.get("to_kind"),
            id_field=body.get("id_field"),
            labels=BooleanLabels.from_wire(body.get("labels")),
            styles=tuple(
                EnumStyle(value=s["value"], style=s["style"]) for s in body.get("styles", [])
            ),
        )


@dataclass(slots=True, frozen=True)
class ColumnSpec:
    """One column of a resource's list/detail table."""

    field: str
    label: str
    cell: CellSpec
    sortable: bool = False
    absent_as: str | None = None

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ColumnSpec:
        """Parse a `ColumnSpec` from its wire dict."""
        return cls(
            field=_require(body, "field", "ColumnSpec"),
            label=_require(body, "label", "ColumnSpec"),
            cell=CellSpec.from_wire(_require(body, "cell", "ColumnSpec")),
            sortable=bool(body.get("sortable", False)),
            absent_as=body.get("absent_as"),
        )


@dataclass(slots=True, frozen=True)
class EnvelopeSpec:
    """The ordered key-path from a proxied list response's raw body to its array."""

    keys: tuple[str, ...]

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> EnvelopeSpec:
        """Parse an `EnvelopeSpec` from its wire dict."""
        return cls(keys=tuple(_require(body, "keys", "EnvelopeSpec")))


@dataclass(slots=True, frozen=True)
class ListSpec:
    """Where a resource's collection lives and how it paginates."""

    path_bytes: str
    envelope: EnvelopeSpec
    pagination: str = "cursor"

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ListSpec:
        """Parse a `ListSpec` from its wire dict."""
        return cls(
            path_bytes=_require(body, "path_bytes", "ListSpec"),
            envelope=EnvelopeSpec.from_wire(_require(body, "envelope", "ListSpec")),
            pagination=body.get("pagination", "cursor"),
        )


@dataclass(slots=True, frozen=True)
class ItemPathSpec:
    """A resource's item-level route base. The real item path is `f"{prefix}/{id}"`."""

    prefix: str
    sample_id: str

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ItemPathSpec:
        """Parse an `ItemPathSpec` from its wire dict."""
        return cls(
            prefix=_require(body, "prefix", "ItemPathSpec"),
            sample_id=_require(body, "sample_id", "ItemPathSpec"),
        )


@dataclass(slots=True, frozen=True)
class ResourceDescriptor:
    """One resource kind: its shape, its columns, and how it is reached."""

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

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ResourceDescriptor:
        """Parse a `ResourceDescriptor` from its wire dict.

        Only the fields pcli's read path (list/get) and renderer actually
        use are kept -- `actions`/`create`/`delete`/`detail`/`relationships`
        back the mutation/detail-tab surface this PR explicitly defers (see
        the PR description's "Scope" section), so parsing them here would
        be dead weight with no consumer.
        """
        kind = _require(body, "kind", "ResourceDescriptor")
        list_body = body.get("list")
        item_path_body = body.get("item_path")
        return cls(
            kind=kind,
            label=_require(body, "label", f"ResourceDescriptor[{kind}]"),
            plural_label=_require(body, "plural_label", f"ResourceDescriptor[{kind}]"),
            id_field=_require(body, "id_field", f"ResourceDescriptor[{kind}]"),
            name_field=_require(body, "name_field", f"ResourceDescriptor[{kind}]"),
            transport=_require(body, "transport", f"ResourceDescriptor[{kind}]"),
            columns=tuple(ColumnSpec.from_wire(c) for c in body.get("columns", [])),
            empty_state=_require(body, "empty_state", f"ResourceDescriptor[{kind}]"),
            error_state=_require(body, "error_state", f"ResourceDescriptor[{kind}]"),
            list=ListSpec.from_wire(list_body) if list_body else None,
            item_path=ItemPathSpec.from_wire(item_path_body) if item_path_body else None,
        )


@dataclass(slots=True, frozen=True)
class NavItem:
    """One entry in the product's nav menu."""

    kind: str
    label: str
    icon: str | None = None


@dataclass(slots=True, frozen=True)
class ConsoleManifest:
    """The complete descriptor for one product's console screens."""

    manifest_version: int
    product_type: str
    display_name: str
    resources: tuple[ResourceDescriptor, ...]
    nav_items: tuple[NavItem, ...] = field(default_factory=tuple)

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ConsoleManifest:
        """Parse a `ConsoleManifest` from its wire dict."""
        product_type = _require(body, "product_type", "ConsoleManifest")
        nav = body.get("nav") or {}
        return cls(
            manifest_version=int(_require(body, "manifest_version", "ConsoleManifest")),
            product_type=product_type,
            display_name=_require(body, "display_name", "ConsoleManifest"),
            resources=tuple(ResourceDescriptor.from_wire(r) for r in body.get("resources", [])),
            nav_items=tuple(
                NavItem(kind=i["kind"], label=i["label"], icon=i.get("icon"))
                for i in nav.get("items", [])
            ),
        )

    def resource(self, kind: str) -> ResourceDescriptor | None:
        """The `ResourceDescriptor` named `kind`, or None if this product has none."""
        return next((r for r in self.resources if r.kind == kind), None)


@dataclass(slots=True, frozen=True)
class ProductManifestEntry:
    """One product connection's overlaid manifest, as `/console/manifests` publishes it.

    `product_id` is the CONNECTION id (see
    `app.console_manifests.ProductManifestEntry`'s own docstring) -- the
    same id `/products/{product_id}/...` routes address, not a separate
    "product type" identifier.
    """

    product_id: int
    product_type: str
    manifest: ConsoleManifest

    @classmethod
    def from_wire(cls, body: dict[str, Any]) -> ProductManifestEntry:
        """Parse a `ProductManifestEntry` from its wire dict."""
        return cls(
            product_id=int(_require(body, "product_id", "ProductManifestEntry")),
            product_type=_require(body, "product_type", "ProductManifestEntry"),
            manifest=ConsoleManifest.from_wire(_require(body, "manifest", "ProductManifestEntry")),
        )


def parse_manifests_response(body: dict[str, Any]) -> tuple[ProductManifestEntry, ...]:
    """Parse the full `GET /api/v1/console/manifests` envelope."""
    entries = body.get("manifests", [])
    return tuple(ProductManifestEntry.from_wire(e) for e in entries)
