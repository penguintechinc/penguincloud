"""Fail-closed proof for the Design §11.1 manifest schema.

Two things this file proves, in order:

1. **The structural layer cannot be bypassed by construction.** Every
   ``__post_init__`` rule in :mod:`app.adapters.manifest` has a negative
   test here that builds the SMALLEST invalid object the rule is meant to
   reject and asserts it raises :class:`~app.adapters.manifest.ManifestError`
   with the red output pasted in the accompanying report — a check that
   passes everything proves nothing (Design §11.1's own acceptance bar).
2. **The adapter-aware layer (`validate_manifest`) is independently live**,
   using a minimal FAKE adapter class built in this file rather than the
   real Gough one, so these tests do not depend on Gough's route table
   staying exactly as it is today — only on the CONTRACT
   :func:`~app.adapters.manifest.validate_manifest` enforces.

Separate from ``test_gough_manifest_conformance.py``, which parametrises the
same layer over :data:`app.adapters.MANIFEST_REGISTRY` — the real, derived
set of registered manifests, not a hand list (see that module's docstring).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from app.adapters.base import RouteRule, product_scope
from app.adapters.manifest import (
    FIELD_TYPES,
    ActionSpec,
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    DeleteSpec,
    EnvelopeSpec,
    ExtensionSlot,
    FormField,
    FormSpec,
    ItemPathSpec,
    ListSpec,
    ManifestError,
    NavItem,
    NavSpec,
    OperationsSpec,
    RelationshipSpec,
    ResourceDescriptor,
    SelectOption,
    apply_capabilities_overlay,
    validate_manifest,
)


def _text_column(field: str = "name") -> ColumnSpec:
    return ColumnSpec(field=field, label=field.title(), cell=CellSpec(kind="text"))


_BASE_RESOURCE: ResourceDescriptor = ResourceDescriptor(
    kind="widgets",
    label="Widget",
    plural_label="Widgets",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=(_text_column("id"), _text_column("name")),
    empty_state="No widgets.",
    error_state="Unable to load widgets.",
)


def _minimal_resource(**overrides: Any) -> ResourceDescriptor:
    """The smallest resource that passes every rule.

    A test can override exactly the one field it means to break.
    """
    return dataclasses.replace(_BASE_RESOURCE, **overrides)


# ---------------------------------------------------------------------------
# CellSpec — closed union + required companions
# ---------------------------------------------------------------------------


def test_unknown_cell_kind_is_refused() -> None:
    """Unknown cell kind is refused."""
    with pytest.raises(ManifestError, match="not in the closed set"):
        CellSpec(kind="html")  # not in CELL_KINDS — see the design's §4.1 note


def test_enum_badge_without_styles_is_refused() -> None:
    """Enum badge without styles is refused."""
    with pytest.raises(ManifestError, match="enum_badge' requires non-empty styles"):
        CellSpec(kind="enum_badge")


def test_money_without_currency_field_is_refused() -> None:
    """Money without currency field is refused."""
    with pytest.raises(ManifestError, match="'money' requires currency_field"):
        CellSpec(kind="money")


def test_boolean_without_labels_is_refused() -> None:
    """Boolean without labels is refused."""
    with pytest.raises(ManifestError, match="'boolean' requires labels"):
        CellSpec(kind="boolean")


def test_link_without_to_kind_or_id_field_is_refused() -> None:
    """Link without to kind or id field is refused."""
    with pytest.raises(ManifestError, match="'link' requires to_kind and id_field"):
        CellSpec(kind="link")


# ---------------------------------------------------------------------------
# ColumnSpec — absent_as is required on every non-text column (Design §3.3)
# ---------------------------------------------------------------------------


def test_missing_absent_as_on_a_non_text_column_is_refused() -> None:
    """Missing absent as on a non text column is refused."""
    with pytest.raises(ManifestError, match="must declare absent_as"):
        ColumnSpec(field="size", label="Size", cell=CellSpec(kind="number", unit="MB"))


def test_text_column_may_omit_absent_as() -> None:
    """Text column may omit absent as."""
    # The one exception: absence and empty-string already look identical.
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text"))


def test_malformed_absent_as_spelling_is_refused() -> None:
    """Malformed absent as spelling is refused."""
    with pytest.raises(ManifestError, match="is not 'dash', 'zero', or 'literal"):
        ColumnSpec(
            field="size",
            label="Size",
            cell=CellSpec(kind="number", unit="MB"),
            absent_as="none",
        )


# ---------------------------------------------------------------------------
# ResourceDescriptor — proxy transport has no typed-mutation dispatch
# ---------------------------------------------------------------------------


def test_proxy_transport_with_create_is_refused() -> None:
    """Proxy transport with create is refused."""
    with pytest.raises(ManifestError, match="declares create/edit/delete"):
        _minimal_resource(
            transport="proxy",
            create=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Go"),
        )


def test_proxy_transport_with_edit_is_refused() -> None:
    """Proxy transport with edit is refused — the exact parallel of create/delete."""
    with pytest.raises(ManifestError, match="declares create/edit/delete"):
        _minimal_resource(
            transport="proxy",
            edit=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Save"),
        )


def test_proxy_transport_with_delete_is_refused() -> None:
    """Proxy transport with delete is refused."""
    with pytest.raises(ManifestError, match="declares create/edit/delete"):
        _minimal_resource(transport="proxy", delete=DeleteSpec(confirm="Delete?"))


def test_proxy_transport_with_an_operation_starting_action_is_refused() -> None:
    """Design §3.3's named rule, exactly as written: starts_operations ⇒ typed."""
    with pytest.raises(ManifestError, match="starts_operations=True but transport"):
        _minimal_resource(
            transport="proxy",
            actions=(ActionSpec(verb="deploy", label="Deploy", starts_operations=True),),
        )


