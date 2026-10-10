"""Behavioural tests for the Tobogganing adapter, and the envelope binding.

Fakes here are built from **Tobogganing's real payload shapes**, read out of its
handlers — not from what the mapper happens to want. A double that mirrors the
implementation's assumption cannot falsify it, which is how Phase 4G shipped a
``FakeGough`` that routed on keys copied from what the adapter sent.

The envelope tests are the important ones. Tobogganing names every collection
differently and **never** uses ``items``; had the adapter assumed one key, every
table would have rendered empty with nothing failing anywhere — the Phase 4N
defect. ``TestEnvelopeKeysAreTheProducts`` grades the adapter's table against
the key each registered handler really emits.
"""

from __future__ import annotations

from typing import Any, Final

import httpx
import pytest
from app.adapters.base import (
    AdapterCapabilityError,
    AdapterContext,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
)
from app.adapters.tobogganing import TobogganingAdapter
from app.adapters.tobogganing.mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_BLOCK_PAGE,
    KIND_LIST_ROUTES,
    KIND_SDWAN_CLIENT,
    KIND_SDWAN_CLUSTER,
    KIND_WIREGUARD_PEER,
    RESOURCE_KINDS,
    envelope_key,
)
from app.adapters.transport import Transport
from tobogganing_route_source import effective_envelope_table

pytestmark = pytest.mark.asyncio

_BASE: Final[str] = "https://tobogganing.example.test"


def _ctx() -> AdapterContext:
    """A context pointed at the fake origin."""
    return AdapterContext(
        connection_id=1,
        portal_tenant_id=1,
        external_id="tenant-1",
        external_kind="tenant",
        base_url=_BASE,
        auth_type="bearer",
        api_key="-".join(("not", "a", "real", "credential")),
        correlation_id="test-corr",
    )


#: Real SD-WAN cluster row shape — the exact field set
#: ``hub_api/api/headend_routes.py:646-655`` and
#: ``hub_api/modules/sdwan/api/clusters.py:271-283`` build.
_CLUSTER_ROW: Final[dict[str, Any]] = {
    "id": "cluster-1",
    "name": "eu-west",
    "region": "eu-west-1",
    "datacenter": "dc1",
    "status": "active",
    "client_count": 3,
}

#: Real block-page row shape — ``blockpages/api.py:111-124``.
_PAGE_ROW: Final[dict[str, Any]] = {
    "id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    "tenant": "tenant-1",
    "name": "Blocked",
    "markdown": "# nope",
    "status": "published",
    "version": 2,
    "created_by": "u1",
    "updated_by": "u1",
    "created_at": "2026-08-01T10:00:00+00:00",
    "updated_at": "2026-08-02T11:30:00+00:00",
}


