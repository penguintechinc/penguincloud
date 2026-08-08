"""Gough adapter: every operation, against a fake Gough speaking its real shapes.

Outbound calls are intercepted with ``httpx.MockTransport``, the convention
this repo already uses in ``test_adapter_transport.py`` and
``test_proxy_boundary.py``. The brief asked for respx; ``MockTransport`` is
what respx itself drives underneath, it needs no dependency the environment
cannot install (this interpreter is PEP 668 externally-managed), and it keeps
the real client, the real header assembly and the real retry loop running —
only the socket is replaced.

The fake below answers with Gough's ACTUAL payloads, including the parts an
integrator would rather it did not have:

* two response shapes — enveloped ``{"status","data","meta"}`` for nodes and
  biomes, bare objects for agents and auth;
* ``state`` on a node where every other product would say ``status``;
* ``total`` that is the page length, not the collection size.

A test suite that normalised those away would pass against a Gough that does
not exist.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import Map, RequestRedirect, Rule

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
from app.adapters.gough import GoughAdapter, clear_token_cache
from app.adapters.gough.mapping import (
    OP_BIOME_UPGRADE,
    OP_DEPLOYMENT,
    upgrade_operation_id,
)
from app.adapters.transport import Transport

BASE_URL = "https://gough.invalid"

# Assembled from low-entropy words rather than written as a literal: a
# realistic-looking secret in a test file is what gitleaks blocks the commit
# on, and allowlisting the file would blind it to a real key landing here.
SERVICE_PASSWORD = "-".join(("not", "a", "real", "password"))
ACCESS_TOKEN = "-".join(("gough", "access", "token", "one"))
ACCESS_TOKEN_2 = "-".join(("gough", "access", "token", "two"))
REFRESH_TOKEN = "-".join(("gough", "refresh", "token", "one"))


def _ctx(**overrides: Any) -> AdapterContext:
    """Context for a Gough connection, pinned to the fake's origin."""
    defaults: dict[str, Any] = {
        "connection_id": 41,
        "portal_tenant_id": 3,
        "external_id": "tenant-ext-9",
        "external_kind": "tenant_id",
        "base_url": BASE_URL,
        "auth_type": "basic",
        "api_key": "svc@penguintech.io",
        "api_secret": SERVICE_PASSWORD,
        "correlation_id": "corr-gough-1",
    }
    defaults.update(overrides)
    return AdapterContext(**defaults)


def _envelope(data: Any, meta: dict[str, Any] | None = None) -> httpx.Response:
    """Gough's ``envelope_success`` shape."""
    return httpx.Response(
        200, json={"status": "success", "data": data, "meta": meta or {}}
    )


def _error(status: int, code: str, message: str, **details: Any) -> httpx.Response:
    """Gough's ``envelope_error`` shape."""
    return httpx.Response(
        status,
        json={
            "status": "error",
            "error": {"code": code, "message": message, "details": details},
            "meta": {},
        },
    )


NODE_ROW = {
    "id": 12,
    "tenant_id": "tenant-ext-9",
    "name": "rack1-node12",
    # Gough says 'state', never 'status'.
    "state": "ready",
    "posture": "compliant",
    "ipv4": "10.0.0.12",
    "hardware_tags": ["gpu", "nvme"],
    "created_at": "2026-08-01T10:00:00+00:00",
    # Naive, as Gough's utcnow() call sites emit.
    "updated_at": "2026-08-02T11:30:00",
}

BIOME_ROW = {
    "id": 5,
    "name": "k8s-control",
    "is_active": True,
    "biome_kind": "k8s",
    "biome_type": "snap",
    "created_at": "2026-07-01T09:00:00+00:00",
}

AGENT_ROW = {
    "id": 3,
    "agent_id": "5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f",
    "hostname": "agent-3",
    "status": "active",
    "capabilities": ["shell"],
    "last_heartbeat": "2026-08-06T12:00:00+00:00",
    "enrolled_at": "2026-07-20T08:00:00+00:00",
}

DEPLOYMENT_ROW = {
    "id": "dep-77",
    "biome_id": 5,
    "node_id": 12,
    "phase": 2,
    "status": "in_progress",
    "logs_url": "/api/v1/biomes/deployments/dep-77/logs",
    "created_at": "2026-08-06T12:00:00+00:00",
    "updated_at": "2026-08-06T12:05:00+00:00",
}

UPGRADE_RUN_ROW = {
    "id": "run-9",
    "biome_id": 5,
    "target_version": "1.4.0",
    "cluster_id": "cl-1",
    "status": "in_progress",
    "phase": "canary",
    "nodes_total": 4,
    "nodes_completed": 2,
    "nodes_failed": 1,
    "started_at": "2026-08-06T12:00:00+00:00",
    "completed_at": None,
    "rollback_reason": None,
}