def test_proxy_transport_with_a_plain_action_is_allowed() -> None:
    """A plain action is reachable through the ordinary proxy allowlist.

    So proxy transport must not blanket-forbid every action — only the one
    Design §3.3 actually names (an operation-starting one).
    """
    resource = _minimal_resource(
        transport="proxy",
        actions=(ActionSpec(verb="suspend", label="Suspend"),),
    )
    assert resource.actions[0].verb == "suspend"


# ---------------------------------------------------------------------------
# ConsoleManifest — nav must agree with declared, listable resources
# ---------------------------------------------------------------------------


def test_nav_item_naming_an_undeclared_resource_is_refused() -> None:
    """Nav item naming an undeclared resource is refused."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",)))
    )
    with pytest.raises(ManifestError, match="does not declare"):
        ConsoleManifest(
            manifest_version=1,
            product_type="acme",
            display_name="Acme",
            nav=NavSpec(items=(NavItem(kind="gizmos", label="Gizmos"),)),
            resources=(resource,),
        )


def test_nav_item_pointing_at_a_list_less_resource_is_refused() -> None:
    """Nav item pointing at a list less resource is refused."""
    resource = _minimal_resource(kind="widgets", list=None)
    with pytest.raises(ManifestError, match="no list endpoint"):
        ConsoleManifest(
            manifest_version=1,
            product_type="acme",
            display_name="Acme",
            nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
            resources=(resource,),
        )


def test_extension_budget_of_two_per_product_is_enforced() -> None:
    """Extension budget of two per product is enforced."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",)))
    )
    slots = tuple(
        ExtensionSlot(slot="detail_tab", id=f"acme.slot{i}", label=f"Slot {i}") for i in range(3)
    )
    with pytest.raises(ManifestError, match="exceeds the Design §4.1 budget"):
        ConsoleManifest(
            manifest_version=1,
            product_type="acme",
            display_name="Acme",
            nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
            resources=(resource,),
            extensions=slots,
        )