class _Recorder:
    """Records the requests the adapter makes, and replays canned answers."""

    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        """Map ``"METHOD /path"`` to the response the product would give."""
        self.responses = responses
        self.seen: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer a request, recording the exact path the adapter built."""
        key = f"{request.method} {request.url.path}"
        self.seen.append(key)
        if key not in self.responses:
            # A 404 rather than a KeyError: the point of the fake is to behave
            # like the product, and the product 404s an unregistered path.
            return httpx.Response(404, json={"error": "not found"})
        return self.responses[key]


def _adapter_with(recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> TobogganingAdapter:
    """Build an adapter whose transport is backed by ``recorder``.

    ``follow_redirects=False`` mirrors the real transport, which is what makes
    the trailing-slash asymmetry observable in a test rather than being papered
    over by a silent 308 follow.
    """
    transport = Transport()
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder.handler),
        follow_redirects=False,
    )

    async def _get_transport() -> Transport:
        return transport

    # String form, never attribute assignment — mypy rejects assigning to a
    # module attribute that is not explicitly exported.
    monkeypatch.setattr("app.adapters.transport.get_transport", _get_transport)
    monkeypatch.setattr(
        "app.adapters.tobogganing.adapter.get_transport",
        _get_transport,
        raising=False,
    )
    adapter = TobogganingAdapter()
    monkeypatch.setattr(type(adapter), "_transport", staticmethod(_get_transport))
    return adapter


class TestEnvelopeKeysAreTheProducts:
    """The adapter's envelope table is graded by Tobogganing, not by a comment."""

    def test_every_kind_declares_an_envelope_key_and_a_list_route(self) -> None:
        """A kind with no key raises at the call site — assert it never happens."""
        assert set(COLLECTION_ENVELOPE_KEYS) == set(RESOURCE_KINDS)
        assert set(KIND_LIST_ROUTES) == set(RESOURCE_KINDS)

    def test_nothing_uses_the_items_envelope(self) -> None:
        """Pin the asymmetry itself, so a "tidy-up" to one key fails here.

        The Phase 4N defect was not a typo — it was the assumption that one
        envelope covered every collection. Tobogganing disproves it six times
        over, so the disproof is stated as a test.
        """
        assert "items" not in set(COLLECTION_ENVELOPE_KEYS.values())

    @pytest.mark.parametrize("kind", sorted(RESOURCE_KINDS))
    def test_each_key_is_the_one_the_registered_handler_emits(self, kind: str) -> None:
        """Graded against a live boot of the product (or the vendored copy)."""
        product = effective_envelope_table()
        route = KIND_LIST_ROUTES[kind]

        assert route in product, (
            f"tobogganing no longer serves a collection at {route!r} whose "
            f"envelope can be read (found {len(product)} such routes) — the "
            f"{kind!r} envelope key can no longer be verified. Run "
            f"`make refresh-product-source-fixtures`."
        )
        assert envelope_key(kind) == product[route], (
            f"{kind!r} is decoded from {envelope_key(kind)!r} but tobogganing's "
            f"{route} emits {product[route]!r} — the collection would decode as "
            f"empty and render as 'none'."
        )

    def test_unknown_kind_raises_rather_than_defaulting(self) -> None:
        """Defaulting to ``items`` is how a collection empties forever."""
        with pytest.raises(KeyError):
            envelope_key("not_a_kind")


