"""NestAdapter behaviour: error taxonomy, mapping, and a real-Nest run.

Two layers, and the second is the one that matters most.

``TestAgainstMockTransport`` drives the adapter through
:class:`httpx.MockTransport` — what respx itself drives underneath, so it
needs no dependency this environment cannot install (the interpreter is
PEP-668 externally managed). It covers the shapes a live instance will not
produce on demand: 409, 429, a malformed body.

``TestAgainstLiveNest`` constructs Nest's OWN Quart app and serves it over
httpx's ASGI transport, so routing, middleware, handlers, status codes and
serializers are Nest's real code rather than this file's idea of them. That
distinction is not academic: the create-payload alias asserted below was
found by this layer and contradicted both Nest's committed spec and the
mock-shaped assumption that preceded it. A mock keyed on what the adapter
sends cannot falsify the adapter.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.adapters.base import (
    AdapterCapabilityError,
    AdapterContext,
    OperationState,
    RateLimitedError,
    ResourceConflictError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamValidationError,
)
from app.adapters.nest import NestAdapter
from app.adapters.nest.mapping import to_create_payload, to_operation, to_resource
from app.adapters.transport import Transport

from nest_route_source import missing_reason, nest_api_module
from product_source_fixtures import source_required

_TENANT = "acme-prod"

#: Nest's app module is executed once per session under this name — it
#: registers Prometheus collectors at import time and cannot be re-executed.
_LIVE_MODULE_NAME = "nest_api_app_under_test"


def _ctx() -> AdapterContext:
    """A context pointing at an origin the mock transport answers for."""
    return AdapterContext(
        connection_id=1,
        portal_tenant_id=1,
        external_id=_TENANT,
        external_kind="tenant",
        base_url="https://nest.invalid",
        auth_type="bearer",
        api_key="-".join(("not", "a", "real", "credential")),
        correlation_id="test-corr",
    )


class _Recorder:
    """Captures the requests an adapter makes and replies from a script.

    A named class rather than a closure over ``list.append`` because mypy
    rejects using ``append``'s return value, and because the recorded
    requests are asserted on — the point of several tests below is WHAT the
    adapter sent, not only what it did with the reply.
    """

    def __init__(self, replies: dict[tuple[str, str], httpx.Response]) -> None:
        """Store the ``(method, path) -> response`` script."""
        self.replies = replies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Record the request and return its scripted reply, or a 404."""
        self.requests.append(request)
        key = (request.method.upper(), request.url.path)
        return self.replies.get(
            key,
            httpx.Response(
                404,
                json={
                    "code": "nest.api.not_found",
                    "message": "Not found",
                },
            ),
        )


def _adapter_with(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> NestAdapter:
    """Build an adapter whose transport is backed by ``recorder``."""
    transport = Transport()
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(recorder),
        follow_redirects=False,
    )

    async def _get_transport() -> Transport:
        return transport

    # String form, never attribute assignment — mypy rejects assigning to a
    # module attribute that is not explicitly exported.
    monkeypatch.setattr("app.adapters.transport.get_transport", _get_transport)
    monkeypatch.setattr(
        "app.adapters.nest.adapter.get_transport", _get_transport, raising=False
    )
    adapter = NestAdapter()
    monkeypatch.setattr(
        type(adapter), "_transport", staticmethod(_get_transport)
    )
    return adapter