# ---------------------------------------------------------------------------
# validate_manifest -- adapter-aware conformance, against a FAKE adapter
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """The minimal shape validate_manifest needs: PRODUCT_TYPE + route_allowlist."""

    PRODUCT_TYPE = "acme"
    route_allowlist: list[RouteRule] = [
        RouteRule("GET", r"^/api/v1/widgets/?\Z", product_scope("acme", "read")),
        RouteRule("GET", r"^/api/v1/widgets/\d+\Z", product_scope("acme", "read")),
    ]


def _fake_manifest(
    resource: ResourceDescriptor, operations: OperationsSpec | None = None
) -> ConsoleManifest:
    return ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind=resource.kind, label=resource.label),))
        if resource.list is not None
        else NavSpec(items=()),
        resources=(resource,),
        operations=operations,
    )


def test_a_read_path_the_allowlist_does_not_admit_refuses_to_load() -> None:
    """Design §11.1's own headline example.

    A manifest naming a route the adapter's route_allowlist does not admit
    must refuse to load.
    """
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(
            path_bytes="/api/v1/widgets/secret-admin-panel/",
            envelope=EnvelopeSpec(keys=("widgets",)),
        ),
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={})


def test_an_admitted_read_path_loads_cleanly() -> None:
    """An admitted read path loads cleanly."""
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = _fake_manifest(resource)
    validate_manifest(manifest, _FakeAdapter, action_verbs={})  # must not raise


def test_an_item_path_the_allowlist_does_not_admit_refuses_to_load() -> None:
    """Schema v2's item-path proof, parallel to list.path_bytes' own.

    A manifest naming an item route the adapter's route_allowlist does not
    admit must refuse to load, exactly like an unadmitted list path.
    """
    resource = _minimal_resource(
        transport="proxy",
        item_path=ItemPathSpec(prefix="/api/v1/widgets/secret-admin-panel", sample_id="1"),
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="item_path .* is not admitted by any GET rule"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={})


def test_an_admitted_item_path_loads_cleanly() -> None:
    """An admitted item path loads cleanly."""
    resource = _minimal_resource(
        transport="proxy",
        item_path=ItemPathSpec(prefix="/api/v1/widgets", sample_id="1"),
    )
    manifest = _fake_manifest(resource)
    validate_manifest(manifest, _FakeAdapter, action_verbs={})  # must not raise


def test_an_envelope_not_matching_the_adapters_declared_shape_refuses_to_load() -> None:
    """Schema v2's envelope-honesty proof.

    A manifest claiming a bare envelope for a resource the adapter says is
    really wrapped in an outer ``data`` key (or vice versa) must refuse to
    load — exactly the ``biome_groups`` trap ``EnvelopeSpec`` exists to
    close, reproduced generically against the fake adapter.
    """
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="does not match the adapter's own real wire shape"):
        validate_manifest(
            manifest,
            _FakeAdapter,
            action_verbs={},
            envelope_paths={"widgets": ("data", "widgets")},
        )


def test_a_matching_envelope_loads_cleanly() -> None:
    """A declared envelope matching the adapter's own shape loads cleanly."""
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(
            path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("data", "widgets"))
        ),
    )
    manifest = _fake_manifest(resource)
    validate_manifest(
        manifest,
        _FakeAdapter,
        action_verbs={},
        envelope_paths={"widgets": ("data", "widgets")},
    )  # must not raise


def test_an_unlisted_kind_in_envelope_paths_is_not_checked() -> None:
    """A kind absent from a supplied envelope_paths mapping is skipped, not refused.

    ``envelope_paths`` may cover only some of an adapter's resources (the
    caller may only have verified some of them) — a kind it says nothing
    about must not be treated as a mismatch.
    """
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("anything",))),
    )
    manifest = _fake_manifest(resource)
    validate_manifest(
        manifest, _FakeAdapter, action_verbs={}, envelope_paths={}
    )  # must not raise -- "widgets" is not a key in envelope_paths


def test_operations_cancel_allowed_with_no_adapter_support_refuses_to_load() -> None:
    """Schema v2's cancel-honesty proof.

    A manifest may not declare ``operations.cancel_allowed=True`` when the
    adapter offers no cancellable operation kind.
    """
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = _fake_manifest(resource, operations=OperationsSpec(cancel_allowed=True))
    with pytest.raises(ManifestError, match="operations.cancel_allowed=True but"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={}, supports_cancel=False)