class TestListResources:
    """Listing uses the product's real paths and real envelope keys."""

    async def test_lists_clusters_from_the_correct_path_and_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole chain: path shape, envelope key, mapping."""
        recorder = _Recorder(
            {
                "GET /api/v1/sdwan/clusters": httpx.Response(
                    200, json={"clusters": [_CLUSTER_ROW], "meta": {"version": 1}}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_SDWAN_CLUSTER, _ctx())

        assert recorder.seen == ["GET /api/v1/sdwan/clusters"]
        assert [r.id for r in page.items] == ["cluster-1"]
        assert page.items[0].name == "eu-west"
        assert page.items[0].status == "active"
        # Not modelled by a named contract field, so it must survive in metadata
        # rather than being silently dropped.
        assert page.items[0].metadata["region"] == "eu-west-1"
        assert page.items[0].metadata["client_count"] == 3
        assert page.total == 1

    async def test_lists_block_pages_and_parses_timestamps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SASE pages arrive under ``pages`` and carry no ``meta`` at all."""
        recorder = _Recorder(
            {"GET /api/v1/sase/blockpages/pages": httpx.Response(200, json={"pages": [_PAGE_ROW]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_BLOCK_PAGE, _ctx())

        assert [r.name for r in page.items] == ["Blocked"]
        created = page.items[0].created_at
        assert created is not None and created.tzinfo is not None

    async def test_an_absent_envelope_key_raises_rather_than_reporting_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE 4N regression: a missing key must never render as "none".

        A product response the adapter does not understand is an error. The
        alternative — an empty list — is indistinguishable from the factual
        "there are none", and that is what put "No snapshots have been taken"
        on Nest's screen unconditionally.
        """
        recorder = _Recorder(
            {
                "GET /api/v1/sdwan/wireguard/peers": httpx.Response(
                    200,
                    json={"items": [], "meta": {}},  # the WRONG key
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamError) as excinfo:
            await adapter.list_resources(KIND_WIREGUARD_PEER, _ctx())

        assert "peers" in str(excinfo.value)
        assert "refusing to report it as empty" in str(excinfo.value)

    async def test_an_empty_collection_is_reported_as_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The counterpart: a real empty list is not an error.

        Without this, the guard above could be satisfied by an adapter that
        simply fails on every empty collection, which would be a new defect.
        """
        recorder = _Recorder(
            {
                "GET /api/v1/sdwan/wireguard/peers": httpx.Response(
                    200, json={"peers": [], "total": 0}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_WIREGUARD_PEER, _ctx())
        assert page.items == []
        assert page.total == 0

    async def test_unknown_kind_is_a_capability_error(self) -> None:
        """501, not an empty page — the two readings are different answers."""
        with pytest.raises(AdapterCapabilityError):
            await TobogganingAdapter().list_resources("vm", _ctx())


class TestGetResource:
    """Item reads filter the collection, because the product serves no item route."""

    async def test_returns_the_matching_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """It must query the COLLECTION, never invent an item path."""
        recorder = _Recorder(
            {"GET /api/v1/sdwan/clusters": httpx.Response(200, json={"clusters": [_CLUSTER_ROW]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        resource = await adapter.get_resource(KIND_SDWAN_CLUSTER, "cluster-1", _ctx())

        assert resource.id == "cluster-1"
        assert recorder.seen == ["GET /api/v1/sdwan/clusters"]

    async def test_missing_row_raises_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A genuine absence is a 404, not an empty object."""
        recorder = _Recorder(
            {"GET /api/v1/sdwan/clusters": httpx.Response(200, json={"clusters": []})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_resource(KIND_SDWAN_CLUSTER, "cluster-9", _ctx())


class TestErrorMapping:
    """Tobogganing's statuses map onto the shared taxonomy."""

    @pytest.mark.parametrize("status", [401, 403])
    async def test_both_refusal_statuses_become_upstream_auth_errors(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        """403 here is NOT "this operator may not" — the portal already checked.

        Tobogganing answers 403 from ``@require_scope`` and 401 from
        ``@require_machine_jwt``; both mean the STORED credential was refused,
        so both must become a 502-class upstream error rather than a 401 that
        would tell the browser to re-login and fix nothing.
        """
        recorder = _Recorder(
            {
                "GET /api/v1/sdwan/clients": httpx.Response(
                    status, json={"error": "Forbidden: insufficient privileges"}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamAuthError):
            await adapter.list_resources(KIND_SDWAN_CLIENT, _ctx())

    async def test_402_is_a_capability_error_not_an_authorization_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``@require_feature`` answers 402 when a module is disabled.

        Mapping it to a permission error would send an operator to check
        permissions that are fine; it is a licence/flag state.
        """
        recorder = _Recorder(
            {
                "GET /api/v1/sase/blockpages/pages": httpx.Response(
                    402, json={"error": "feature not enabled"}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(AdapterCapabilityError):
            await adapter.list_resources(KIND_BLOCK_PAGE, _ctx())


class TestCapabilities:
    """capabilities() must tell the truth about what is implemented."""

    async def test_reports_what_it_implements_and_no_operations(self) -> None:
        """Tobogganing has no async operations, so none may be claimed."""
        reported = await TobogganingAdapter().capabilities(_ctx())

        assert "health" in reported
        assert {"list_resources", "get_resource"} <= set(reported)
        for absent in (
            "list_operations",
            "get_operation",
            "cancel_operation",
            "operation_logs",
            "metrics_summary",
        ):
            assert absent not in reported

    async def test_health_endpoint_is_the_one_the_product_registers(self) -> None:
        """``/healthz`` is registered nowhere; the default would 404."""
        assert TobogganingAdapter.HEALTH_ENDPOINT == "/health"