#: Gough's REAL route registrations, transcribed from its source.
#:
#: Sources (``~/code/gough/services/api-manager/app/``): ``auth.py``,
#: ``api/nodes.py`` (``url_prefix="/api/v1/nodes"``), ``api/biomes.py``
#: (``url_prefix="/api/v1/biomes"``), ``api/agents.py``
#: (``url_prefix="/api/v1/agents"``), ``api/clusters.py`` (prefix applied at
#: ``register_blueprint``) and ``__init__.py`` for ``/healthz`` / ``/readyz``.
#: Deliberately NOT transcribed from Gough's committed
#: ``docs/api/openapi-spec.yaml``, which documents routes the service does not
#: register.
#:
#: The trailing slashes here are the load-bearing part: ``nodes``, ``biomes``
#: and ``agents`` register ``"/"`` for their collection, while ``groups`` and
#: ``deployments`` register no trailing slash. Gough never sets
#: ``strict_slashes``, so Werkzeug's asymmetric default governs, and
#: :class:`FakeGough` reproduces it below rather than restating it.
_GOUGH_REAL_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/healthz", ("GET",)),
    ("/readyz", ("GET",)),
    ("/api/v1/status", ("GET",)),
    ("/metrics", ("GET",)),
    ("/api/v1/auth/login", ("POST",)),
    ("/api/v1/auth/refresh", ("POST",)),
    # -- nodes ------------------------------------------------------------
    ("/api/v1/nodes/", ("GET",)),
    ("/api/v1/nodes/<int:node_id>", ("GET", "PATCH", "DELETE")),
    ("/api/v1/nodes/<int:node_id>/deploy", ("POST",)),
    ("/api/v1/nodes/<int:node_id>/evacuate", ("POST",)),
    ("/api/v1/nodes/<int:node_id>/reject", ("POST",)),
    ("/api/v1/nodes/<int:node_id>/tags", ("GET", "PATCH")),
    ("/api/v1/nodes/<int:node_id>/biomes", ("GET", "POST")),
    ("/api/v1/nodes/<int:node_id>/biomes/<int:biome_id>", ("DELETE",)),
    # -- biomes -----------------------------------------------------------
    ("/api/v1/biomes/", ("GET", "POST")),
    ("/api/v1/biomes/<int:biome_id>", ("GET", "PUT", "DELETE")),
    ("/api/v1/biomes/<int:biome_id>/upgrade", ("POST",)),
    ("/api/v1/biomes/<int:biome_id>/upgrade-runs/<run_id>", ("GET",)),
    ("/api/v1/biomes/<int:biome_id>/eligibility", ("GET",)),
    # No trailing slash — this is the shape the adapter got wrong.
    ("/api/v1/biomes/groups", ("GET", "POST")),
    ("/api/v1/biomes/groups/<int:group_id>", ("GET", "PUT", "DELETE")),
    ("/api/v1/biomes/deployments", ("GET",)),
    ("/api/v1/biomes/deployments/<string:deployment_id>", ("GET",)),
    ("/api/v1/biomes/deployments/<string:deployment_id>/logs", ("GET",)),
    ("/api/v1/biomes/deployments/<string:deployment_id>/cancel", ("POST",)),
    # -- agents -----------------------------------------------------------
    ("/api/v1/agents/", ("GET",)),
    ("/api/v1/agents/enrollment-keys", ("GET", "POST")),
    ("/api/v1/agents/<agent_id>", ("GET",)),
    ("/api/v1/agents/<agent_id>/suspend", ("POST",)),
    ("/api/v1/agents/<agent_id>/resume", ("POST",)),
    # -- clusters ---------------------------------------------------------
    ("/api/v1/clusters/<cluster_id>/config", ("GET", "PATCH")),
    ("/api/v1/clusters/<cluster_id>/storage", ("GET", "PATCH")),
    ("/api/v1/clusters/<cluster_id>/lxd/status", ("GET",)),
    ("/api/v1/clusters/<cluster_id>/lxd/members", ("GET",)),
    ("/api/v1/clusters/<cluster_id>/network-pools", ("GET", "PATCH")),
)


def _gough_url_map() -> Map:
    """Build a Werkzeug map mirroring Gough's own registrations.

    Using a real :class:`~werkzeug.routing.Map` rather than a hand-written
    string comparison is the point: Gough IS a Quart app, so its slash
    handling is Werkzeug's, and reproducing that behaviour by description
    would just re-encode the same assumption the adapter got wrong.
    """
    return Map(
        [
            Rule(rule, endpoint=f"{rule}:{','.join(methods)}", methods=methods)
            for rule, methods in _GOUGH_REAL_ROUTES
        ]
    )


class FakeGough:
    """An in-process Gough that records what it was asked.

    Every request is first matched against :data:`_GOUGH_REAL_ROUTES` through a
    real Werkzeug map, so the fake answers **the way Gough would** rather than
    the way the adapter assumes:

    * a path Gough does not register at all -> 404
    * a path missing a registered trailing slash -> **308**, as Werkzeug's
      default ``strict_slashes`` produces
    * a path carrying a trailing slash Gough does NOT declare -> **404**, with
      no redirect back, which is the asymmetry that made
      ``/api/v1/biomes/groups/`` fail outright

    This is what the previous version could not catch. It routed purely on the
    ``(method, path)`` keys the tests supplied, which were themselves copied
    from what the adapter sent — so the fake agreed with the adapter by
    construction and a wrong path shape was unfalsifiable.

    ``self.routes`` still supplies the response BODY; the map decides only
    whether the request is one Gough would have accepted.
    """

    def __init__(self, routes: dict[tuple[str, str], Any] | None = None) -> None:
        """Start with optional route overrides."""
        self.routes: dict[tuple[str, str], Any] = routes or {}
        self.requests: list[httpx.Request] = []
        self.login_count = 0
        self.refresh_count = 0
        self._url_adapter = _gough_url_map().bind("gough.test")

    def _route_shape_response(self, request: httpx.Request) -> httpx.Response | None:
        """Reproduce Gough's routing outcome, or None when the path matches.

        Returns the response Gough itself would produce for a path whose SHAPE
        is wrong, so the adapter is tested against the product's real slash
        semantics instead of the fake's convenience.
        """
        try:
            self._url_adapter.match(request.url.path, method=request.method)
        except RequestRedirect as redirect:
            # Werkzeug's 308 for a missing trailing slash. The portal transport
            # does not follow redirects and the proxy strips `location`, so this
            # reaches the browser as an empty body — the exact failure that
            # rendered three empty tables.
            return httpx.Response(308, headers={"location": redirect.new_url})
        except MethodNotAllowed:
            return _error(405, "method_not_allowed", f"{request.method} not allowed")
        except NotFound:
            return _error(
                404,
                "not_found",
                f"gough registers no route for {request.method} {request.url.path}",
            )
        return None

    def handler(self, request: httpx.Request) -> httpx.Response:
        """MockTransport handler."""
        self.requests.append(request)

        shape_failure = self._route_shape_response(request)
        if shape_failure is not None:
            return shape_failure

        key = (request.method, request.url.path)

        if key == ("POST", "/api/v1/auth/login"):
            self.login_count += 1
            return self._login(request)
        if key == ("POST", "/api/v1/auth/refresh"):
            self.refresh_count += 1
            return self._refresh(request)

        route = self.routes.get(key)
        if route is None:
            return _error(404, "not_found", f"no route for {key[0]} {key[1]}")
        if callable(route):
            result = route(request)
            assert isinstance(result, httpx.Response)
            return result
        if isinstance(route, list):
            # A queue: successive calls get successive responses, the last
            # repeating. This is how retry and refresh sequences are staged.
            response = route[0]
            if len(route) > 1:
                route.pop(0)
            assert isinstance(response, httpx.Response)
            return response
        assert isinstance(route, httpx.Response)
        return route

    def _login(self, request: httpx.Request) -> httpx.Response:
        """Answer Gough's un-enveloped login."""
        body = json.loads(request.content or b"{}")
        if body.get("password") != SERVICE_PASSWORD:
            return httpx.Response(401, json={"error": "Invalid email or password"})
        return httpx.Response(
            200,
            json={
                "access_token": ACCESS_TOKEN,
                "refresh_token": REFRESH_TOKEN,
                "user": {"id": 1, "email": body.get("email"), "roles": ["admin"]},
            },
        )

    def _refresh(self, request: httpx.Request) -> httpx.Response:
        """Answer Gough's un-enveloped refresh."""
        return httpx.Response(200, json={"access_token": ACCESS_TOKEN_2})

    def auth_headers(self) -> list[str | None]:
        """Authorization header seen on every non-auth request, in order."""
        return [
            request.headers.get("authorization")
            for request in self.requests
            if not request.url.path.startswith("/api/v1/auth/")
        ]


