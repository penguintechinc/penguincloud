"""WaddleAI-specific manifest conformance — Phase 8 acceptance test.

Generic, registry-derived checks (every registered manifest still passes
``validate_manifest``, no column names a sensitive field, no
operation-starting action on a non-``typed`` resource, ...) already run
against ``waddleai`` the moment it is registered in ``_CONFORMANCE_INPUTS``
in ``test_gough_manifest_conformance.py`` — this module holds only the
assertions specific to WaddleAI's OWN manifest: the exact resource set,
byte-equal list paths, the ``item_path=None`` fact true of all three
resources (including the two — ``provider``, ``knowledge_document`` — that
DO have a real item route on the product, unlike Tobogganing where none do),
and an injection proof that :func:`validate_manifest` really refuses a bad
path rather than merely never having been asked to check one.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.adapters import ADAPTER_REGISTRY, MANIFEST_REGISTRY
from app.adapters.manifest import ItemPathSpec, ManifestError, validate_manifest
from app.adapters.waddleai.adapter import WaddleAIAdapter
from app.adapters.waddleai.manifest import _ACTION_VERBS, _ENVELOPE_PATHS
from app.adapters.waddleai.routes import PATH_KNOWLEDGE, PATH_PROVIDERS, PATH_QUOTAS

_MANIFEST = MANIFEST_REGISTRY["waddleai"]

_ALL_KINDS = ("provider", "knowledge_document", "quota")


def test_waddleai_is_registered_with_an_active_adapter() -> None:
    """A manifest with no backing adapter can never be validated or served."""
    assert "waddleai" in ADAPTER_REGISTRY
    assert "waddleai" in MANIFEST_REGISTRY


def test_waddleai_is_no_longer_a_planned_product() -> None:
    """The registry flip this acceptance test is about: planned -> active."""
    from app.adapters import PLANNED_PRODUCTS

    assert "waddleai" not in PLANNED_PRODUCTS


def test_manifest_declares_exactly_the_three_resource_kinds() -> None:
    """Pin the set so an added/removed resource is a deliberate test edit.

    Deliberately three, not WaddleAI's whole surface — see ``adapter.py``'s
    module docstring for what was left out (secrets, portal-native domains)
    and why.
    """
    assert {resource.kind for resource in _MANIFEST.resources} == set(_ALL_KINDS)


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("provider", PATH_PROVIDERS),
        ("knowledge_document", PATH_KNOWLEDGE),
        ("quota", PATH_QUOTAS),
    ],
)
def test_list_path_bytes_is_byte_equal_to_the_route_constant(kind: str, expected: str) -> None:
    """A manifest's ``list.path_bytes`` must be the SAME string as the route constant."""
    resource = _MANIFEST.resource(kind)
    assert resource is not None, f"waddleai manifest does not declare resource {kind!r}"
    assert resource.list is not None, f"waddleai manifest resource {kind!r} declares no list"
    assert resource.list.path_bytes == expected


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_every_list_path_is_admitted_by_the_proxy_allowlist(kind: str) -> None:
    """Independent re-assertion of what ``validate_manifest`` already enforced at import time."""
    from app.adapters.waddleai.routes import WADDLEAI_ROUTE_ALLOWLIST

    resource = _MANIFEST.resource(kind)
    assert resource is not None and resource.list is not None
    path = resource.list.path_bytes
    assert any(rule.matches("GET", path) for rule in WADDLEAI_ROUTE_ALLOWLIST), (
        f"waddleai manifest resource {kind!r} declares list.path_bytes {path!r}, "
        f"which no GET rule in WADDLEAI_ROUTE_ALLOWLIST admits"
    )


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_every_resource_declares_no_item_path(kind: str) -> None:
    """``provider`` and ``knowledge_document`` DO have a real item route on the product.

    Neither is allowlisted or declared here — see ``routes.py``'s and
    ``adapter.py``'s docstrings for why (unreviewed extra provider-detail
    fields; a knowledge-detail response identical to its list row; and, for
    ``quota``, no per-id read exists on the product at all).
    """
    resource = _MANIFEST.resource(kind)
    assert resource is not None
    assert resource.item_path is None


def test_manifest_declares_no_operations_or_metrics_block() -> None:
    """None of the three resources has an async operation to poll."""
    assert _MANIFEST.operations is None
    assert _MANIFEST.metrics is None


def test_every_resource_is_proxy_transport_with_no_actions_create_or_delete() -> None:
    """This cut is read-only — see the adapter module docstring."""
    for resource in _MANIFEST.resources:
        assert resource.transport == "proxy"
        assert resource.actions == ()
        assert resource.create is None
        assert resource.delete is None


def test_every_registered_manifest_still_passes_validate_manifest() -> None:
    """Re-run the same fail-closed check the module performed at import time."""
    validate_manifest(
        _MANIFEST,
        WaddleAIAdapter,
        action_verbs=_ACTION_VERBS,
        sensitive_fields=frozenset(),
        envelope_paths=_ENVELOPE_PATHS,
        supports_cancel=False,
        supports_operation_logs=False,
    )


# ---------------------------------------------------------------------------
# Injection proof — the gate really bites, not merely never asked to check
# ---------------------------------------------------------------------------


def test_a_bogus_item_path_on_a_waddleai_resource_refuses_to_load() -> None:
    """Prove ``validate_manifest`` refuses a read path the allowlist does not admit.

    A local copy of the real ``provider`` resource, with a fabricated
    ``item_path`` no GET rule in ``WADDLEAI_ROUTE_ALLOWLIST`` admits, must
    raise — the same proof
    ``test_manifest_schema.py``'s ``test_an_item_path_the_allowlist_does_not_admit_refuses_to_load``
    performs generically, re-run here against WaddleAI's OWN registered
    manifest and adapter so a future edit that accidentally loosens the
    allowlist or widens ``item_path`` acceptance would be caught here too.
    """
    real_provider = _MANIFEST.resource("provider")
    assert real_provider is not None
    poisoned_provider = replace(
        real_provider,
        item_path=ItemPathSpec(prefix="/api/v1/providers/secret-admin", sample_id="1"),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_provider if r.kind == "provider" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            WaddleAIAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )


def test_a_bogus_list_path_on_a_waddleai_resource_refuses_to_load() -> None:
    """Same injection proof, for ``list.path_bytes`` instead of ``item_path``."""
    real_provider = _MANIFEST.resource("provider")
    assert real_provider is not None and real_provider.list is not None
    poisoned_provider = replace(
        real_provider,
        list=replace(real_provider.list, path_bytes="/api/v1/providers/../../admin/secrets"),
    )
    poisoned_manifest = replace(
        _MANIFEST,
        resources=tuple(
            poisoned_provider if r.kind == "provider" else r for r in _MANIFEST.resources
        ),
    )
    with pytest.raises(ManifestError, match="is not admitted by any GET rule"):
        validate_manifest(
            poisoned_manifest,
            WaddleAIAdapter,
            action_verbs=_ACTION_VERBS,
            sensitive_fields=frozenset(),
        )