class TestCreatePayloadAliasing:
    """Nest reads different field names than it writes."""

    def test_data_resource_create_is_rewritten_to_the_wire_names(self) -> None:
        """``resourceType``/``storageClass`` become ``type``/``class``.

        Regression for a live-verified defect: Nest's create handler reads
        ``type`` and ``class`` (``handlers/dataresource.py:103-104``) while
        its serializer emits ``resourceType`` and ``storageClass``
        (``models.py:75,77``), so a payload built from a resource just READ is
        rejected with ``400 name and type are required``.

        What was verified live is that asymmetry — request shape against
        response shape. **Not** a spec-vs-handler contradiction: the spec's
        ``CreateDataResourceRequest`` (``openapi/v1.yaml:1018``) is
        ``required: [name, type]`` with ``type``/``class`` and agrees with the
        handler; ``resourceType``/``storageClass`` are its *response* schema
        (``:1048``). An earlier version of this docstring said the opposite
        and presented it as live-verified evidence.
        """
        body = to_create_payload(
            "database",
            {"name": "db1", "resourceType": "postgres", "storageClass": "gp3"},
        )
        assert body == {"name": "db1", "type": "postgres", "class": "gp3"}

    def test_wire_names_are_passed_through_untouched(self) -> None:
        """A caller already speaking Nest's format must be unaffected."""
        body = to_create_payload(
            "database", {"name": "db1", "type": "postgres", "class": "gp3"}
        )
        assert body == {"name": "db1", "type": "postgres", "class": "gp3"}

    def test_an_explicit_wire_value_wins_over_its_alias(self) -> None:
        """Never let an alias silently overwrite an explicit value."""
        body = to_create_payload(
            "database", {"name": "db1", "type": "postgres", "resourceType": "object"}
        )
        assert body["type"] == "postgres"

    def test_kinds_without_an_asymmetry_are_untouched(self) -> None:
        """Only DataResource is asymmetric; the rest must not be rewritten."""
        payload = {"name": "snap1", "sourcePVC": "db1", "snapshotClass": "rbd"}
        assert to_create_payload("snapshot", payload) == payload


class TestMapping:
    """Payload → DTO mapping, including the contract's ``result`` channel."""

    def test_operation_carries_result_and_verbatim_status(self) -> None:
        """``state`` normalises for control flow, ``status`` stays verbatim."""
        operation = to_operation(
            {
                "id": "op-1",
                "tenant": _TENANT,
                "type": "snapshot",
                "resource": "db1",
                "phase": "Succeeded",
                "startedAt": "2026-08-08T10:00:00Z",
                "completedAt": "2026-08-08T10:05:00Z",
                "result": {"snapshot": "db1-2026-08-08"},
            }
        )
        assert operation.state is OperationState.SUCCEEDED
        assert operation.status == "Succeeded"
        assert operation.result == {"snapshot": "db1-2026-08-08"}
        assert operation.state.is_terminal
        assert operation.completed_at is not None

    def test_operation_progress_is_never_synthesised(self) -> None:
        """Nest publishes nothing countable, so a fraction would be invented."""
        for phase in ("Pending", "Running", "Succeeded", "Failed"):
            assert to_operation({"id": "x", "phase": phase}).progress is None

    def test_failed_operation_keeps_nests_reason(self) -> None:
        """``error`` is the FAILED counterpart of ``result``."""
        operation = to_operation(
            {"id": "op-2", "phase": "Failed", "error": "volume unavailable"}
        )
        assert operation.state is OperationState.FAILED
        assert operation.error == "volume unavailable"

    def test_snapshot_records_its_source_as_a_parent_edge(self) -> None:
        """Without the edge the portal can only render flat lists."""
        resource = to_resource(
            "snapshot", {"name": "snap1", "sourcePVC": "db1", "readyToUse": True}
        )
        assert resource.parent_id == "db1"
        assert resource.parent_kind == "database"

    def test_identity_is_the_name_not_the_uuid(self) -> None:
        """Every Nest route addresses a resource by name, not by id."""
        resource = to_resource(
            "database", {"id": "uuid-here", "name": "db1", "phase": "ready"}
        )
        assert resource.id == "db1"
        assert resource.metadata["nest_id"] == "uuid-here"
        assert resource.status == "ready"