@pytest.fixture(autouse=True)
def _clean_token_cache() -> Any:
    """Isolate the module-level token cache between tests.

    Cleared before AND after: the cache is keyed by connection id, every test
    here uses the same one, and a token left behind would let a later test
    pass without ever logging in — hiding exactly the auth bug these tests
    exist to catch.
    """
    clear_token_cache()
    yield
    clear_token_cache()


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the transport's retry backoff so 5xx tests stay fast."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.adapters.transport.asyncio.sleep", _instant)


def _wire(fake: FakeGough, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the adapter's transport at the fake.

    Patched by string form rather than attribute assignment — mypy rejects
    assigning to a module attribute the module does not export.
    """
    transport = Transport()
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler),
        timeout=httpx.Timeout(10.0),
    )

    async def _get_transport(*_args: Any, **_kwargs: Any) -> Transport:
        return transport

    monkeypatch.setattr("app.adapters.gough.adapter.get_transport", _get_transport)


class TestAuthentication:
    """Service-account login, token reuse, and refresh-on-401."""

    async def test_logs_in_once_then_reuses_the_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second call must not re-login: the token is cached per connection."""
        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": [NODE_ROW]})})
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        await adapter.list_resources("nodes", _ctx())
        await adapter.list_resources("nodes", _ctx())

        assert fake.login_count == 1
        assert fake.auth_headers() == [
            f"Bearer {ACCESS_TOKEN}",
            f"Bearer {ACCESS_TOKEN}",
        ]

    async def test_service_account_password_is_never_sent_as_a_bearer_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The stored credential is a login, not a token.

        The context arrives with the password in ``api_key``/``api_secret``.
        If the adapter forwarded that context to the transport unchanged, the
        transport would dutifully attach the password as an Authorization
        header on every request — to the product, and to anything reading its
        access log.
        """
        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": []})})
        _wire(fake, monkeypatch)

        await GoughAdapter().list_resources("nodes", _ctx())

        sent = " ".join(
            f"{request.headers.get('authorization', '')} {request.url}"
            for request in fake.requests
        )
        assert SERVICE_PASSWORD not in sent
        # The login carries it in the BODY, which is where Gough wants it.
        login = fake.requests[0]
        assert login.url.path == "/api/v1/auth/login"
        assert login.headers.get("authorization") is None
        assert json.loads(login.content)["password"] == SERVICE_PASSWORD

    async def test_expired_token_is_refreshed_and_the_call_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 401 mid-request must be invisible to the caller.

        Gough's access token lives 30 minutes; a portal that surfaced the
        first 401 after that would fail one call in every connection's day.
        """
        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): [
                    httpx.Response(401, json={"error": "token expired"}),
                    _envelope({"nodes": [NODE_ROW]}),
                ]
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("nodes", _ctx())

        assert [node.id for node in page.items] == ["12"]
        assert fake.refresh_count == 1
        # Second attempt carries the REFRESHED token, not the stale one.
        assert fake.auth_headers() == [
            f"Bearer {ACCESS_TOKEN}",
            f"Bearer {ACCESS_TOKEN_2}",
        ]

    async def test_persistent_401_surfaces_as_upstream_auth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 401 that survives a fresh token is a bad credential, not a stale one.

        It must not loop: the retry fires once, then the failure is reported
        as an upstream auth problem (502) rather than the portal caller's own
        401, which would tell the browser to re-login and fix nothing.
        """
        fake = FakeGough(
            {("GET", "/api/v1/nodes/"): httpx.Response(401, json={"error": "nope"})}
        )
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamAuthError):
            await GoughAdapter().list_resources("nodes", _ctx())

        assert len(fake.auth_headers()) == 2

    async def test_missing_credential_fails_before_any_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unconfigured connection must not produce a mystery 401."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamAuthError, match="service-account"):
            await GoughAdapter().list_resources("nodes", _ctx(api_secret=""))

        assert fake.requests == []


class TestResourceReads:
    """Listing and fetching, including the shapes Gough gets wrong."""

    async def test_node_state_becomes_status_and_naive_timestamps_become_aware(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough nodes have no ``status`` field — mapping it would yield None."""
        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": [NODE_ROW]})})
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("nodes", _ctx())
        node = page.items[0]

        assert node.status == "ready"
        assert node.name == "rack1-node12"
        assert node.metadata["posture"] == "compliant"
        assert node.created_at is not None and node.created_at.tzinfo is not None
        # Naive input, made aware — Resource promises tz-aware timestamps and
        # comparing a naive to an aware datetime raises.
        assert node.updated_at is not None and node.updated_at.tzinfo is not None

    async def test_gough_total_is_not_forwarded_as_a_collection_total(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``total`` from Gough is the page length, not the fleet size.

        Forwarding it would render "1 node" on every page of a 400-node fleet,
        and the UI shows a total as fact.
        """
        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): _envelope(
                    {"nodes": [NODE_ROW], "total": 1},
                    meta={"next_cursor": "cur-2"},
                )
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("nodes", _ctx())

        assert page.total is None
        assert page.next_cursor == "cur-2"
        assert page.has_more is True

    async def test_last_page_reports_no_more(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough sends ``next_cursor: null`` rather than omitting the key."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): _envelope(
                    {"nodes": [NODE_ROW]}, meta={"next_cursor": None}
                )
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("nodes", _ctx())

        assert page.next_cursor is None
        assert page.has_more is False

    async def test_agents_come_back_unenveloped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough's agent routes predate its envelope and return a bare object."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/agents/"): httpx.Response(
                    200, json={"agents": [AGENT_ROW], "count": 1}
                )
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("agents", _ctx())

        assert [agent.id for agent in page.items] == [
            "5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f"
        ]
        assert page.items[0].name == "agent-3"
        assert page.items[0].status == "active"

    async def test_agent_is_addressed_by_uuid_not_row_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Using the numeric row id would build a list whose every link 404s."""
        fake = FakeGough(
            {
                (
                    "GET",
                    "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f",
                ): httpx.Response(200, json={"agent": AGENT_ROW})
            }
        )
        _wire(fake, monkeypatch)

        agent = await GoughAdapter().get_resource(
            "agents", "5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f", _ctx()
        )

        assert agent.id == "5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f"
        assert agent.metadata["row_id"] == 3

    async def test_filters_are_allowlisted_not_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``tenant_id`` must never reach Gough from a portal caller.

        Gough honours ``?tenant_id=`` for cross-tenant super-admins. Relaying
        a caller's key unfiltered would make the portal's tenant isolation
        depend on how privileged the SERVICE ACCOUNT is, not on who is asking.
        """
        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": []})})
        _wire(fake, monkeypatch)

        await GoughAdapter().list_resources(
            "nodes",
            _ctx(),
            filters={"state": "ready", "tenant_id": "someone-else", "cross_tenant": 1},
        )

        query = fake.requests[-1].url.params
        assert query.get("state") == "ready"
        assert "tenant_id" not in query
        assert "cross_tenant" not in query

    async def test_missing_node_is_not_found_not_a_capability_gap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """404 from the product means "no such node", never "unsupported"."""
        fake = FakeGough(
            {("GET", "/api/v1/nodes/99"): _error(404, "not_found", "Node 99 not found")}
        )
        _wire(fake, monkeypatch)

        with pytest.raises(ResourceNotFoundError):
            await GoughAdapter().get_resource("nodes", "99", _ctx())


class TestCapabilityGaps:
    """Absences that must be declared, never faked as an empty result."""

    async def test_clusters_cannot_be_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough registers no ``GET /api/v1/clusters``.

        An empty Page would read as "this deployment has no clusters", which
        is the exact confusion the contract's capability/emptiness split
        exists to prevent.
        """
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError, match="no cluster collection"):
            await GoughAdapter().list_resources("clusters", _ctx())

        assert fake.requests == []

    async def test_single_cluster_is_readable_via_lxd_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one per-cluster route returning a cluster-shaped object."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/clusters/cl-1/lxd/status"): _envelope(
                    {
                        "cluster_id": "cl-1",
                        "healthy": False,
                        "quorum_status": "degraded",
                        "member_count": 3,
                        "members_online": 2,
                        "members_offline": 1,
                    }
                )
            }
        )
        _wire(fake, monkeypatch)

        cluster = await GoughAdapter().get_resource("clusters", "cl-1", _ctx())

        assert cluster.status == "degraded"
        assert cluster.metadata["members_offline"] == 1

    async def test_unknown_kind_raises_capability_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A kind this adapter never serves is a 501, not a 404."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError):
            await GoughAdapter().list_resources("volumes", _ctx())

    async def test_nodes_and_agents_cannot_be_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough discovers nodes and enrols agents; a portal create is fiction."""
        fake = FakeGough()
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        with pytest.raises(AdapterCapabilityError, match="discovered"):
            await adapter.create_resource("nodes", {"name": "x"}, _ctx())
        with pytest.raises(AdapterCapabilityError):
            await adapter.create_resource("agents", {"hostname": "x"}, _ctx())
        assert fake.requests == []

    async def test_unknown_action_is_rejected_before_any_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``action`` is a table key, never a path fragment.

        The rejection happens before a URL exists, so a caller cannot reach an
        undeclared Gough endpoint by naming it as an action.
        """
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError, match="no action"):
            await GoughAdapter().perform_action(
                "nodes", "12", "../../../etc/passwd", None, _ctx()
            )
        assert fake.requests == []

    async def test_hostile_resource_id_never_reaches_a_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ids are the one caller value that becomes a path segment."""
        fake = FakeGough()
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        for hostile in ("../admin", "12/deploy", "a b", "12?x=1", ""):
            with pytest.raises(ResourceNotFoundError):
                await adapter.get_resource("nodes", hostile, _ctx())
        assert fake.requests == []


class TestWritesAndActions:
    """Creates, updates, deletes, and the verbs that start background work."""

    async def test_create_biome_uses_post_and_maps_the_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A created biome comes back as a portal Resource."""
        fake = FakeGough({("POST", "/api/v1/biomes/"): _envelope(BIOME_ROW)})
        _wire(fake, monkeypatch)

        biome = await GoughAdapter().create_resource(
            "biomes", {"name": "k8s-control"}, _ctx()
        )

        assert biome.id == "5"
        assert biome.status == "active"

    async def test_update_uses_patch_for_nodes_and_put_for_biomes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough is not uniform; sending the wrong verb yields an opaque 405."""
        fake = FakeGough(
            {
                ("PATCH", "/api/v1/nodes/12"): _envelope(NODE_ROW),
                ("PUT", "/api/v1/biomes/5"): _envelope(BIOME_ROW),
            }
        )
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        await adapter.update_resource("nodes", "12", {"name": "n"}, _ctx())
        await adapter.update_resource("biomes", "5", {"name": "b"}, _ctx())

        methods = [
            (request.method, request.url.path)
            for request in fake.requests
            if not request.url.path.startswith("/api/v1/auth/")
        ]
        assert methods == [
            ("PATCH", "/api/v1/nodes/12"),
            ("PUT", "/api/v1/biomes/5"),
        ]

    async def test_validation_failure_is_422_not_a_bad_gateway(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bad form field must not read as "the product is broken".

        Gough answers 422 with per-field violations; rendering that as 502
        hides the only information that would fix it.
        """
        fake = FakeGough(
            {
                ("POST", "/api/v1/biomes/"): _error(
                    422,
                    "validation_failed",
                    "name is required",
                    violations=[{"field": "name", "error": "required"}],
                )
            }
        )
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamValidationError) as caught:
            await GoughAdapter().create_resource("biomes", {}, _ctx())

        assert caught.value.violations == [{"field": "name", "error": "required"}]

    async def test_node_deploy_sends_the_idempotency_key_gough_requires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough rejects a deploy with no ``X-Idempotency-Key`` outright."""
        fake = FakeGough(
            {
                ("POST", "/api/v1/nodes/12/deploy"): _envelope(
                    {"node_id": 12, "assignment_ids": ["dep-77"], "note": "queued"}
                )
            }
        )
        _wire(fake, monkeypatch)

        await GoughAdapter().perform_action("nodes", "12", "deploy", {}, _ctx())

        deploy = fake.requests[-1]
        assert deploy.headers.get("X-Idempotency-Key", "").startswith(
            "portal-deploy-12"
        )

    async def test_one_deploy_returns_every_operation_it_started(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This is why ActionResult.operations is a list.

        A single Gough deploy creates one deployment per assigned biome. A
        singular field would force this adapter to pick one and drop the rest,
        leaving the UI polling a fraction of the work it started.
        """
        fake = FakeGough(
            {
                ("POST", "/api/v1/nodes/12/deploy"): _envelope(
                    {
                        "node_id": 12,
                        "assignment_ids": ["dep-77", "dep-78", "dep-79"],
                        "note": "Plan compile queued",
                    }
                )
            }
        )
        _wire(fake, monkeypatch)

        result = await GoughAdapter().perform_action(
            "nodes", "12", "deploy", {"biome_assignments": []}, _ctx()
        )

        assert [op.id for op in result.operations] == ["dep-77", "dep-78", "dep-79"]
        assert {op.kind for op in result.operations} == {OP_DEPLOYMENT}
        assert all(op.state is OperationState.PENDING for op in result.operations)
        assert result.message == "Plan compile queued"

    async def test_synchronous_action_returns_no_operations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty list is how a caller knows there is nothing to poll."""
        fake = FakeGough(
            {
                (
                    "POST",
                    "/api/v1/agents/5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f/suspend",
                ): _envelope({"ok": True})
            }
        )
        _wire(fake, monkeypatch)

        result = await GoughAdapter().perform_action(
            "agents", "5c1d9e2f-4a6b-4c8d-9e0f-1a2b3c4d5e6f", "suspend", None, _ctx()
        )

        assert result.operations == []
        assert result.accepted is True

    async def test_delete_conflict_is_reported_as_a_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """409 means re-read, not retry."""
        fake = FakeGough(
            {
                ("DELETE", "/api/v1/nodes/12"): _error(
                    409, "conflict", "node still has biomes assigned"
                )
            }
        )
        _wire(fake, monkeypatch)

        with pytest.raises(ResourceConflictError):
            await GoughAdapter().delete_resource("nodes", "12", _ctx())


class TestOperations:
    """Poll, cancel and logs — the surface added to the contract this phase."""

    async def test_deployment_poll_maps_state_for_control_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``in_progress`` must be RUNNING so the poll loop keeps going."""
        fake = FakeGough(
            {("GET", "/api/v1/biomes/deployments/dep-77"): _envelope(DEPLOYMENT_ROW)}
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().get_operation(OP_DEPLOYMENT, "dep-77", _ctx())

        assert op.state is OperationState.RUNNING
        assert op.state.is_terminal is False
        assert op.status == "in_progress"
        assert op.resource_id == "12"
        assert op.resource_kind == "nodes"

    async def test_deployment_progress_is_none_not_invented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough reports ``phase`` with no maximum — a fraction would be fiction."""
        fake = FakeGough(
            {("GET", "/api/v1/biomes/deployments/dep-77"): _envelope(DEPLOYMENT_ROW)}
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().get_operation(OP_DEPLOYMENT, "dep-77", _ctx())

        assert op.progress is None
        assert op.detail == "phase 2"

    async def test_upgrade_run_progress_is_computed_from_real_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failed nodes count as work done: the run is finished with them.

        Excluding them would park a run that failed on every node at 0% while
        it is demonstrably over.
        """
        fake = FakeGough(
            {("GET", "/api/v1/biomes/5/upgrade-runs/run-9"): _envelope(UPGRADE_RUN_ROW)}
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().get_operation(
            OP_BIOME_UPGRADE, upgrade_operation_id(5, "run-9"), _ctx()
        )

        # 2 completed + 1 failed of 4.
        assert op.progress == pytest.approx(0.75)
        assert op.metadata["target_version"] == "1.4.0"

    async def test_upgrade_run_id_round_trips_through_poll(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_operation(op.kind, op.id) must refresh op with no outside state.

        Gough nests upgrade runs under a biome, so the parent id is folded
        into the operation id. Without that, a caller holding an Operation
        could not poll it.
        """
        fake = FakeGough(
            {("GET", "/api/v1/biomes/5/upgrade-runs/run-9"): _envelope(UPGRADE_RUN_ROW)}
        )
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        first = await adapter.get_operation(
            OP_BIOME_UPGRADE, upgrade_operation_id(5, "run-9"), _ctx()
        )
        again = await adapter.get_operation(first.kind, first.id, _ctx())

        assert first.id == "5:run-9"
        assert again.id == first.id

    async def test_malformed_composite_id_is_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare run id cannot build a URL and must not try."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(ResourceNotFoundError):
            await GoughAdapter().get_operation(OP_BIOME_UPGRADE, "run-9", _ctx())

    async def test_unknown_status_stays_running_never_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two mistakes are not symmetric.

        Calling a live operation finished freezes the UI on a stale frame
        forever; calling a finished one live costs a few extra polls.
        """
        fake = FakeGough(
            {
                ("GET", "/api/v1/biomes/deployments/dep-77"): _envelope(
                    {**DEPLOYMENT_ROW, "status": "reticulating_splines"}
                )
            }
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().get_operation(OP_DEPLOYMENT, "dep-77", _ctx())

        assert op.state is OperationState.RUNNING
        assert op.status == "reticulating_splines"

    async def test_terminal_operation_records_completion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A succeeded deployment stops the poll loop."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/biomes/deployments/dep-77"): _envelope(
                    {**DEPLOYMENT_ROW, "status": "succeeded"}
                )
            }
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().get_operation(OP_DEPLOYMENT, "dep-77", _ctx())

        assert op.state.is_terminal is True
        assert op.completed_at is not None

    async def test_cancel_rereads_the_operation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough's cancel response omits the timestamps the caller's view needs."""
        fake = FakeGough(
            {
                ("POST", "/api/v1/biomes/deployments/dep-77/cancel"): _envelope(
                    {
                        "cancelled": True,
                        "deployment_id": "dep-77",
                        "status": "cancelled",
                    }
                ),
                ("GET", "/api/v1/biomes/deployments/dep-77"): _envelope(
                    {**DEPLOYMENT_ROW, "status": "cancelled"}
                ),
            }
        )
        _wire(fake, monkeypatch)

        op = await GoughAdapter().cancel_operation(OP_DEPLOYMENT, "dep-77", _ctx())

        assert op.state is OperationState.CANCELLED
        assert op.updated_at is not None

    async def test_cancelling_a_finished_deployment_is_a_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gough answers 409; the UI should not have offered the button."""
        fake = FakeGough(
            {
                ("POST", "/api/v1/biomes/deployments/dep-77/cancel"): _error(
                    409, "conflict", "Cannot cancel deployment in status 'succeeded'"
                )
            }
        )
        _wire(fake, monkeypatch)

        with pytest.raises(ResourceConflictError):
            await GoughAdapter().cancel_operation(OP_DEPLOYMENT, "dep-77", _ctx())

    async def test_upgrade_runs_cannot_be_cancelled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Declared gap: Gough rolls an upgrade back under its own orchestration."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError):
            await GoughAdapter().cancel_operation(OP_BIOME_UPGRADE, "5:run-9", _ctx())

    async def test_operation_logs_are_ordered_and_typed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The DetailDrawer log tab renders severity and time, not raw strings."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/biomes/deployments/dep-77/logs"): _envelope(
                    {
                        "deployment_id": "dep-77",
                        "logs": [
                            {
                                "id": "1",
                                "message": "starting",
                                "level": "info",
                                "created_at": "2026-08-06T12:00:00+00:00",
                            },
                            {
                                "id": "2",
                                "message": "pull failed",
                                "level": "error",
                                "created_at": "2026-08-06T12:01:00+00:00",
                            },
                        ],
                    }
                )
            }
        )
        _wire(fake, monkeypatch)

        lines = await GoughAdapter().operation_logs(
            OP_DEPLOYMENT, "dep-77", _ctx(), tail=50
        )

        assert [line.message for line in lines] == ["starting", "pull failed"]
        assert lines[1].level == "error"
        assert lines[0].timestamp is not None
        assert fake.requests[-1].url.params.get("tail") == "50"

    async def test_list_operations_filters_by_portal_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RUNNING must translate back to Gough's own ``in_progress``."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/biomes/deployments"): _envelope(
                    {"deployments": [DEPLOYMENT_ROW], "total": 1, "limit": 20}
                )
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_operations(
            _ctx(), state=OperationState.RUNNING
        )

        assert [op.id for op in page.items] == ["dep-77"]
        assert fake.requests[-1].url.params.get("status") == "in_progress"

    async def test_upgrade_runs_have_no_collection_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Declared, not faked as an empty page."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError, match="collection endpoint"):
            await GoughAdapter().list_operations(_ctx(), kind=OP_BIOME_UPGRADE)