def test_operations_show_logs_with_no_adapter_support_refuses_to_load() -> None:
    """A manifest may not declare ``operations.show_logs=True`` with no adapter log stream."""
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = _fake_manifest(resource, operations=OperationsSpec(show_logs=True))
    with pytest.raises(ManifestError, match="operations.show_logs=True but"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={}, supports_operation_logs=False)


def test_operations_cancel_allowed_with_adapter_support_loads_cleanly() -> None:
    """A manifest's cancel_allowed/show_logs claim loads cleanly when the adapter backs it."""
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/api/v1/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = _fake_manifest(
        resource, operations=OperationsSpec(cancel_allowed=True, show_logs=True)
    )
    validate_manifest(
        manifest,
        _FakeAdapter,
        action_verbs={},
        supports_cancel=True,
        supports_operation_logs=True,
    )  # must not raise


def test_an_action_verb_the_adapter_does_not_implement_refuses_to_load() -> None:
    """An action verb the adapter does not implement refuses to load."""
    resource = _minimal_resource(
        transport="typed", actions=(ActionSpec(verb="teleport", label="Teleport"),)
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="is not one _FakeAdapter implements"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={"widgets": frozenset({"reboot"})})


def test_a_real_action_verb_loads_cleanly() -> None:
    """A real action verb loads cleanly."""
    resource = _minimal_resource(
        transport="typed", actions=(ActionSpec(verb="reboot", label="Reboot"),)
    )
    manifest = _fake_manifest(resource)
    validate_manifest(manifest, _FakeAdapter, action_verbs={"widgets": frozenset({"reboot"})})


def test_a_sensitive_field_named_in_a_column_is_refused_not_hidden() -> None:
    """A sensitive field named in a column is refused not hidden."""
    resource = _minimal_resource(
        columns=(_text_column("id"), _text_column("import_conn_str")),
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="marks sensitive — refused, not hidden"):
        validate_manifest(
            manifest,
            _FakeAdapter,
            action_verbs={},
            sensitive_fields=frozenset({"import_conn_str"}),
        )


def test_a_sensitive_field_named_in_a_columns_fallback_fields_is_refused_not_hidden() -> None:
    """The ``fallback_fields`` refusal is the same rule as ``field``'s, not a loophole.

    Gough convergence finding (Phase 8 Step 5): ``agentColumns.tsx``'s
    hostname fallback chain reads ``row.agent_id`` then ``row.id`` when
    ``hostname`` is absent. A fallback chain that silently reached a
    sensitive field would leak it into a rendered cell exactly as surely as
    naming it in ``field`` would — this proves the gate bites there too,
    not just on the primary field.
    """
    resource = _minimal_resource(
        columns=(
            _text_column("id"),
            ColumnSpec(
                field="hostname",
                label="Hostname",
                cell=CellSpec(kind="text"),
                fallback_fields=("agent_id", "secret_token"),
            ),
        ),
    )
    manifest = _fake_manifest(resource)
    with pytest.raises(ManifestError, match="fallback_fields names a field .* marks sensitive"):
        validate_manifest(
            manifest,
            _FakeAdapter,
            action_verbs={},
            sensitive_fields=frozenset({"secret_token"}),
        )


def test_a_non_sensitive_fallback_chain_loads_cleanly() -> None:
    """The positive case for the fallback-fields sensitive-field gate."""
    resource = _minimal_resource(
        columns=(
            _text_column("id"),
            ColumnSpec(
                field="hostname",
                label="Hostname",
                cell=CellSpec(kind="text"),
                fallback_fields=("agent_id", "id"),
            ),
        ),
    )
    manifest = _fake_manifest(resource)
    validate_manifest(
        manifest, _FakeAdapter, action_verbs={}, sensitive_fields=frozenset({"secret_token"})
    )  # must not raise