@pytest.mark.asyncio
class TestAgainstMockTransport:
    """Status codes a live instance will not produce on demand."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (400, UpstreamValidationError),
            (401, UpstreamAuthError),
            (403, UpstreamAuthError),
            (404, ResourceNotFoundError),
            (409, ResourceConflictError),
            (429, RateLimitedError),
            (500, UpstreamError),
            (503, UpstreamError),
        ],
    )
    async def test_status_maps_onto_the_shared_taxonomy(
        self, status: int, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each status becomes the error the portal renders correctly.

        401/403 are deliberately NOT a 401 at the portal boundary: they mean
        the STORED credential was refused, so telling the browser to
        re-login would fix nothing.
        """
        path = f"/api/v1/tenants/{_TENANT}/data-resources"
        recorder = _Recorder(
            {
                ("GET", path): httpx.Response(
                    status,
                    json={"code": "nest.test.failure", "message": "nope"},
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(expected):
            await adapter.list_resources("database", _ctx())

    async def test_rate_limit_carries_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A throttle must be distinguishable from an outage, with its delay."""
        path = f"/api/v1/tenants/{_TENANT}/data-resources"
        recorder = _Recorder(
            {("GET", path): httpx.Response(429, headers={"Retry-After": "30"})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(RateLimitedError) as excinfo:
            await adapter.list_resources("database", _ctx())
        assert excinfo.value.retry_after == 30.0

    async def test_error_message_carries_nests_own_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``code`` is stable and searchable; ``message`` is prose."""
        path = f"/api/v1/tenants/{_TENANT}/data-resources/db1"
        recorder = _Recorder(
            {
                ("GET", path): httpx.Response(
                    404,
                    json={
                        "code": "nest.dataresource.not_found",
                        "message": "DataResource not found",
                    },
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(ResourceNotFoundError) as excinfo:
            await adapter.get_resource("database", "db1", _ctx())
        assert "nest.dataresource.not_found" in str(excinfo.value)

    async def test_a_non_list_collection_is_an_upstream_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed body must not read as an empty account."""
        path = f"/api/v1/tenants/{_TENANT}/data-resources"
        recorder = _Recorder(
            {("GET", path): httpx.Response(200, json={"items": "not-a-list"})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamError):
            await adapter.list_resources("database", _ctx())

    async def test_has_more_is_derived_by_overfetching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nest reports no total, so ``has_more`` is the only honest signal.

        Also asserts the adapter asks for one row MORE than requested — the
        mechanism the flag depends on. Without that assertion the flag could
        be right by luck on a short page.
        """
        path = f"/api/v1/tenants/{_TENANT}/data-resources"
        rows = [{"name": f"db{index}", "phase": "ready"} for index in range(4)]
        recorder = _Recorder({("GET", path): httpx.Response(200, json={"items": rows})})
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources("database", _ctx(), per_page=3)

        assert [row.id for row in page.items] == ["db0", "db1", "db2"]
        assert page.has_more is True
        assert page.total is None
        assert recorder.requests[0].url.params["limit"] == "4"
        assert recorder.requests[0].url.params["offset"] == "0"

    async def test_paths_carry_no_trailing_slash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nest 404s a trailing slash with no redirect back."""
        path = f"/api/v1/tenants/{_TENANT}/data-resources"
        recorder = _Recorder({("GET", path): httpx.Response(200, json={"items": []})})
        adapter = _adapter_with(recorder, monkeypatch)

        await adapter.list_resources("database", _ctx())

        assert recorder.requests[0].url.path == path
        assert not recorder.requests[0].url.path.endswith("/")

    async def test_the_tenant_in_the_path_is_the_mapped_external_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The caller never supplies a tenant; the mapping does."""
        path = f"/api/v1/tenants/{_TENANT}/snapshots"
        recorder = _Recorder(
            {("GET", path): httpx.Response(200, json={"snapshots": []})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        await adapter.list_resources("snapshot", _ctx())

        assert f"/tenants/{_TENANT}/" in recorder.requests[0].url.path

    @pytest.mark.parametrize(
        ("kind", "collection", "key"),
        [
            ("database", "data-resources", "items"),
            ("snapshot", "snapshots", "snapshots"),
            ("protection_policy", "protection-policies", "policies"),
            ("search_pool", "search-pools", "searchPools"),
        ],
    )
    async def test_each_kind_is_read_from_its_own_envelope_key(
        self,
        kind: str,
        collection: str,
        key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Nest names a different key per collection; only one is ``items``.

        The literal key is written out here rather than taken from
        ``COLLECTION_ENVELOPE_KEYS`` on purpose: a test that feeds the table
        back into itself passes while the table is wrong, which is exactly how
        three of four kinds shipped decoding as permanently empty. These four
        strings come from Nest's handlers (``protection.py:26``, ``:206``,
        ``searchpool.py:25``, ``dataresource.py:47``), and
        ``test_nest_envelopes.py`` asserts them against that source directly.
        """
        path = f"/api/v1/tenants/{_TENANT}/{collection}"
        rows = [{"name": "row-a"}, {"name": "row-b"}]
        recorder = _Recorder({("GET", path): httpx.Response(200, json={key: rows})})
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources(kind, _ctx())

        assert [row.id for row in page.items] == ["row-a", "row-b"]

    @pytest.mark.parametrize(
        ("kind", "collection"),
        [
            ("snapshot", "snapshots"),
            ("protection_policy", "protection-policies"),
            ("search_pool", "search-pools"),
        ],
    )
    async def test_the_data_resource_envelope_does_not_decode_other_kinds(
        self, kind: str, collection: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reading ``items`` everywhere is the defect; prove it now fails.

        Before the per-kind table this body decoded to ``[]`` and the screen
        stated "No snapshots have been taken from this resource" as fact. An
        unrecognised shape must surface, not render as "none".
        """
        path = f"/api/v1/tenants/{_TENANT}/{collection}"
        recorder = _Recorder(
            {("GET", path): httpx.Response(200, json={"items": [{"name": "x"}]})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamError) as excinfo:
            await adapter.list_resources(kind, _ctx())
        assert "refusing to report it as empty" in str(excinfo.value)

    async def test_an_absent_envelope_key_is_never_an_empty_collection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shape this adapter was not written against is an error.

        Every Nest list handler builds its key unconditionally, so an empty
        collection still arrives as ``{"snapshots": []}``. A missing key
        therefore cannot mean "none" — and reporting it as none is a false
        statement to the operator, not a graceful degradation.
        """
        path = f"/api/v1/tenants/{_TENANT}/snapshots"
        recorder = _Recorder(
            {("GET", path): httpx.Response(200, json={"meta": {"count": 0}})}
        )
        adapter = _adapter_with(recorder, monkeypatch)

        with pytest.raises(UpstreamError):
            await adapter.list_resources("snapshot", _ctx())

    async def test_a_genuinely_empty_collection_is_still_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strictness must not turn "none yet" into an error.

        The key present with an empty list is Nest's real answer for an empty
        collection, and it has to keep rendering as an empty table.
        """
        path = f"/api/v1/tenants/{_TENANT}/snapshots"
        recorder = _Recorder(
            {
                ("GET", path): httpx.Response(
                    200, json={"snapshots": [], "meta": {"count": 0}}
                )
            }
        )
        adapter = _adapter_with(recorder, monkeypatch)

        page = await adapter.list_resources("snapshot", _ctx())

        assert page.items == []
        assert page.has_more is False

    async def test_unsupported_kinds_and_actions_raise_501(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """501, never an empty result that reads as "nothing there"."""
        adapter = _adapter_with(_Recorder({}), monkeypatch)
        ctx = _ctx()

        with pytest.raises(AdapterCapabilityError):
            await adapter.list_resources("vm", ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.perform_action("database", "db1", "reboot", None, ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.perform_action("snapshot", "s1", "restore", None, ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.get_resource("snapshot", "s1", ctx)
        with pytest.raises(AdapterCapabilityError):
            await adapter.get_operation("deployment", "op-1", ctx)


@pytest.mark.asyncio
class TestAgainstLiveNest:
    """The adapter against Nest's real Quart app, over an ASGI transport.

    Skipped where no Nest checkout is present (CI runners), which is why the
    mock layer above still carries the taxonomy cases.
    """

    @staticmethod
    def _live_app() -> Any:
        """Construct Nest's real api app with its in-memory store.

        Loaded under a distinct module name because Nest's top-level
        ``app.py`` would otherwise collide with the portal's own ``app``
        package in ``sys.modules``.

        The module is executed at most ONCE per session and cached: it
        registers Prometheus collectors at import time, and a second exec
        raises ``Duplicated timeseries in CollectorRegistry``. ``create_app``
        itself is re-callable, so each test still gets a fresh store.
        """
        import importlib.util
        import sys

        module_path = nest_api_module()
        assert module_path is not None
        api_root = str(module_path.parent)
        if api_root not in sys.path:
            sys.path.insert(0, api_root)

        store_module = pytest.importorskip(
            "store", reason="nest's own dependencies are not installed here"
        )

        module = sys.modules.get(_LIVE_MODULE_NAME)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                _LIVE_MODULE_NAME, str(module_path)
            )
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[_LIVE_MODULE_NAME] = module
            spec.loader.exec_module(module)
        return module.create_app(store_module.MemoryStore())

    @pytest.fixture
    def live(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[NestAdapter]:
        """An adapter wired to Nest's real app, with auth satisfied.

        Nest validates RS256 tokens against a JWKS URL and fails closed
        without one, so a single-key JWKS is served on a real socket — its
        fetch is blocking ``requests``, which no in-process stub intercepts.

        This class is the one thing that genuinely cannot be vendored: it
        EXECUTES Nest's Quart app, so it needs Nest's dependencies installed
        and not merely its source. It therefore still skips without a
        checkout — but ``REQUIRE_PRODUCT_SOURCE=1`` (``make test-api-live``)
        turns that skip into a failure, so a job that is supposed to have the
        checkout reports its absence instead of quietly covering less.
        """
        if nest_api_module() is None:
            if source_required():
                pytest.fail(missing_reason())
            pytest.skip(missing_reason())
        pytest.importorskip("quart")
        pytest.importorskip("opentelemetry")
        jwt_module = pytest.importorskip("jwt")
        rsa = pytest.importorskip(
            "cryptography.hazmat.primitives.asymmetric.rsa"
        )

        import base64
        import sys
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = key.public_key().public_numbers()

        def b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        document = json.dumps(
            {
                "keys": [
                    {
                        "kty": "RSA",
                        "kid": "test-key",
                        "use": "sig",
                        "alg": "RS256",
                        "n": b64(numbers.n),
                        "e": b64(numbers.e),
                    }
                ]
            }
        ).encode()

        class _JWKS(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(document)))
                self.end_headers()
                self.wfile.write(document)

            def log_message(self, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), _JWKS)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        monkeypatch.setenv(
            "OIDC_JWKS_URL", f"http://127.0.0.1:{server.server_port}/jwks"
        )
        monkeypatch.setenv("OIDC_ISSUER", "https://issuer.invalid/")
        monkeypatch.setenv("OIDC_AUDIENCE", "nest-api")

        now = int(time.time())
        self.token = jwt_module.encode(
            {
                "sub": "portal-service-account",
                "tenant": _TENANT,
                "scope": " ".join(
                    f"nest:{area}:{action}"
                    for area in (
                        "catalog",
                        "dataresource",
                        "snapshot",
                        "policy",
                        "searchpool",
                        "operations",
                    )
                    for action in ("read", "write", "delete")
                ),
                "aud": "nest-api",
                "iss": "https://issuer.invalid/",
                "iat": now,
                "exp": now + 3600,
            },
            key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

        nest_app = self._live_app()

        # Nest caches JWKS for five minutes in a module-level global. Each
        # test mints a fresh key, so without clearing it the second test's
        # token is verified against the first test's public key and fails
        # with "Signature verification failed" — real Nest behaviour, and a
        # caching property worth leaving visible rather than designing around.
        # Reached through sys.modules rather than an import statement:
        # it is Nest's module, present only once Nest's app has been
        # loaded above, and importing it by name would be an unresolvable
        # first-party-looking import to any static checker.
        nest_tenant = sys.modules.get("middleware.tenant")
        assert nest_tenant is not None, "nest's app did not load its middleware"
        nest_tenant._JWKS_CACHE.clear()

        transport = Transport()
        transport._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=nest_app),
            follow_redirects=False,
        )

        async def _get_transport() -> Transport:
            return transport

        monkeypatch.setattr(
            "app.adapters.transport.get_transport", _get_transport
        )
        adapter = NestAdapter()
        monkeypatch.setattr(
            type(adapter), "_transport", staticmethod(_get_transport)
        )
        yield adapter
        server.shutdown()

    def _live_ctx(self) -> AdapterContext:
        """A context holding a token Nest's own middleware accepts."""
        return AdapterContext(
            connection_id=1,
            portal_tenant_id=1,
            external_id=_TENANT,
            external_kind="tenant",
            base_url="http://nest.invalid",
            auth_type="bearer",
            api_key=self.token,
            correlation_id="live",
        )

    async def test_health_endpoint_is_the_one_nest_registers(
        self, live: NestAdapter
    ) -> None:
        """Regression: the inherited ``/healthz`` default 404s against Nest.

        Nest registers ``/health`` and ``/ready`` and no ``/healthz``
        anywhere, so a portal probing the default would report every healthy
        Nest as unhealthy.
        """
        result = await live.health(self._live_ctx())
        assert result.status == "healthy"
        assert result.status_code == 200

    async def test_create_list_act_poll_delete_round_trip(
        self, live: NestAdapter
    ) -> None:
        """The whole flow a Databases screen performs, against real handlers.

        This is the test the create-payload alias was found by: sending the
        spec's ``resourceType``/``storageClass`` here returns
        ``400 name and type are required`` from Nest's own handler.
        """
        ctx = self._live_ctx()

        created = await live.create_resource(
            "database",
            {"name": "orders", "resourceType": "postgres", "storageClass": "gp3"},
            ctx,
        )
        assert created.id == "orders"
        assert created.metadata["operationId"]

        page = await live.list_resources("database", ctx)
        assert [row.id for row in page.items] == ["orders"]
        assert page.total is None

        detail = await live.get_resource("database", "orders", ctx)
        assert detail.status is not None
        assert detail.created_at is not None

        action = await live.perform_action("database", "orders", "snapshot", None, ctx)
        assert action.accepted
        assert len(action.operations) == 1

        operation = await live.get_operation(
            "operation", action.operations[0].id, ctx
        )
        assert operation.id == action.operations[0].id
        assert operation.status
        assert operation.progress is None

        await live.delete_resource("database", "orders", ctx)
        assert await live.list_resources("database", ctx) is not None

    @pytest.mark.parametrize(
        "kind", ["database", "snapshot", "protection_policy", "search_pool"]
    )
    async def test_every_kind_decodes_against_the_real_handlers(
        self, kind: str, live: NestAdapter
    ) -> None:
        """Each collection is read from the key its OWN handler emits.

        Against the real service, so the envelope key is graded by Nest rather
        than by a mock built from the same assumption. Reading ``items`` for
        all four (the shipped behaviour) raises here for three of them.
        """
        page = await live.list_resources(kind, self._live_ctx())

        assert page.items == [] or all(row.kind == kind for row in page.items)

    async def test_missing_resource_is_a_not_found_not_an_outage(
        self, live: NestAdapter
    ) -> None:
        """Nest's real 404 envelope must reach the portal as 404."""
        with pytest.raises(ResourceNotFoundError):
            await live.get_resource("database", "nope", self._live_ctx())

    async def test_unreachable_surfaces_raise_rather_than_return_empty(
        self, live: NestAdapter
    ) -> None:
        """list/cancel live on nest-manager, which no Nest origin routes to."""
        ctx = self._live_ctx()
        with pytest.raises(AdapterCapabilityError):
            await live.list_operations(ctx)
        with pytest.raises(AdapterCapabilityError):
            await live.cancel_operation("operation", "op-1", ctx)
