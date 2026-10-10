"""Tobogganing-specific manifest conformance — Phase 8 Step 4.

Generic, registry-derived checks (every registered manifest still passes
``validate_manifest``, no column names a sensitive field, no
operation-starting action on a non-``typed`` resource, ...) already run
against ``tobogganing`` the moment it is registered in
``_CONFORMANCE_INPUTS`` in ``test_gough_manifest_conformance.py`` — this
module holds only the assertions specific to Tobogganing's OWN manifest:
the exact resource set, byte-equal list paths, the ``item_path=None`` fact
that is true of every one of its six resources (unlike Gough, where four of
five have a real item path), the ``blockpage_route`` nav omission, and an
injection proof that :func:`validate_manifest` really refuses a bad path
rather than merely never having been asked to check one.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.adapters import ADAPTER_REGISTRY, MANIFEST_REGISTRY
from app.adapters.manifest import ItemPathSpec, ManifestError, validate_manifest
from app.adapters.tobogganing.adapter import TobogganingAdapter
from app.adapters.tobogganing.manifest import _ACTION_VERBS, _ENVELOPE_PATHS
from app.adapters.tobogganing.routes import (
    PATH_BLOCKPAGE_PAGES,
    PATH_BLOCKPAGE_ROUTES,
    PATH_SDWAN_CLIENTS,
    PATH_SDWAN_CLUSTERS,
    PATH_SWG_POLICY,
    PATH_WIREGUARD_PEERS,
)

_MANIFEST = MANIFEST_REGISTRY["tobogganing"]

#: All six resource kinds, reused by every parametrized sweep below.
_ALL_KINDS = (
    "sdwan_client",
    "sdwan_cluster",
    "wireguard_peer",
    "block_page",
    "blockpage_route",
    "swg_policy",
)


def test_tobogganing_is_registered_with_an_active_adapter() -> None:
    """A manifest with no backing adapter can never be validated or served."""
    assert "tobogganing" in ADAPTER_REGISTRY
    assert "tobogganing" in MANIFEST_REGISTRY


def test_manifest_declares_exactly_the_six_resource_kinds() -> None:
    """Pin the set so an added/removed resource is a deliberate test edit.

    Matches ``mapping.RESOURCE_KINDS`` — every kind the adapter serves, all
    declared read-only in this PR (see the manifest module docstring).
    """
    assert {resource.kind for resource in _MANIFEST.resources} == {
        "sdwan_client",
        "sdwan_cluster",
        "wireguard_peer",
        "block_page",
        "blockpage_route",
        "swg_policy",
    }


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("sdwan_client", PATH_SDWAN_CLIENTS),
        ("sdwan_cluster", PATH_SDWAN_CLUSTERS),
        ("wireguard_peer", PATH_WIREGUARD_PEERS),
        ("block_page", PATH_BLOCKPAGE_PAGES),
        ("blockpage_route", PATH_BLOCKPAGE_ROUTES),
        ("swg_policy", PATH_SWG_POLICY),
    ],
)
def test_list_path_bytes_is_byte_equal_to_the_route_constant(kind: str, expected: str) -> None:
    """A manifest's ``list.path_bytes`` must be the SAME string as the route constant."""
    resource = _MANIFEST.resource(kind)
    assert resource is not None, f"tobogganing manifest does not declare resource {kind!r}"
    assert resource.list is not None, f"tobogganing manifest resource {kind!r} declares no list"
    assert resource.list.path_bytes == expected


@pytest.mark.parametrize(
    "kind",
    _ALL_KINDS,
)
def test_every_list_path_is_admitted_by_the_proxy_allowlist(kind: str) -> None:
    """Independent re-assertion of what ``validate_manifest`` already enforced at import time."""
    from app.adapters.tobogganing.routes import TOBOGGANING_ROUTE_ALLOWLIST

    resource = _MANIFEST.resource(kind)
    assert resource is not None and resource.list is not None
    path = resource.list.path_bytes
    assert any(rule.matches("GET", path) for rule in TOBOGGANING_ROUTE_ALLOWLIST), (
        f"tobogganing manifest resource {kind!r} declares list.path_bytes {path!r}, "
        f"which no GET rule in TOBOGGANING_ROUTE_ALLOWLIST admits"
    )