def test_product_type_mismatch_between_manifest_and_adapter_refuses_to_load() -> None:
    """Product type mismatch between manifest and adapter refuses to load."""
    resource = _minimal_resource()
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="not-acme",
        display_name="Not Acme",
        nav=NavSpec(items=()),
        resources=(resource,),
    )
    with pytest.raises(ManifestError, match="does not match adapter_cls.PRODUCT_TYPE"):
        validate_manifest(manifest, _FakeAdapter, action_verbs={})


# ---------------------------------------------------------------------------
# apply_capabilities_overlay -- subtract-only
# ---------------------------------------------------------------------------


def test_overlay_strips_create_when_capability_is_missing() -> None:
    """Overlay strips create when capability is missing."""
    resource = _minimal_resource(
        transport="typed",
        create=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Go"),
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
        resources=(resource,),
    )
    overlaid = apply_capabilities_overlay(manifest, ["list_resources"])
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.create is None
    # Never regains what the committed manifest did not declare in the first place.
    assert got.delete is None


def test_overlay_strips_edit_when_capability_is_missing() -> None:
    """Overlay strips edit when update_resource capability is missing -- create's exact parallel."""
    resource = _minimal_resource(
        transport="typed",
        edit=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Save"),
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
        resources=(resource,),
    )
    overlaid = apply_capabilities_overlay(manifest, ["list_resources"])  # no "update_resource"
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.edit is None


def test_overlay_keeps_edit_when_capability_is_present() -> None:
    """The subtraction is conditional -- proves the positive case for edit too."""
    resource = _minimal_resource(
        transport="typed",
        edit=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Save"),
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
        resources=(resource,),
    )
    overlaid = apply_capabilities_overlay(manifest, ["list_resources", "update_resource"])
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.edit == resource.edit


def test_overlay_never_adds_a_capability_the_manifest_did_not_declare() -> None:
    """Overlay never adds a capability the manifest did not declare."""
    resource = _minimal_resource(
        transport="proxy",
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
    )
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
        resources=(resource,),
    )
    # Every capability present -- the overlay must still not manufacture a
    # create/edit/delete/actions surface the committed manifest never declared.
    overlaid = apply_capabilities_overlay(
        manifest,
        [
            "list_resources",
            "create_resource",
            "update_resource",
            "delete_resource",
            "perform_action",
        ],
    )
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.create is None
    assert got.edit is None
    assert got.delete is None
    assert got.actions == ()


def test_overlay_drops_nav_items_whose_resource_lost_its_list() -> None:
    """Overlay drops nav items whose resource lost its list."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",)))
    )
    manifest = ConsoleManifest(
        manifest_version=1,
        product_type="acme",
        display_name="Acme",
        nav=NavSpec(items=(NavItem(kind="widgets", label="Widgets"),)),
        resources=(resource,),
    )
    overlaid = apply_capabilities_overlay(manifest, [])  # no capabilities at all
    assert overlaid.nav.items == ()
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.list is None


def test_overlay_strips_item_path_when_get_resource_capability_is_missing() -> None:
    """Schema v2's item_path is subtract-only, matching every other field here."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
        item_path=ItemPathSpec(prefix="/widgets", sample_id="1"),
    )
    manifest = _fake_manifest(resource)
    overlaid = apply_capabilities_overlay(manifest, ["list_resources"])  # no "get_resource"
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.item_path is None