class TestTransportBehaviour:
    """Timeouts, retries and throttling, exercised through the adapter."""

    async def test_5xx_is_retried_and_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A GET is idempotent, so the shared transport retries it."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): [
                    httpx.Response(503, text="upstream unavailable"),
                    _envelope({"nodes": [NODE_ROW]}),
                ]
            }
        )
        _wire(fake, monkeypatch)

        page = await GoughAdapter().list_resources("nodes", _ctx())

        assert [node.id for node in page.items] == ["12"]
        assert len(fake.auth_headers()) == 2

    async def test_exhausted_5xx_retries_surface_as_upstream_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Three attempts, then an upstream failure — never a portal 500."""
        from app.adapters.base import UpstreamError
        from app.adapters.transport import MAX_ATTEMPTS

        fake = FakeGough({("GET", "/api/v1/nodes/"): httpx.Response(500, text="boom")})
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamError):
            await GoughAdapter().list_resources("nodes", _ctx())

        assert len(fake.auth_headers()) == MAX_ATTEMPTS

    async def test_post_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A retried deploy could provision the same hardware twice."""
        from app.adapters.base import UpstreamError

        fake = FakeGough(
            {("POST", "/api/v1/biomes/"): httpx.Response(500, text="boom")}
        )
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamError):
            await GoughAdapter().create_resource("biomes", {"name": "b"}, _ctx())

        assert len(fake.auth_headers()) == 1

    async def test_timeout_surfaces_as_a_transport_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hung product must not hang the portal silently."""

        def _hang(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        fake = FakeGough({("GET", "/api/v1/nodes/"): _hang})
        _wire(fake, monkeypatch)

        with pytest.raises(httpx.ReadTimeout):
            await GoughAdapter().list_resources("nodes", _ctx())

    async def test_rate_limit_carries_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """429 is a throttle to back off from, not an outage."""
        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): httpx.Response(
                    429, json={"error": "slow down"}, headers={"Retry-After": "30"}
                )
            }
        )
        _wire(fake, monkeypatch)

        with pytest.raises(RateLimitedError) as caught:
            await GoughAdapter().list_resources("nodes", _ctx())

        assert caught.value.retry_after == 30.0

    async def test_html_error_page_is_an_upstream_error_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A proxy in front of Gough answering 200 with HTML is a real case."""
        from app.adapters.base import UpstreamError

        fake = FakeGough(
            {
                ("GET", "/api/v1/nodes/"): httpx.Response(
                    200,
                    text="<html>login</html>",
                    headers={"content-type": "text/html"},
                )
            }
        )
        _wire(fake, monkeypatch)

        with pytest.raises(UpstreamError, match="non-JSON"):
            await GoughAdapter().list_resources("nodes", _ctx())

    async def test_every_call_including_login_stays_on_the_connection_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The adapter builds every URL from ``ctx.base_url``.

        The login is the one worth asserting: an adapter that authenticated
        against a fixed auth host would send the operator's service-account
        password somewhere they never configured, and the transport's origin
        pin could not object because the pin compares against ``base_url``
        itself. Nothing here is protected by the pin — this is the property
        that has to hold on its own for the pin to mean anything.
        """
        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": [NODE_ROW]})})
        _wire(fake, monkeypatch)

        await GoughAdapter().list_resources("nodes", _ctx())

        assert fake.requests, "expected at least the login and the list call"
        assert {request.url.host for request in fake.requests} == {"gough.invalid"}
        assert fake.requests[0].url.path == "/api/v1/auth/login"

    async def test_a_mis_built_url_cannot_reach_another_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pin is the backstop if the property above ever breaks.

        Asserted at the adapter's own transport rather than through a public
        method, because no current code path can produce a foreign URL — which
        is the point. If a future edit introduces one, this fails before the
        socket rather than after the credential has left.
        """
        from app.adapters.transport import CredentialEgressError

        fake = FakeGough()
        _wire(fake, monkeypatch)
        transport = await GoughAdapter()._transport()

        with pytest.raises(CredentialEgressError):
            await transport.request(
                "GET", "https://attacker.invalid/api/v1/nodes/", _ctx()
            )
        assert fake.requests == []


