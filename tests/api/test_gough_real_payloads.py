"""Map REAL Gough payloads, captured from a running Gough, not invented ones.

``test_gough_adapter.py`` proves the adapter's routing and error handling
against ``FakeGough``. It cannot prove the thing that actually broke here:
whether the fields :mod:`app.adapters.gough.mapping` reads exist in what Gough
really sends. Every payload in ``fixtures/gough_real_payloads.json`` came off a
live Gough (see ``README-gough-fixtures.md`` for how, and the live-verification
report for what could and could not be reached), so a mapper that reads a field
Gough does not emit fails here.

That is not hypothetical — it is what these tests were written to catch:
``map_biome_group`` read ``biome_ids``, a key that appears in **no** Gough group
response. It resolved to ``None`` on every group, ``or []`` turned that into an
empty list, and group membership rendered as "no biomes" with nothing failing
anywhere. The fixture below carries the real ``biomes`` array, so the old code
cannot pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from app.adapters.gough.mapping import (
    map_biome,
    map_biome_group,
    map_node,
    parse_timestamp,
)

_FIXTURE: Final[Path] = Path(__file__).parent / "fixtures" / "gough_real_payloads.json"


@pytest.fixture(scope="module")
def real() -> dict[str, Any]:
    """The captured Gough payloads."""
    loaded: dict[str, Any] = json.loads(_FIXTURE.read_text())
    return loaded


@pytest.fixture(scope="module")
def serializer(real: dict[str, Any]) -> dict[str, Any]:
    """Payloads produced by Gough's own serializer functions."""
    payloads: dict[str, Any] = real["serializer"]
    return payloads


class TestRealNode:
    """``map_node`` against a real ``_serialize_node`` payload."""

    def test_every_field_the_mapper_reads_exists_in_the_real_payload(
        self, serializer: dict[str, Any]
    ) -> None:
        """No mapped key is absent from what Gough emits.

        ``firmware_type`` is deliberately included: it IS a key Gough emits,
        even though no column backs it. Its always-``None`` value is asserted
        separately below so the distinction stays visible.
        """
        payload = serializer["node"]
        for field in (
            "id",
            "name",
            "state",
            "posture",
            "tenant_id",
            "ipv4",
            "ipv6",
            "primary_nic_mac",
            "firmware_type",
            "attestation_method",
            "hardware_tags",
            "discovered_at",
            "deployed_at",
            "created_at",
            "updated_at",
        ):
            assert field in payload, f"gough no longer emits node field {field!r}"

    def test_node_has_state_and_not_status(self, serializer: dict[str, Any]) -> None:
        """The trap ``map_node`` exists to avoid, asserted against real data."""
        payload = serializer["node"]
        assert "state" in payload
        assert "status" not in payload

    def test_maps_state_to_status(self, serializer: dict[str, Any]) -> None:
        """Lifecycle lands on the portal's status field."""
        resource = map_node(serializer["node"])
        assert resource.status == serializer["node"]["state"] == "ready"

    def test_real_timestamps_parse(self, serializer: dict[str, Any]) -> None:
        """Gough's ``_iso`` emits a ``Z`` suffix; the parser must accept it."""
        raw = serializer["node"]["created_at"]
        assert raw.endswith("Z"), "fixture no longer exercises the Z-suffix form"
        resource = map_node(serializer["node"])
        assert resource.created_at is not None
        assert resource.created_at.tzinfo is not None

    def test_firmware_type_is_structurally_none(
        self, serializer: dict[str, Any]
    ) -> None:
        """Documents a Gough gap rather than pretending the field works.

        ``_serialize_node`` emits ``firmware_type`` from a tolerant getter over
        a column that exists in no table and no model, so it is ``None`` for
        every node. If this ever starts failing, Gough added the column and the
        mapper begins working with no change.
        """
        assert serializer["node"]["firmware_type"] is None
        assert map_node(serializer["node"]).metadata["firmware_type"] is None

    def test_hardware_tags_round_trip(self, serializer: dict[str, Any]) -> None:
        """A real jsonb array arrives as a list."""
        assert map_node(serializer["node"]).metadata["hardware_tags"] == ["gpu", "nvme"]