def test_overlay_keeps_item_path_when_get_resource_capability_is_present() -> None:
    """The subtraction is conditional, not unconditional -- proves the positive case too."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",))),
        item_path=ItemPathSpec(prefix="/widgets", sample_id="1"),
    )
    manifest = _fake_manifest(resource)
    overlaid = apply_capabilities_overlay(manifest, ["list_resources", "get_resource"])
    got = overlaid.resource("widgets")
    assert got is not None
    assert got.item_path == resource.item_path


def test_overlay_forces_cancel_allowed_and_show_logs_false_when_capabilities_are_missing() -> None:
    """A live connection that has lost cancel/log capability must lose the claim too.

    Otherwise the overlay -- whose entire contract is "never gain, only
    lose" -- would let a degraded connection keep advertising a Cancel
    control it can no longer honour.
    """
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",)))
    )
    manifest = _fake_manifest(
        resource, operations=OperationsSpec(cancel_allowed=True, show_logs=True)
    )
    overlaid = apply_capabilities_overlay(manifest, ["list_resources", "list_operations"])
    assert overlaid.operations is not None
    assert overlaid.operations.cancel_allowed is False
    assert overlaid.operations.show_logs is False


def test_overlay_keeps_cancel_allowed_and_show_logs_when_capabilities_are_present() -> None:
    """The subtraction is conditional -- proves the positive case for operations too."""
    resource = _minimal_resource(
        list=ListSpec(path_bytes="/widgets/", envelope=EnvelopeSpec(keys=("widgets",)))
    )
    manifest = _fake_manifest(
        resource, operations=OperationsSpec(cancel_allowed=True, show_logs=True)
    )
    overlaid = apply_capabilities_overlay(
        manifest,
        ["list_resources", "list_operations", "cancel_operation", "operation_logs"],
    )
    assert overlaid.operations is not None
    assert overlaid.operations.cancel_allowed is True
    assert overlaid.operations.show_logs is True


# ---------------------------------------------------------------------------
# Trivial-guard sweep -- every remaining "must not be empty"/"must be a
# recognised value" branch, one assertion each. Compact on purpose: these
# are defensive completeness, not the security-relevant rules the file's
# docstring is about, so they share a terse table-driven style rather than
# a named test per line.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"field": "", "label": "X"}, "field must not be empty"),
        ({"field": "x", "label": ""}, "must declare a label"),
        (
            {"field": "x", "label": "X", "fallback_fields": ("",)},
            "must be a plain identifier",
        ),
        (
            {"field": "x", "label": "X", "fallback_fields": ("row.id",)},
            "must be a plain identifier",
        ),
        (
            {"field": "x", "label": "X", "fallback_fields": ("row['id']",)},
            "must be a plain identifier",
        ),
    ],
)
def test_column_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """ColumnSpec refuses an empty field/label or a non-identifier fallback field."""
    with pytest.raises(ManifestError, match=match):
        ColumnSpec(cell=CellSpec(kind="text"), **kwargs)


def test_column_spec_with_plain_identifier_fallback_fields_loads_cleanly() -> None:
    """The positive case: real field names construct cleanly as fallback_fields."""
    column = ColumnSpec(
        field="hostname",
        label="Hostname",
        cell=CellSpec(kind="text"),
        fallback_fields=("agent_id", "id"),
    )
    assert column.fallback_fields == ("agent_id", "id")


@pytest.mark.parametrize(
    "kwargs, match",
    [
        (
            {"path_bytes": "widgets/", "envelope": EnvelopeSpec(keys=("w",))},
            "must be an absolute path",
        ),
        (
            {
                "path_bytes": "/widgets/",
                "envelope": EnvelopeSpec(keys=("w",)),
                "pagination": "bogus",
            },
            "is not one of",
        ),
    ],
)
def test_list_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """ListSpec refuses a relative path or a bad pagination style."""
    with pytest.raises(ManifestError, match=match):
        ListSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"keys": ()}, "keys must not be empty"),
        ({"keys": ("data", "")}, "must not contain an empty key"),
    ],
)
def test_envelope_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """EnvelopeSpec refuses an empty path or a path containing an empty key."""
    with pytest.raises(ManifestError, match=match):
        EnvelopeSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"prefix": "widgets", "sample_id": "1"}, "must be an absolute path"),
        ({"prefix": "/widgets/", "sample_id": "1"}, "must not end with '/'"),
        ({"prefix": "/widgets", "sample_id": ""}, "sample_id must not be empty"),
    ],
)
def test_item_path_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """ItemPathSpec refuses a relative or trailing-slash prefix, or an empty sample id."""
    with pytest.raises(ManifestError, match=match):
        ItemPathSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [{"child_kind": "", "parent_field": "p"}, {"child_kind": "c", "parent_field": ""}],
)
def test_relationship_spec_trivial_guards(kwargs: dict[str, Any]) -> None:
    """RelationshipSpec refuses a half-declared edge."""
    with pytest.raises(ManifestError, match="requires both child_kind and parent_field"):
        RelationshipSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"name": "", "label": "X"}, "name must not be empty"),
        ({"name": "x", "label": ""}, "must declare a label"),
    ],
)
def test_form_field_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """FormField refuses an empty name or label."""
    with pytest.raises(ManifestError, match=match):
        FormField(**kwargs)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"value": "", "label": "X"}, "value must not be empty"),
        ({"value": "x", "label": ""}, "must declare a label"),
    ],
)
def test_select_option_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """SelectOption refuses an unvalued or unlabelled option."""
    with pytest.raises(ManifestError, match=match):
        SelectOption(**kwargs)


def test_form_field_with_a_field_type_outside_react_libs_union_is_refused() -> None:
    """Schema v2's react-libs-conformance proof.

    ``field_type`` must be one of react-libs' own closed ``FieldType``
    union (:data:`FIELD_TYPES`) — a manifest naming anything else would be
    silently unrenderable by ``FormBuilder``, so it is refused at
    construction instead.
    """
    assert "html" not in FIELD_TYPES
    with pytest.raises(ManifestError, match="not in react-libs' closed FieldType union"):
        FormField(name="x", label="X", field_type="html")


def test_form_field_with_every_real_field_type_is_accepted() -> None:
    """Every real react-libs FieldType is accepted -- proves the union isn't over-tight."""
    for field_type in sorted(FIELD_TYPES - {"select", "radio"}):
        FormField(name="x", label="X", field_type=field_type)


