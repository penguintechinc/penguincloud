"""Behavioural tests for the WaddleAI adapter, and the envelope binding.

Fakes here are built from **WaddleAI's real payload shapes**, read out of its
own handler source (``services/management/app/api/v1/{providers,knowledge,
quotas}.py``, ``penguintechinc/waddleai``) — not from what the mapper
happens to want, matching :mod:`tests.api.test_tobogganing_adapter`'s own
stated rationale for why that distinction matters.
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
)
from app.adapters.transport import Transport
from app.adapters.waddleai import WaddleAIAdapter
from app.adapters.waddleai.mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_KNOWLEDGE_DOCUMENT,
    KIND_PROVIDER,
    KIND_QUOTA,
    RESOURCE_KINDS,
    envelope_key,
)

pytestmark = pytest.mark.asyncio

_BASE: Final[str] = "https://waddleai.example.test"


def _ctx() -> AdapterContext:
    """A context pointed at the fake origin, tenanted by organization_id."""
    return AdapterContext(
        connection_id=1,
        portal_tenant_id=1,
        external_id="org-1",
        external_kind="organization_id",
        base_url=_BASE,
        auth_type="bearer",
        api_key="-".join(("not", "a", "real", "credential")),
        correlation_id="test-corr",
    )


#: Real provider row shape — ``providers.py``'s ``list_providers()`` builds
#: exactly these keys, byte-equal to ``ProviderSummary``.
_PROVIDER_ROW: Final[dict[str, Any]] = {
    "id": 1,
    "name": "openai-primary",
    "provider_type": "openai",
    "endpoint_url": "https://api.openai.com/v1",
    "model_list": ["gpt-4o", "gpt-4o-mini"],
    "rate_limits": {"rpm": 60},
    "enabled": True,
    "priority": 1,
    "ailb_sync_enabled": False,
    "created_at": "2026-08-01T10:00:00",
}

#: Real knowledge-document row shape — ``knowledge.py``'s ``_serialize``.
_KNOWLEDGE_ROW: Final[dict[str, Any]] = {
    "id": 7,
    "content": "# Runbook\nDo the thing.",
    "source": "runbook.md",
    "provenance": {"source_filename": "runbook.md", "uploader_user_id": 3},
    "created_at": "2026-08-02T11:30:00",
}

#: Real quota rows — ``quotas.py``'s ``list_quotas()``, one of each type.
_ORG_QUOTA_ROW: Final[dict[str, Any]] = {
    "type": "organization",
    "id": 1,
    "name": "Acme",
    "token_quota_daily": 100000,
    "token_quota_monthly": 2000000,
    "enabled": True,
}
_KEY_QUOTA_ROW: Final[dict[str, Any]] = {
    "type": "key",
    "id": 1,
    "name": "prod-key",
    "user_id": 3,
    "organization_id": 1,
    "budget_limit_daily": 10.0,
    "budget_limit_monthly": 250.0,
    "tpm_limit": 1000,
    "rpm_limit": 60,
    "enabled": True,
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
            return httpx.Response(404, json={"error": "not found"})
        return self.responses[key]


def _adapter_with(recorder: _Recorder, monkeypatch: pytest.MonkeyPatch) -> WaddleAIAdapter:
    """Build an adapter whose transport is backed by ``recorder``."""
    transport = Transport()
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder.handler),
        follow_redirects=False,
    )

    async def _get_transport() -> Transport:
        return transport

    monkeypatch.setattr("app.adapters.transport.get_transport", _get_transport)
    monkeypatch.setattr(
        "app.adapters.waddleai.adapter.get_transport",
        _get_transport,
        raising=False,
    )
    adapter = WaddleAIAdapter()
    monkeypatch.setattr(type(adapter), "_transport", staticmethod(_get_transport))
    return adapter


class TestEnvelopeKeysAreTheProducts:
    """The adapter's envelope table is graded by WaddleAI's own handlers."""

    def test_every_kind_declares_an_envelope_key(self) -> None:
        """Every RESOURCE_KINDS entry has a declared envelope key."""
        assert set(COLLECTION_ENVELOPE_KEYS) == set(RESOURCE_KINDS)

    def test_nothing_uses_the_items_envelope(self) -> None:
        """None of the three routes answers under ``items`` — pin it as a test."""
        assert "items" not in set(COLLECTION_ENVELOPE_KEYS.values())

    def test_unknown_kind_raises_rather_than_defaulting(self) -> None:
        """Defaulting to "items" is how a collection empties forever."""
        with pytest.raises(KeyError):
            envelope_key("not_a_kind")


class TestListResources:
    """Listing uses the product's real paths and real envelope keys."""

    async def test_lists_providers_from_the_correct_path_and_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole chain: path shape, envelope key, mapping."""
        recorder = _Recorder(
            {
                "GET /api/v1/providers": httpx.Response(
                    200, json={"providers": [_PROVIDER_ROW], "total": 1}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_PROVIDER, _ctx())

        assert recorder.seen == ["GET /api/v1/providers"]
        assert [r.id for r in page.items] == ["1"]
        assert page.items[0].name == "openai-primary"
        assert page.items[0].status == "enabled"
        # Not modelled by a named contract field, so it must survive in metadata.
        assert page.items[0].metadata["provider_type"] == "openai"
        assert page.items[0].metadata["model_list"] == ["gpt-4o", "gpt-4o-mini"]
        assert page.total == 1

    async def test_lists_knowledge_documents_and_parses_timestamps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Documents arrive under "documents" and carry no boolean-shaped field."""
        recorder = _Recorder(
            {"GET /api/v1/knowledge": httpx.Response(200, json={"documents": [_KNOWLEDGE_ROW]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_KNOWLEDGE_DOCUMENT, _ctx())

        assert [r.name for r in page.items] == ["runbook.md"]
        created = page.items[0].created_at
        assert created is not None and created.tzinfo is not None
        assert page.items[0].status is None  # no boolean-shaped field on this kind

    async def test_lists_heterogeneous_quota_rows_in_one_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Org, user, and key rows all arrive under the same ``quotas`` key."""
        recorder = _Recorder(
            {
                "GET /api/v1/quotas": httpx.Response(
                    200,
                    json={"quotas": [_ORG_QUOTA_ROW, _KEY_QUOTA_ROW], "total": 2},
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(KIND_QUOTA, _ctx())

        assert [r.name for r in page.items] == ["Acme", "prod-key"]
        assert page.items[0].metadata["type"] == "organization"
        assert page.items[1].metadata["type"] == "key"
        # Org row has no budget_limit_daily; key row has no token_quota_daily.
        assert "budget_limit_daily" not in page.items[0].metadata
        assert "token_quota_daily" not in page.items[1].metadata

    async def test_an_absent_envelope_key_raises_rather_than_reporting_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing key must never render as "none" -- the Phase 4N regression."""
        recorder = _Recorder(
            {"GET /api/v1/providers": httpx.Response(200, json={"items": [], "total": 0})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        from app.adapter_errors import UpstreamError

        with pytest.raises(UpstreamError) as excinfo:
            await adapter.list_resources(KIND_PROVIDER, _ctx())

        assert "providers" in str(excinfo.value)
        assert "refusing to report it as empty" in str(excinfo.value)

    async def test_unknown_kind_is_a_capability_error(self) -> None:
        """501, not an empty page -- the two readings are different answers."""
        with pytest.raises(AdapterCapabilityError):
            await WaddleAIAdapter().list_resources("vm", _ctx())


class TestGetResource:
    """Item reads filter the collection for two kinds, and refuse for quota."""

    async def test_returns_the_matching_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """It must query the COLLECTION, never invent an item path."""
        recorder = _Recorder(
            {"GET /api/v1/providers": httpx.Response(200, json={"providers": [_PROVIDER_ROW]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        resource = await adapter.get_resource(KIND_PROVIDER, "1", _ctx())

        assert resource.id == "1"
        assert recorder.seen == ["GET /api/v1/providers"]

    async def test_missing_provider_raises_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A genuine absence is a 404, not an empty object."""
        recorder = _Recorder({"GET /api/v1/providers": httpx.Response(200, json={"providers": []})})
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_resource(KIND_PROVIDER, "9", _ctx())

    async def test_returns_the_matching_knowledge_document(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The same filter-the-collection strategy, for the second kind."""
        recorder = _Recorder(
            {"GET /api/v1/knowledge": httpx.Response(200, json={"documents": [_KNOWLEDGE_ROW]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        resource = await adapter.get_resource(KIND_KNOWLEDGE_DOCUMENT, "7", _ctx())

        assert resource.id == "7"

    async def test_quota_get_resource_refuses_rather_than_risking_the_wrong_row(
        self,
    ) -> None:
        """No network call at all: the refusal is structural, not a fetch that fails.

        WaddleAI ids are not unique across the three quota row types — see
        ``adapter.py``'s docstring. A wrong-row answer would be worse than a
        501.
        """
        with pytest.raises(AdapterCapabilityError, match="not unique"):
            await WaddleAIAdapter().get_resource(KIND_QUOTA, "1", _ctx())


class TestErrorMapping:
    """WaddleAI's statuses map onto the shared taxonomy."""

    @pytest.mark.parametrize("status", [401, 403])
    async def test_both_refusal_statuses_become_upstream_auth_errors(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        """401 (require_auth) and 403 (require_scope) both describe the STORED credential.

        Neither is a statement about the portal caller's own authorization —
        the portal already enforced that before the adapter was reached.
        """
        recorder = _Recorder(
            {
                "GET /api/v1/providers": httpx.Response(
                    status, json={"error": "Insufficient permissions"}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamAuthError):
            await adapter.list_resources(KIND_PROVIDER, _ctx())

    async def test_feature_disabled_404_is_a_resource_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``knowledge_ingest`` disabled answers a plain 404 -- see responses.py."""
        recorder = _Recorder(
            {
                "GET /api/v1/knowledge": httpx.Response(
                    404, json={"error": "knowledge_ingest feature disabled"}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(ResourceNotFoundError, match="knowledge_ingest feature disabled"):
            await adapter.list_resources(KIND_KNOWLEDGE_DOCUMENT, _ctx())


class TestCapabilities:
    """capabilities() must tell the truth about what is implemented."""

    async def test_reports_what_it_implements_and_no_operations(self) -> None:
        """WaddleAI has no async operations on this cut, so none may be claimed."""
        reported = await WaddleAIAdapter().capabilities(_ctx())

        assert "health" in reported
        assert {"list_resources", "get_resource"} <= set(reported)
        for absent in (
            "create_resource",
            "update_resource",
            "delete_resource",
            "perform_action",
            "list_operations",
            "get_operation",
            "cancel_operation",
            "operation_logs",
            "metrics_summary",
        ):
            assert absent not in reported

    async def test_health_endpoint_is_the_one_the_product_registers(self) -> None:
        """``/healthz`` is what ``services/management/app/__init__.py`` registers."""
        assert WaddleAIAdapter.HEALTH_ENDPOINT == "/healthz"