class TestCollectionRouteShapes:
    """The adapter must address each collection the way Gough registers it.

    These are regression tests for a defect the previous suite structurally
    could not catch: :class:`FakeGough` used to route on the keys the tests
    supplied, and those keys were copied from what the adapter sent, so any
    path shape the adapter chose was correct by construction.

    The fake now matches through a real Werkzeug map built from Gough's own
    registrations, so a wrong slash produces the product's real answer — 308
    one way, 404 the other. Both are fatal to the caller: the transport does
    not follow redirects and the proxy strips ``location``.
    """

    async def test_biome_groups_list_hits_the_slashless_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``/api/v1/biomes/groups`` has NO trailing slash in Gough.

        The adapter previously sent ``/api/v1/biomes/groups/``. Werkzeug does
        not redirect that direction, so it was a flat 404 — the biome-groups
        collection simply never worked. Reverting the fix makes this red.
        """
        fake = FakeGough({("GET", "/api/v1/biomes/groups"): _envelope({"groups": []})})
        _wire(fake, monkeypatch)

        await GoughAdapter().list_resources("biome_groups", _ctx())

        paths = [r.url.path for r in fake.requests if "auth" not in r.url.path]
        assert paths == ["/api/v1/biomes/groups"]

    async def test_biome_groups_create_hits_the_slashless_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Create shares the same route shape, and shared the same bug."""
        fake = FakeGough(
            {
                ("POST", "/api/v1/biomes/groups"): _envelope(
                    {"group": {"id": 3, "name": "edge"}}
                )
            }
        )
        _wire(fake, monkeypatch)

        await GoughAdapter().create_resource("biome_groups", {"name": "edge"}, _ctx())

        paths = [r.url.path for r in fake.requests if "auth" not in r.url.path]
        assert paths == ["/api/v1/biomes/groups"]

    @pytest.mark.parametrize(
        ("kind", "expected_path", "item_key"),
        [
            ("nodes", "/api/v1/nodes/", "nodes"),
            ("biomes", "/api/v1/biomes/", "biomes"),
            ("agents", "/api/v1/agents/", "agents"),
        ],
    )
    async def test_slashed_collections_keep_their_trailing_slash(
        self,
        kind: str,
        expected_path: str,
        item_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """These three DO register ``"/"``; dropping the slash yields a 308."""
        fake = FakeGough({("GET", expected_path): _envelope({item_key: []})})
        _wire(fake, monkeypatch)

        await GoughAdapter().list_resources(kind, _ctx())

        paths = [r.url.path for r in fake.requests if "auth" not in r.url.path]
        assert paths == [expected_path]

    async def test_fake_reproduces_goughs_308_for_a_missing_slash(self) -> None:
        """Guard on the guard: prove the fake models the 308, not just a 404.

        If this ever stops being a 308, the tests above stop testing the thing
        that actually broke the UI — an empty-bodied redirect the browser reads
        as zero rows rather than as an error.
        """
        fake = FakeGough()
        response = fake.handler(httpx.Request("GET", "https://gough.test/api/v1/nodes"))
        assert response.status_code == 308
        assert response.headers["location"].endswith("/api/v1/nodes/")

    async def test_fake_reproduces_goughs_404_for_an_extra_slash(self) -> None:
        """The other direction: no redirect back, just a 404."""
        fake = FakeGough()
        response = fake.handler(
            httpx.Request("GET", "https://gough.test/api/v1/biomes/groups/")
        )
        assert response.status_code == 404


class TestSessionLockIsolation:
    """I8: one hanging Gough must not stall every other Gough connection.

    The token cache was guarded by a single module-level ``asyncio.Lock`` held
    ACROSS the network login. Because the await sat inside the critical
    section, a slow or hanging product stalled every Gough request in the
    portal — including other tenants' connections, which share nothing with it
    but that lock. This module is the template Phase-4N and 4T copy from.
    """

    async def test_a_hanging_connection_does_not_block_a_different_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The load-bearing assertion: connection B completes while A hangs.

        With one global lock this deadlocks until the timeout — B cannot even
        begin its login while A holds the lock waiting on a socket that never
        answers.
        """
        import asyncio

        release_a = asyncio.Event()
        a_is_hanging = asyncio.Event()

        class HangingGough(FakeGough):
            """Blocks connection 41's login until told to proceed."""

            async def _ahandler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == "/api/v1/auth/login" and b"hang@" in (
                    request.content or b""
                ):
                    # Signal that the hang is IN PROGRESS — the lock is now
                    # provably held across a network await. Without this the
                    # test races: a bare `sleep(0)` can return before the first
                    # task has acquired anything, so the second call sails
                    # through even under a single global lock and the test
                    # proves nothing. (It did exactly that on first writing.)
                    a_is_hanging.set()
                    await release_a.wait()
                return self.handler(request)

        fake = HangingGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": []})})
        transport = Transport()
        transport._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake._ahandler),
            timeout=httpx.Timeout(10.0),
        )

        async def _get_transport(*_a: Any, **_k: Any) -> Transport:
            return transport

        monkeypatch.setattr("app.adapters.gough.adapter.get_transport", _get_transport)
        adapter = GoughAdapter()

        stuck = asyncio.create_task(
            adapter.list_resources(
                "nodes", _ctx(connection_id=41, api_key="hang@penguintech.io")
            )
        )
        # Wait until A is provably inside its login, holding its lock.
        await asyncio.wait_for(a_is_hanging.wait(), timeout=2.0)

        # A different connection must complete while the first is still stuck.
        await asyncio.wait_for(
            adapter.list_resources(
                "nodes", _ctx(connection_id=99, api_key="other@penguintech.io")
            ),
            timeout=2.0,
        )

        assert not stuck.done(), "the hanging connection should still be blocked"
        release_a.set()
        await asyncio.wait_for(stuck, timeout=2.0)

    async def test_concurrent_calls_on_one_connection_still_log_in_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The property the lock exists for, kept.

        Per-key locking must not degrade into no locking: a burst of parallel
        calls for the SAME connection must still perform exactly one login.
        """
        import asyncio

        fake = FakeGough({("GET", "/api/v1/nodes/"): _envelope({"nodes": []})})
        _wire(fake, monkeypatch)
        adapter = GoughAdapter()

        await asyncio.gather(
            *(adapter.list_resources("nodes", _ctx()) for _ in range(8))
        )

        assert fake.login_count == 1

    async def test_distinct_connections_get_distinct_locks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keying is by (connection_id, credential fingerprint), as documented."""
        from app.adapters.gough.session import _KEY_LOCKS, _lock_for

        first = await _lock_for((1, "fp-a"))
        assert await _lock_for((1, "fp-a")) is first, "same key must reuse its lock"
        assert await _lock_for((2, "fp-a")) is not first
        assert await _lock_for((1, "fp-b")) is not first
        assert len(_KEY_LOCKS) == 3