def test_select_field_type_with_no_options_is_refused() -> None:
    """A ``select``/``radio`` field with no options would render an empty control."""
    with pytest.raises(ManifestError, match="requires non-empty options"):
        FormField(name="x", label="X", field_type="select")


def test_select_field_type_with_options_loads_cleanly() -> None:
    """A select field with real SelectOptions constructs cleanly."""
    field = FormField(
        name="x",
        label="X",
        field_type="select",
        options=(SelectOption(value="a", label="A"), SelectOption(value="b", label="B")),
    )
    assert field.options[0].value == "a"


def test_form_spec_with_no_fields_is_refused() -> None:
    """FormSpec refuses an empty field list."""
    with pytest.raises(ManifestError, match="fields must not be empty"):
        FormSpec(fields=(), submit_label="Go")


def test_form_spec_with_no_submit_label_is_refused() -> None:
    """FormSpec refuses an empty submit label."""
    with pytest.raises(ManifestError, match="submit_label must not be empty"):
        FormSpec(fields=(FormField(name="n", label="N"),), submit_label="")


# ---------------------------------------------------------------------------
# ResourceDescriptor.edit -- exact parallel of .create
# ---------------------------------------------------------------------------


def test_resource_descriptor_edit_is_validated_the_same_way_as_create() -> None:
    """``edit`` runs through the identical FormSpec/FormField construction as ``create``.

    Proves the "same __post_init__ validation as create" claim directly: a
    field_type outside react-libs' closed union refuses to load whether it
    is declared on ``create`` or ``edit``.
    """
    with pytest.raises(ManifestError, match="not in react-libs' closed FieldType union"):
        _minimal_resource(
            transport="typed",
            edit=FormSpec(
                fields=(FormField(name="x", label="X", field_type="html"),),
                submit_label="Save",
            ),
        )


def test_resource_descriptor_edit_with_a_real_form_loads_cleanly() -> None:
    """A well-formed edit FormSpec loads cleanly, independent of create."""
    resource = _minimal_resource(
        transport="typed",
        edit=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Save"),
    )
    assert resource.edit is not None
    assert resource.edit.submit_label == "Save"
    assert resource.create is None  # edit does not imply create


