"""Nest-specific manifest conformance — Phase 8 convergence, core-3 completion.

Generic, registry-derived checks (every registered manifest still passes
``validate_manifest``, no column names a sensitive field, no
operation-starting action on a non-``typed`` resource, ...) already run
against ``nest`` the moment it is registered in ``_CONFORMANCE_INPUTS`` in
``test_gough_manifest_conformance.py`` — this module holds only the
assertions specific to Nest's OWN manifest: the exact resource set, the
per-kind ``transport``/``item_path`` split (only ``database`` is typed with
a real item route; ``search_pool`` is proxy-read-only with a real item
route; ``snapshot``/``protection_policy`` are proxy with no item route at
all), the ``mode="watch"`` operations panel, the two-slot extension budget,
and an injection proof that :func:`validate_manifest` really refuses a bad
path rather than merely never having been asked to check one.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.adapters import ADAPTER_REGISTRY, MANIFEST_REGISTRY
from app.adapters.manifest import ItemPathSpec, ManifestError, validate_manifest
from app.adapters.nest.adapter import NestAdapter
from app.adapters.nest.manifest import _ACTION_VERBS, _ENVELOPE_PATHS
from app.adapters.nest.mapping import OP_KIND
from app.adapters.nest.routes import (
    NEST_ROUTE_ALLOWLIST,
    tenant_path,
)

_MANIFEST = MANIFEST_REGISTRY["nest"]

_ALL_KINDS = ("database", "search_pool", "snapshot", "protection_policy")

#: Kinds Nest serves a real single-item GET for — see
#: ``adapters/nest/adapter.py``'s ``_DETAIL_KINDS`` and this manifest's own
#: module docstring for the verified route evidence.
_KINDS_WITH_ITEM_PATH = ("database", "search_pool")
_KINDS_WITHOUT_ITEM_PATH = ("snapshot", "protection_policy")


def test_nest_is_registered_with_an_active_adapter() -> None:
    """A manifest with no backing adapter can never be validated or served."""
    assert "nest" in ADAPTER_REGISTRY
    assert "nest" in MANIFEST_REGISTRY


def test_manifest_declares_exactly_the_four_resource_kinds() -> None:
    """Pin the set so an added/removed resource is a deliberate test edit."""
    assert {resource.kind for resource in _MANIFEST.resources} == set(_ALL_KINDS)


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_every_list_path_is_admitted_by_the_proxy_allowlist(kind: str) -> None:
    """Independent re-assertion of what ``validate_manifest`` already enforced at import time."""
    resource = _MANIFEST.resource(kind)
    assert resource is not None and resource.list is not None
    path = resource.list.path_bytes
    assert any(rule.matches("GET", path) for rule in NEST_ROUTE_ALLOWLIST), (
        f"nest manifest resource {kind!r} declares list.path_bytes {path!r}, "
        f"which no GET rule in NEST_ROUTE_ALLOWLIST admits"
    )


@pytest.mark.parametrize("kind", _KINDS_WITH_ITEM_PATH)
def test_database_and_search_pool_declare_a_real_item_path(kind: str) -> None:
    """``database`` and ``search_pool`` both have a real ``GET .../<name>`` route."""
    resource = _MANIFEST.resource(kind)
    assert resource is not None
    assert resource.item_path is not None
    probe = f"{resource.item_path.prefix}/{resource.item_path.sample_id}"
    assert any(rule.matches("GET", probe) for rule in NEST_ROUTE_ALLOWLIST), (
        f"nest manifest resource {kind!r} declares item_path {probe!r}, "
        f"which no GET rule in NEST_ROUTE_ALLOWLIST admits"
    )


@pytest.mark.parametrize("kind", _KINDS_WITHOUT_ITEM_PATH)
def test_snapshot_and_protection_policy_declare_no_item_path(kind: str) -> None:
    """Nest registers no single-item GET for either kind — a product fact, not an omission.

    ``NestAdapter._DETAIL_KINDS`` excludes both, and
    ``NEST_ROUTE_ALLOWLIST`` admits no item rule for either collection.
    """
    resource = _MANIFEST.resource(kind)
    assert resource is not None
    assert resource.item_path is None


def test_only_database_is_typed_with_actions_create_and_delete() -> None:
    """``search_pool``/``snapshot``/``protection_policy`` declare no typed mutation surface."""
    database = _MANIFEST.resource("database")
    assert database is not None
    assert database.transport == "typed"
    assert database.create is not None
    assert database.delete is not None
    assert database.edit is None
    assert {action.verb for action in database.actions} == {
        "snapshot",
        "restore",
        "introspect",
        "migrate",
    }
    assert all(action.starts_operations for action in database.actions)

    for kind in ("search_pool", "snapshot", "protection_policy"):
        resource = _MANIFEST.resource(kind)
        assert resource is not None
        assert resource.transport == "proxy"
        assert resource.actions == ()
        assert resource.create is None
        assert resource.edit is None
        assert resource.delete is None


def test_only_database_is_a_nav_item() -> None:
    """The other three kinds have no hand-written screen to mirror (see the manifest docstring)."""
    assert {item.kind for item in _MANIFEST.nav.items} == {"database"}
    for kind in ("search_pool", "snapshot", "protection_policy"):
        assert _MANIFEST.resource(kind) is not None


def test_database_declares_the_snapshot_relationship() -> None:
    """The Snapshots detail tab comes from ``RelationshipSpec``, not a nav entry."""
    database = _MANIFEST.resource("database")
    assert database is not None
    assert len(database.relationships) == 1
    relationship = database.relationships[0]
    assert relationship.child_kind == "snapshot"
    assert relationship.parent_field == "sourcePVC"


def test_operations_panel_is_watch_mode_with_no_cancel_or_logs() -> None:
    """``get_operation`` is real; the list/cancel/logs operation capabilities are not."""
    assert _MANIFEST.operations is not None
    assert _MANIFEST.operations.mode == "watch"
    assert _MANIFEST.operations.cancel_allowed is False
    assert _MANIFEST.operations.show_logs is False


def test_operations_panel_operation_kind_matches_nest_adapter_op_kind() -> None:
    """The watch URL kind is NestAdapter's own OP_KIND, not database's resource kind.

    ``get_operation`` only accepts ``kind in OPERATION_KINDS`` (``{OP_KIND}``) --
    without this override the generic watch hook's default (the resource's own
    kind, ``"database"``) would 501 against a real Nest deployment.
    """
    assert _MANIFEST.operations is not None
    assert _MANIFEST.operations.operation_kind == OP_KIND


def test_manifest_declares_no_metrics_block() -> None:
    """``metrics_summary`` is not among ``NestAdapter.capabilities()``'s answers."""
    assert _MANIFEST.metrics is None