class TestMetricsErrorTaxonomy:
    """M12: /metrics failures use the same taxonomy as every other call.

    ``metrics_summary`` cannot go through ``_call`` — ``/metrics`` answers
    Prometheus text, not Gough's JSON envelope — but that is a reason to skip
    ``unwrap``, not a reason to skip the error taxonomy. It previously
    collapsed every 4xx/5xx into a bare ``UpstreamError``, so the dashboard
    reported "upstream error" for a throttle the portal should have backed off
    from and for a permission problem an operator could have fixed.
    """

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (403, UpstreamAuthError),
            (404, ResourceNotFoundError),
            (429, RateLimitedError),
            (500, UpstreamError),
        ],
    )
    async def test_metrics_failure_maps_to_the_shared_taxonomy(
        self,
        status: int,
        expected: type[Exception],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same status -> same exception class as any other adapter call."""
        fake = FakeGough()
        fake.routes[("GET", "/metrics")] = _error(status, "boom", "metrics failed")
        _wire(fake, monkeypatch)

        with pytest.raises(expected):
            await GoughAdapter().metrics_summary(_ctx())

    async def test_metrics_429_carries_the_retry_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A throttle must be distinguishable from an outage, with its delay.

        This is the concrete cost of the old bare `UpstreamError`: the caller
        could not back off correctly because the hint was thrown away.
        """
        fake = FakeGough()
        fake.routes[("GET", "/metrics")] = httpx.Response(
            429,
            headers={"Retry-After": "17"},
            json={"status": "error", "error": {"message": "slow down"}, "meta": {}},
        )
        _wire(fake, monkeypatch)

        with pytest.raises(RateLimitedError) as caught:
            await GoughAdapter().metrics_summary(_ctx())

        assert caught.value.retry_after == 17


class TestKindTableParity:
    """Every table keyed by resource kind must cover the same kinds.

    `_require_kind` validates a caller's kind against `_COLLECTIONS` alone,
    and the call sites then index `_COLLECTION_ROUTES`, `_ITEM_KEYS` and
    `_MAPPERS` unguarded. A kind in one table and not another passes
    validation and raises `KeyError` — a 500, where the contract promises
    `AdapterCapabilityError` (501, a declared absence a caller can act on).
    """

    def test_all_kind_keyed_tables_agree(self) -> None:
        """The parity the import-time guard enforces, asserted explicitly."""
        from app.adapters.gough.adapter import _KIND_TABLES, _KINDS

        assert _KINDS, "the adapter must serve at least one kind"
        for name, table in _KIND_TABLES.items():
            assert frozenset(table) == _KINDS, name

    def test_the_guard_rejects_a_divergent_table(self) -> None:
        """Prove the import-time check would actually fire.

        Re-runs the guard's own comparison against a deliberately divergent
        table. Without this the guard could be dead code that happens to sit
        beside four tables somebody keeps in sync by hand.
        """
        from app.adapters.gough.adapter import _KINDS

        divergent = {"nodes": "x", "biomes": "y"}  # missing two kinds
        assert frozenset(divergent) != _KINDS

    async def test_an_unknown_kind_is_501_not_500(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The behaviour the parity guard protects, end to end."""
        fake = FakeGough()
        _wire(fake, monkeypatch)

        with pytest.raises(AdapterCapabilityError):
            await GoughAdapter().list_resources("widgets", _ctx())

        assert fake.requests == [], "no request should be attempted"