def test_resource_descriptor_with_edit_and_create_and_delete_all_declared() -> None:
    """A resource may declare create, edit and delete independently."""
    resource = _minimal_resource(
        transport="typed",
        create=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Create"),
        edit=FormSpec(fields=(FormField(name="name", label="Name"),), submit_label="Save"),
        delete=DeleteSpec(confirm="Delete?"),
    )
    assert resource.create is not None
    assert resource.edit is not None
    assert resource.delete is not None


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"verb": "", "label": "X"}, "verb must not be empty"),
        ({"verb": "x", "label": ""}, "must declare a label"),
        ({"verb": "x", "label": "X", "requires": "bogus"}, "not one of"),
        (
            {"verb": "x", "label": "X", "enabled_when_field": "state"},
            "must be declared together or not at all",
        ),
    ],
)
def test_action_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """ActionSpec refuses an empty verb/label, a bad scope, or a half predicate."""
    with pytest.raises(ManifestError, match=match):
        ActionSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"confirm": ""}, "confirm must not be empty"),
        ({"confirm": "Delete?", "requires": "bogus"}, "not one of"),
    ],
)
def test_delete_spec_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """DeleteSpec refuses an empty confirm or a bad scope."""
    with pytest.raises(ManifestError, match=match):
        DeleteSpec(**kwargs)


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"kind": ""}, "kind must not be empty"),
        ({"transport": "bogus"}, "is not 'proxy' or 'typed'"),
        ({"id_field": ""}, "must declare id_field and name_field"),
        ({"columns": ()}, "must declare columns"),
        ({"empty_state": ""}, "must declare empty_state and error_state"),
        (
            {"columns": (_text_column("id"), _text_column("id"))},
            "has duplicate column fields",
        ),
    ],
)
def test_resource_descriptor_trivial_guards(overrides: dict[str, Any], match: str) -> None:
    """ResourceDescriptor refuses the remaining empty/invalid field cases."""
    with pytest.raises(ManifestError, match=match):
        _minimal_resource(**overrides)


def test_operations_spec_with_non_positive_interval_is_refused() -> None:
    """OperationsSpec refuses a zero or negative poll interval."""
    with pytest.raises(ManifestError, match="must be positive"):
        OperationsSpec(poll_interval_seconds=0)


def test_extension_slot_with_an_unknown_kind_is_refused() -> None:
    """ExtensionSlot refuses a slot kind outside the closed set."""
    with pytest.raises(ManifestError, match="is not one of"):
        ExtensionSlot(slot="bogus", id="acme.x", label="X")


def test_extension_slot_with_an_empty_id_is_refused() -> None:
    """ExtensionSlot refuses an unnamed slot."""
    with pytest.raises(ManifestError, match="id must not be empty"):
        ExtensionSlot(slot="page", id="", label="X")


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"manifest_version": 0}, "manifest_version must be >= 1"),
        ({"product_type": ""}, "product_type must not be empty"),
        ({"resources": ()}, "resources must not be empty"),
    ],
)
def test_console_manifest_trivial_guards(kwargs: dict[str, Any], match: str) -> None:
    """ConsoleManifest refuses the remaining empty/invalid top-level cases."""
    defaults: dict[str, Any] = {
        "manifest_version": 1,
        "product_type": "acme",
        "display_name": "Acme",
        "nav": NavSpec(items=()),
        "resources": (_minimal_resource(),),
    }
    defaults.update(kwargs)
    with pytest.raises(ManifestError, match=match):
        ConsoleManifest(**defaults)


def test_console_manifest_with_duplicate_resource_kinds_is_refused() -> None:
    """ConsoleManifest refuses two resources declaring the same kind."""
    resource = _minimal_resource()
    with pytest.raises(ManifestError, match="duplicate resource kinds"):
        ConsoleManifest(
            manifest_version=1,
            product_type="acme",
            display_name="Acme",
            nav=NavSpec(items=()),
            resources=(resource, resource),
        )