class TestRealBiome:
    """``map_biome`` against a real ``serialize_biome`` payload."""

    def test_every_field_the_mapper_reads_exists(
        self, serializer: dict[str, Any]
    ) -> None:
        """No mapped biome key is absent from Gough's real serialisation."""
        payload = serializer["biome"]
        for field in (
            "id",
            "name",
            "is_active",
            "biome_type",
            "biome_kind",
            "phase",
            "category",
            "version",
            "workload_type",
            "is_default",
            "lock_to_host",
            "requires_hardware_tags",
            "forbids_hardware_tags",
            "signing_key_id",
            "created_at",
            "updated_at",
        ):
            assert field in payload, f"gough no longer emits biome field {field!r}"

    def test_is_active_becomes_a_readable_status(
        self, serializer: dict[str, Any]
    ) -> None:
        """Biomes carry no lifecycle field, so ``is_active`` supplies one."""
        payload = serializer["biome"]
        assert payload["is_active"] is True
        assert map_biome(payload).status == "active"

    def test_seeded_biome_timestamps_are_null_and_tolerated(
        self, serializer: dict[str, Any]
    ) -> None:
        """Gough's own seeded biomes have NULL timestamps — the mapper must cope.

        This is real: ``seed_builtin_biomes`` inserts without ``created_at``.
        A mapper that assumed a string here would raise on a stock install.
        """
        payload = serializer["biome"]
        assert payload["created_at"] is None
        assert map_biome(payload).created_at is None


class TestRealBiomeGroup:
    """``map_biome_group`` — the mapper that was reading a nonexistent field."""

    def test_gough_emits_biomes_not_biome_ids(self, serializer: dict[str, Any]) -> None:
        """The regression this whole module exists for.

        ``biome_ids`` is not a key Gough ever puts in a group response; the
        column is ``biomes``. Asserting the absence pins the bug, so a future
        edit cannot quietly reintroduce a read of the invented name.
        """
        payload = serializer["biome_group"]
        assert "biomes" in payload
        assert "biome_ids" not in payload

    def test_membership_is_ordered_objects_not_bare_ids(
        self, serializer: dict[str, Any]
    ) -> None:
        """Shape, not just name: entries are ``{biome_id, order}`` objects."""
        members = serializer["biome_group"]["biomes"]
        assert members == [{"biome_id": 1, "order": 0}, {"biome_id": 2, "order": 1}]

    def test_membership_survives_the_mapping(self, serializer: dict[str, Any]) -> None:
        """The whole point: a real group maps to a NON-empty membership.

        Against the previous mapper both assertions below failed — ``biome_ids``
        was ``[]`` and ``biomes`` was absent — while every mock-based test in the
        suite stayed green.
        """
        resource = map_biome_group(serializer["biome_group"])
        assert resource.metadata["biome_ids"] == [1, 2]
        assert resource.metadata["biomes"] == [
            {"biome_id": 1, "order": 0},
            {"biome_id": 2, "order": 1},
        ]

    def test_group_timestamps_use_the_offset_form(
        self, serializer: dict[str, Any]
    ) -> None:
        """Gough is not internally consistent about timestamp spelling.

        ``serialize_biome_group`` uses a bare ``.isoformat()`` (``+00:00``)
        while ``_serialize_node`` rewrites it to ``Z``. Both are real and both
        must parse, which is why ``parse_timestamp`` handles the pair.
        """
        raw = serializer["biome_group"]["created_at"]
        assert raw.endswith("+00:00"), "fixture no longer exercises the offset form"
        assert parse_timestamp(raw) is not None


class TestRealMetrics:
    """What Gough's ``/metrics`` really publishes."""

    def test_no_fleet_size_gauge_exists(self, real: dict[str, Any]) -> None:
        """Pins the reason the dashboard tiles stay list-derived.

        Gough publishes operational and security metrics only. There is no
        ``gough_nodes`` / ``gough_agents`` / ``gough_biomes`` gauge to source a
        fleet count from, so a card wired to ``metrics_summary`` for fleet size
        would render nothing. If this fails, Gough added one and the dashboard
        can finally use it.
        """
        families = real["metrics_families"]
        assert families, "fixture captured no gough metric families"
        for name in ("gough_nodes", "gough_agents", "gough_biomes"):
            assert name not in families

    def test_queue_depth_gauges_are_available(self, real: dict[str, Any]) -> None:
        """The metrics that DO exist, and that a card can legitimately use."""
        families = real["metrics_families"]
        assert "gough_provisioning_queue_depth" in families
        assert "gough_deployment_queue_depth" in families