@pytest.mark.parametrize(
    "kind",
    _ALL_KINDS,
)
def test_every_resource_declares_no_item_path(kind: str) -> None:
    """Tobogganing serves no item route for any of these kinds.

    :meth:`TobogganingAdapter.get_resource`'s own docstring says so outright,
    and ``TOBOGGANING_ROUTE_ALLOWLIST`` admits a ``GET`` rule for each
    collection path and for none of their would-be item paths — this is a
    fact about the product, not an omission in this manifest.
    """
    resource = _MANIFEST.resource(kind)
    assert resource is not None
    assert resource.item_path is None


def test_blockpage_route_is_declared_but_not_a_nav_item() -> None:
    """Matches the ``biome_groups`` precedent in Gough's own manifest.

    The adapter addresses ``blockpage_route`` server-side, but no
    hand-written screen in ``services/webui/.../tobogganing/`` requests it.
    """
    assert _MANIFEST.resource("blockpage_route") is not None
    assert "blockpage_route" not in {item.kind for item in _MANIFEST.nav.items}


def test_manifest_declares_no_operations_or_metrics_block() -> None:
    """The adapter offers no operation surface and no metrics_summary capability."""
    assert _MANIFEST.operations is None
    assert _MANIFEST.metrics is None


def test_every_resource_is_proxy_transport_with_no_actions_create_or_delete() -> None:
    """Scope cut for this PR: read surface only — see the module docstring."""
    for resource in _MANIFEST.resources:
        assert resource.transport == "proxy"
        assert resource.actions == ()
        assert resource.create is None
        assert resource.delete is None


def test_every_registered_manifest_still_passes_validate_manifest() -> None:
    """Re-run the same fail-closed check the module performed at import time."""
    validate_manifest(
        _MANIFEST,
        TobogganingAdapter,
        action_verbs=_ACTION_VERBS,
        sensitive_fields=frozenset(),
        envelope_paths=_ENVELOPE_PATHS,
        supports_cancel=False,
        supports_operation_logs=False,
    )


# ---------------------------------------------------------------------------
# Injection proof — the gate really bites, not merely never asked to check
# ---------------------------------------------------------------------------


def test_a_bogus_item_path_on_a_tobogganing_resource_refuses_to_load() -> None:
    """Prove ``validate_manifest`` refuses a read path the allowlist does not admit.

    A local copy of the real ``sdwan_client`` resource, with a fabricated
    ``item_path`` no GET rule in ``TOBOGGANING_ROUTE_ALLOWLIST`` admits,
    must raise — the same proof
    ``test_manifest_schema.py``'s ``test_an_item_path_the_allowlist_does_not_admit_refuses_to_load``
    performs generically, re-run here against Tobogganing's OWN registered
    manifest and adapter rather than a fake one, so a future edit that
    accidentally loosens the allowlist or widens ``item_path`` acceptance
    would be caught here too.
    """
    real_client = _MANIFEST.resource("sdwan_client")
    assert real_client is not None
    poisoned_client = replace(
        real_client,
        item_path=ItemPathSpec(prefix="/api/v1/sdwan/clients/secret-admin", sample_id="1"),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_client if r.kind == "sdwan_client" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            TobogganingAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )


def test_a_bogus_list_path_on_a_tobogganing_resource_refuses_to_load() -> None:
    """Same injection proof, for ``list.path_bytes`` instead of ``item_path``."""
    real_client = _MANIFEST.resource("sdwan_client")
    assert real_client is not None and real_client.list is not None
    poisoned_client = replace(
        real_client,
        list=replace(real_client.list, path_bytes="/api/v1/sdwan/clients/../../admin/secrets"),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_client if r.kind == "sdwan_client" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            TobogganingAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )
