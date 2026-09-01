"""Tests for `pcli.api.manifest_types` wire parsing."""

from __future__ import annotations

from typing import Any

import pytest

from pcli.api.manifest_types import (
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    EnvelopeSpec,
    ItemPathSpec,
    ListSpec,
    ProductManifestEntry,
    ResourceDescriptor,
    parse_manifests_response,
)
from pcli.errors import ManifestError


def _node_resource_wire() -> dict[str, Any]:
    return {
        "kind": "nodes",
        "label": "Node",
        "plural_label": "Nodes",
        "id_field": "id",
        "name_field": "name",
        "transport": "typed",
        "empty_state": "No nodes.",
        "error_state": "Unable to load nodes.",
        "columns": [
            {
                "field": "id",
                "label": "ID",
                "cell": {"kind": "text"},
                "sortable": False,
                "absent_as": None,
            },
            {
                "field": "state",
                "label": "State",
                "cell": {"kind": "text"},
                "sortable": False,
                "absent_as": "dash",
            },
        ],
        "list": {
            "path_bytes": "/api/v1/nodes/",
            "envelope": {"keys": ["data", "nodes"]},
            "pagination": "cursor",
        },
        "item_path": {"prefix": "/api/v1/nodes", "sample_id": "1"},
    }


def test_resource_descriptor_from_wire() -> None:
    """Resource descriptor from wire."""
    resource = ResourceDescriptor.from_wire(_node_resource_wire())
    assert resource.kind == "nodes"
    assert resource.list is not None
    assert resource.list.path_bytes == "/api/v1/nodes/"
    assert resource.list.envelope.keys == ("data", "nodes")
    assert resource.item_path is not None
    assert resource.item_path.prefix == "/api/v1/nodes"
    assert len(resource.columns) == 2
    assert resource.columns[1].absent_as == "dash"


def test_resource_descriptor_with_no_list_or_item_path() -> None:
    """Resource descriptor with no list or item path."""
    body = _node_resource_wire()
    body["list"] = None
    body["item_path"] = None
    resource = ResourceDescriptor.from_wire(body)
    assert resource.list is None
    assert resource.item_path is None


def test_resource_descriptor_missing_required_field_raises_manifest_error() -> None:
    """Resource descriptor missing required field raises manifest error."""
    body = _node_resource_wire()
    del body["label"]
    with pytest.raises(ManifestError, match="label"):
        ResourceDescriptor.from_wire(body)


def test_console_manifest_from_wire() -> None:
    """Console manifest from wire."""
    body = {
        "manifest_version": 2,
        "product_type": "gough",
        "display_name": "Gough",
        "nav": {"items": [{"kind": "nodes", "label": "Nodes", "icon": None}]},
        "resources": [_node_resource_wire()],
    }
    manifest = ConsoleManifest.from_wire(body)
    assert manifest.product_type == "gough"
    assert manifest.manifest_version == 2
    assert manifest.resource("nodes") is not None
    assert manifest.resource("missing") is None
    assert manifest.nav_items[0].kind == "nodes"


def test_product_manifest_entry_from_wire() -> None:
    """Product manifest entry from wire."""
    body = {
        "product_id": 42,
        "product_type": "gough",
        "manifest": {
            "manifest_version": 2,
            "product_type": "gough",
            "display_name": "Gough",
            "nav": {"items": []},
            "resources": [],
        },
    }
    entry = ProductManifestEntry.from_wire(body)
    assert entry.product_id == 42
    assert entry.manifest.display_name == "Gough"


def test_parse_manifests_response_envelope() -> None:
    """Parse manifests response envelope."""
    body = {
        "manifests": [
            {
                "product_id": 1,
                "product_type": "gough",
                "manifest": {
                    "manifest_version": 2,
                    "product_type": "gough",
                    "display_name": "Gough",
                    "nav": {"items": []},
                    "resources": [],
                },
            }
        ],
        "count": 1,
    }
    entries = parse_manifests_response(body)
    assert len(entries) == 1
    assert entries[0].product_type == "gough"


def test_parse_manifests_response_empty() -> None:
    """Parse manifests response empty."""
    assert parse_manifests_response({"manifests": [], "count": 0}) == ()


def test_cell_spec_with_boolean_labels_and_styles() -> None:
    """Cell spec with boolean labels and styles."""
    body = {
        "kind": "boolean",
        "labels": {"true_label": "Yes", "false_label": "No"},
        "styles": [{"value": "healthy", "style": "success"}],
    }
    cell = CellSpec.from_wire(body)
    assert cell.labels is not None
    assert cell.labels.true_label == "Yes"
    assert cell.styles[0].value == "healthy"


def test_column_spec_missing_cell_raises() -> None:
    """Column spec missing cell raises."""
    with pytest.raises(ManifestError):
        ColumnSpec.from_wire({"field": "x", "label": "X"})


def test_envelope_spec_missing_keys_raises() -> None:
    """Envelope spec missing keys raises."""
    with pytest.raises(ManifestError):
        EnvelopeSpec.from_wire({})


def test_list_spec_defaults_pagination_to_cursor() -> None:
    """List spec defaults pagination to cursor."""
    spec = ListSpec.from_wire({"path_bytes": "/x/", "envelope": {"keys": ["a"]}})
    assert spec.pagination == "cursor"


def test_item_path_spec_from_wire() -> None:
    """Item path spec from wire."""
    spec = ItemPathSpec.from_wire({"prefix": "/api/v1/nodes", "sample_id": "1"})
    assert spec.prefix == "/api/v1/nodes"