def test_manifest_declares_exactly_two_extension_slots_at_the_budget() -> None:
    """Design §4.1's <=2-slots-per-product budget, hit exactly."""
    assert len(_MANIFEST.extensions) == 2
    slots = {(slot.slot, slot.id, slot.resource) for slot in _MANIFEST.extensions}
    assert slots == {
        ("page", "billing", None),
        ("detail_tab", "health", "database"),
    }


def test_every_registered_manifest_still_passes_validate_manifest() -> None:
    """Re-run the same fail-closed check the module performed at import time."""
    validate_manifest(
        _MANIFEST,
        NestAdapter,
        action_verbs=_ACTION_VERBS,
        sensitive_fields=frozenset(),
        envelope_paths=_ENVELOPE_PATHS,
        supports_cancel=False,
        supports_operation_logs=False,
    )


# ---------------------------------------------------------------------------
# Injection proof — the gate really bites, not merely never asked to check
# ---------------------------------------------------------------------------


def test_a_bogus_item_path_on_the_database_resource_refuses_to_load() -> None:
    """Prove ``validate_manifest`` refuses a read path the allowlist does not admit.

    A local copy of the real ``database`` resource, with a fabricated
    ``item_path`` no GET rule in ``NEST_ROUTE_ALLOWLIST`` admits, must raise
    — the same proof ``test_manifest_schema.py``'s
    ``test_an_item_path_the_allowlist_does_not_admit_refuses_to_load``
    performs generically, re-run here against Nest's OWN registered manifest
    and adapter so a future edit that accidentally loosens the allowlist or
    widens ``item_path`` acceptance would be caught here too.
    """
    real_database = _MANIFEST.resource("database")
    assert real_database is not None
    poisoned_database = replace(
        real_database,
        item_path=ItemPathSpec(
            prefix=tenant_path("{tenant}", "internal-admin"), sample_id="sample-db"
        ),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_database if r.kind == "database" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            NestAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )


def test_a_bogus_list_path_on_the_database_resource_refuses_to_load() -> None:
    """Same injection proof, for ``list.path_bytes`` instead of ``item_path``."""
    real_database = _MANIFEST.resource("database")
    assert real_database is not None and real_database.list is not None
    poisoned_database = replace(
        real_database,
        list=replace(
            real_database.list,
            path_bytes=tenant_path("{tenant}", "data-resources/../../admin/secrets"),
        ),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_database if r.kind == "database" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            NestAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )
