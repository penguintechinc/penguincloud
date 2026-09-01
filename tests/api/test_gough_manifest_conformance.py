"""Derived conformance over every REGISTERED manifest — Design §11.1.

Parametrised over :data:`app.adapters.MANIFEST_REGISTRY`, not a hand list —
a future product's manifest (Nest, Tobogganing) inherits every check here
the moment it registers, the same move ``test_gate_coverage_is_derived.py``
and ``test_adapter_registry.py`` already make for their own obligations.
Today the registry has one entry (Gough), so these tests are also, in
effect, Gough-specific — but nothing here names Gough directly except the
adapter-lookup table used to re-run :func:`validate_manifest` per product.

Generalises ``test_gough_webui_paths.py``'s core assertion (the collection
path a manifest declares must be byte-equal to the adapter's own route
constant, trailing slash included) to every manifest resource with a
``list``, rather than the three the webui happens to fetch today.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest
from app.adapters import ADAPTER_REGISTRY, MANIFEST_REGISTRY
from app.adapters.gough.adapter import _ACTIONS as _GOUGH_ACTIONS
from app.adapters.gough.adapter import _COLLECTION_ROUTES as _GOUGH_COLLECTION_ROUTES
from app.adapters.gough.adapter import GoughAdapter
from app.adapters.gough.manifest import _ENVELOPE_PATHS as _GOUGH_ENVELOPE_PATHS
from app.adapters.manifest import _RouteSourceAdapter, apply_capabilities_overlay, validate_manifest
from app.adapters.tobogganing.adapter import TobogganingAdapter
from app.adapters.tobogganing.manifest import _ACTION_VERBS as _TOBOGGANING_ACTION_VERBS
from app.adapters.tobogganing.manifest import _ENVELOPE_PATHS as _TOBOGGANING_ENVELOPE_PATHS
from app.adapters.waddleai.adapter import WaddleAIAdapter
from app.adapters.waddleai.manifest import _ACTION_VERBS as _WADDLEAI_ACTION_VERBS
from app.adapters.waddleai.manifest import _ENVELOPE_PATHS as _WADDLEAI_ENVELOPE_PATHS


@dataclass(slots=True, frozen=True)
class _ConformanceInputs:
    """Per-registered-product inputs only that product's OWN module can supply.

    See ``validate_manifest``'s docstring for why these are not read off the
    Adapter Protocol generically. A future product's manifest adds one entry
    to :data:`_CONFORMANCE_INPUTS`; everything below it is already
    parametrised over the registry.
    """

    adapter_cls: type[_RouteSourceAdapter]
    action_verbs: dict[str, frozenset[str]]
    sensitive_fields: frozenset[str]
    envelope_paths: dict[str, tuple[str, ...]]
    supports_cancel: bool
    supports_operation_logs: bool


_CONFORMANCE_INPUTS: Final[dict[str, _ConformanceInputs]] = {
    "gough": _ConformanceInputs(
        adapter_cls=GoughAdapter,
        action_verbs={kind: frozenset(verbs) for kind, verbs in _GOUGH_ACTIONS.items()},
        sensitive_fields=GoughAdapter.SENSITIVE_FIELDS,
        envelope_paths=_GOUGH_ENVELOPE_PATHS,
        supports_cancel=GoughAdapter.SUPPORTS_OPERATION_CANCEL,
        supports_operation_logs=GoughAdapter.SUPPORTS_OPERATION_LOGS,
    ),
    "tobogganing": _ConformanceInputs(
        adapter_cls=TobogganingAdapter,
        action_verbs=dict(_TOBOGGANING_ACTION_VERBS),
        sensitive_fields=frozenset(),
        envelope_paths=_TOBOGGANING_ENVELOPE_PATHS,
        supports_cancel=False,
        supports_operation_logs=False,
    ),
    "waddleai": _ConformanceInputs(
        adapter_cls=WaddleAIAdapter,
        action_verbs=dict(_WADDLEAI_ACTION_VERBS),
        sensitive_fields=frozenset(),
        envelope_paths=_WADDLEAI_ENVELOPE_PATHS,
        supports_cancel=False,
        supports_operation_logs=False,
    ),
}


@pytest.fixture(params=sorted(MANIFEST_REGISTRY))
def product_type(request: pytest.FixtureRequest) -> str:
    """Every product_type with a REGISTERED manifest — derived, not listed."""
    return str(request.param)


def test_every_registered_product_type_has_an_active_adapter(product_type: str) -> None:
    """A manifest with no backing adapter can never be validated or served."""
    assert product_type in ADAPTER_REGISTRY, (
        f"{product_type!r} is in MANIFEST_REGISTRY but not ADAPTER_REGISTRY -- "
        f"a manifest with no adapter can never pass validate_manifest"
    )


def test_every_registered_manifest_still_passes_validate_manifest(product_type: str) -> None:
    """Re-run the same fail-closed check the module performed at import time.

    Not redundant with the import-time call in ``adapters/gough/manifest.py``:
    that call proves the manifest was valid THEN; this one proves the
    registry entry the route actually serves still is, independent of
    whether someone edited the manifest after import-time validation ran.
    """
    manifest = MANIFEST_REGISTRY[product_type]
    inputs = _CONFORMANCE_INPUTS[product_type]
    validate_manifest(
        manifest,
        inputs.adapter_cls,
        action_verbs=inputs.action_verbs,
        sensitive_fields=inputs.sensitive_fields,
        envelope_paths=inputs.envelope_paths,
        supports_cancel=inputs.supports_cancel,
        supports_operation_logs=inputs.supports_operation_logs,
    )


def test_manifest_version_is_within_bounds(product_type: str) -> None:
    """Manifest version is within bounds."""
    from app.adapters.manifest import MAX_MANIFEST_VERSION, MIN_MANIFEST_VERSION

    manifest = MANIFEST_REGISTRY[product_type]
    assert MIN_MANIFEST_VERSION <= manifest.manifest_version <= MAX_MANIFEST_VERSION


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("nodes", "/api/v1/nodes/"),
        ("biomes", "/api/v1/biomes/"),
        ("biome_groups", "/api/v1/biomes/groups"),
        ("agents", "/api/v1/agents/"),
    ],
)
def test_gough_list_path_bytes_is_byte_equal_to_the_adapter_route_constant(
    kind: str, expected: str
) -> None:
    """The Design §3.3 defect, generalised.

    A manifest's ``list.path_bytes`` must be the SAME OBJECT VALUE as the
    adapter's own route constant, not a re-typed string that happens to
    look the same today.

    Parametrised over the resources the GOUGH manifest actually declares
    (derived from ``MANIFEST_REGISTRY["gough"]`` below), not a hand list —
    the four cases named here are the closed set
    ``test_manifest_declares_exactly_the_expected_gough_resources`` pins.
    """
    manifest = MANIFEST_REGISTRY["gough"]
    resource = manifest.resource(kind)
    assert resource is not None, f"gough manifest does not declare resource {kind!r}"
    assert resource.list is not None, f"gough manifest resource {kind!r} declares no list"
    assert resource.list.path_bytes == expected == _GOUGH_COLLECTION_ROUTES[kind]


def test_manifest_declares_exactly_the_expected_gough_resources() -> None:
    """Pin the set so an added/removed resource is a deliberate test edit.

    Matches ``test_webui_declares_exactly_the_collections_its_screens_fetch``'s
    reasoning in ``test_gough_webui_paths.py``.
    """
    manifest = MANIFEST_REGISTRY["gough"]
    assert {resource.kind for resource in manifest.resources} == {
        "nodes",
        "biomes",
        "biome_groups",
        "agents",
    }


def test_clusters_is_not_declared_as_a_resource() -> None:
    """The documented schema finding in ``adapters/gough/manifest.py``.

    Gough has no ``GET /api/v1/clusters`` collection and an irregular
    per-item path, so this schema version does not attempt to express it.
    """
    manifest = MANIFEST_REGISTRY["gough"]
    assert manifest.resource("clusters") is None


def test_biome_groups_is_declared_but_not_a_nav_item() -> None:
    """Matches ``test_gough_webui_paths.py``'s established fact.

    The adapter addresses ``biome_groups`` server-side, but no screen
    requests it.
    """
    manifest = MANIFEST_REGISTRY["gough"]
    assert manifest.resource("biome_groups") is not None
    assert "biome_groups" not in {item.kind for item in manifest.nav.items}


@pytest.mark.parametrize("kind", ["nodes", "biomes", "biome_groups", "agents"])
def test_every_gough_list_path_is_admitted_by_the_proxy_allowlist(kind: str) -> None:
    """Independent re-assertion of what ``validate_manifest`` already enforced.

    Proves the SPECIFIC rule, not just that import-time validation as a
    whole passed.
    """
    from app.adapters.gough.routes import GOUGH_ROUTE_ALLOWLIST

    manifest = MANIFEST_REGISTRY["gough"]
    resource = manifest.resource(kind)
    assert resource is not None and resource.list is not None
    path = resource.list.path_bytes
    assert any(rule.matches("GET", path) for rule in GOUGH_ROUTE_ALLOWLIST), (
        f"gough manifest resource {kind!r} declares list.path_bytes {path!r}, "
        f"which no GET rule in GOUGH_ROUTE_ALLOWLIST admits"
    )


def test_no_manifest_action_verb_is_unknown_to_its_adapter(product_type: str) -> None:
    """No manifest action verb is unknown to its adapter."""
    manifest = MANIFEST_REGISTRY[product_type]
    inputs = _CONFORMANCE_INPUTS[product_type]
    for resource in manifest.resources:
        allowed = inputs.action_verbs.get(resource.kind, frozenset())
        for action in resource.actions:
            assert action.verb in allowed, (
                f"{product_type}/{resource.kind}: action verb {action.verb!r} is not "
                f"one the adapter implements for this kind (known: {sorted(allowed)})"
            )


def test_no_column_names_a_field_the_adapter_marks_sensitive(product_type: str) -> None:
    """No column names a field the adapter marks sensitive."""
    manifest = MANIFEST_REGISTRY[product_type]
    inputs = _CONFORMANCE_INPUTS[product_type]
    for resource in manifest.resources:
        for column in resource.columns:
            assert column.field not in inputs.sensitive_fields, (
                f"{product_type}/{resource.kind}: column {column.field!r} names a "
                f"field the adapter marks sensitive"
            )


def test_every_operation_starting_action_is_on_a_typed_resource(product_type: str) -> None:
    """Every operation starting action is on a typed resource."""
    manifest = MANIFEST_REGISTRY[product_type]
    for resource in manifest.resources:
        for action in resource.actions:
            if action.starts_operations:
                assert resource.transport == "typed", (
                    f"{product_type}/{resource.kind}: action {action.verb!r} starts "
                    f"operations but transport is {resource.transport!r}"
                )


def test_every_non_text_column_declares_absent_as(product_type: str) -> None:
    """Independent re-check of Design §3.3 across the whole registry.

    Already enforced at ColumnSpec construction; re-verified here so the
    registry-wide sweep does not silently rely on nobody having bypassed it.
    """
    manifest = MANIFEST_REGISTRY[product_type]
    for resource in manifest.resources:
        for column in resource.columns:
            if column.cell.kind != "text":
                assert column.absent_as is not None, (
                    f"{product_type}/{resource.kind}: column {column.field!r} "
                    f"({column.cell.kind}) declares no absent_as"
                )


# ---------------------------------------------------------------------------
# apply_capabilities_overlay against the REAL Gough manifest
# ---------------------------------------------------------------------------


def test_gough_overlay_with_a_reduced_capability_list_only_ever_subtracts() -> None:
    """Gough overlay with a reduced capability list only ever subtracts."""
    manifest = MANIFEST_REGISTRY["gough"]
    original_kinds = {r.kind for r in manifest.resources}

    overlaid = apply_capabilities_overlay(manifest, ["list_resources"])

    assert {r.kind for r in overlaid.resources} == original_kinds  # never drops a resource
    for resource in overlaid.resources:
        assert resource.actions == ()
        assert resource.create is None
        assert resource.delete is None
    assert overlaid.operations is None
    assert overlaid.metrics is None


def test_gough_overlay_with_every_capability_reproduces_the_committed_manifest() -> None:
    """Gough overlay with every capability reproduces the committed manifest."""
    manifest = MANIFEST_REGISTRY["gough"]
    full_capabilities = [
        "health",
        "list_resources",
        "get_resource",
        "create_resource",
        "update_resource",
        "delete_resource",
        "perform_action",
        "list_operations",
        "get_operation",
        "cancel_operation",
        "operation_logs",
        "metrics_summary",
    ]
    overlaid = apply_capabilities_overlay(manifest, full_capabilities)
    assert overlaid == manifest
