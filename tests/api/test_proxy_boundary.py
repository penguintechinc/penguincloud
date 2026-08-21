"""Proxy boundary correctness: kill-switch, audit-on-denial, header allow-list.

Companion to ``test_proxy_allowlist.py``, which covers *which* requests are
forwarded. This file covers three properties that a proxy can get wrong while
still routing correctly:

1. **The kill-switch works.** ``is_active`` is offered to admins in the
   products UI. If deactivating a connection does not stop traffic, the UI
   promises a control that does not exist — and a compromised or misbehaving
   integration keeps running after an operator believes they stopped it.
2. **Refusals are recorded.** On a deny-by-default boundary, denials are the
   signal. A trail containing only successes shows an attacker's failed
   probing as silence.
3. **Only named headers cross.** The forwarding filter is an allow-list, so
   the next auth-bearing header name nobody has thought of yet does not reach
   a third-party product by default.
"""

import json
import uuid
from typing import Any

import httpx
import pytest
from quart import Quart

PRODUCT_SECRET = "-".join(("not", "a", "real", "boundary", "credential"))


async def _register(client: Any) -> tuple[int, str]:
    """Register a user; return (id, email)."""
    email = f"bnd-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Bnd User"},
    )
    assert response.status_code in (200, 201), await response.get_json()
    return int((await response.get_json())["user"]["id"]), email


async def _headers(client: Any, email: str) -> dict[str, str]:
    """Log in and build Authorization headers."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert response.status_code == 200, await response.get_json()
    return {"Authorization": f"Bearer {(await response.get_json())['access_token']}"}


async def _create_tenant(client: Any, headers: dict[str, str], name: str) -> int:
    """Create a tenant owned by the caller."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": name,
            "slug": f"{name.lower()}-{uuid.uuid4().hex[:6]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _create_connection(app: Quart, tenant_id: int, *, product_type: str = "gough") -> int:
    """Create an active product connection plus its tenant mapping."""
    async with app.app_context():
        from app.models import create_product_connection, set_product_tenant_map

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type=product_type,
            display_name="Boundary Product",
            base_url="https://product.invalid",
            auth_type="bearer",
            api_key=PRODUCT_SECRET,
            api_secret="",
        )
        assert conn_id is not None
        await set_product_tenant_map(conn_id, tenant_id, "tenant_id", "ext-boundary")
        return int(conn_id)


async def _set_active(app: Quart, conn_id: int, active: bool) -> None:
    """Flip a connection's is_active flag at the schema level."""
    async with app.app_context():
        from app.models import get_db

        db = get_db()
        await db(db.product_connections.id == conn_id).update(is_active=active)
        await db.commit()


async def _audit_rows(app: Quart, connection_id: int) -> list[dict[str, Any]]:
    """Every audit row filed against a product connection, newest last."""
    async with app.app_context():
        from app.models import get_db

        db = get_db()
        rows = await db(
            (db.audit_logs.resource_type == "product_connection")
            & (db.audit_logs.resource_id == str(connection_id))
        ).select()
        return [dict(row) for row in rows]


def _outcomes(rows: list[dict[str, Any]]) -> list[str]:
    """Pull the recorded outcome out of each audit row's metadata blob."""
    outcomes = []
    for row in rows:
        raw = row.get("metadata")
        if not raw:
            continue
        outcomes.append(str(json.loads(raw).get("outcome", "")))
    return outcomes


class _Upstream:
    """Records what the product actually received, and replies as told."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body = b'{"ok": true}'
        self.headers: dict[str, str] = {"content-type": "application/json"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        """MockTransport handler."""
        self.requests.append(request)
        return httpx.Response(self.status, content=self.body, headers=self.headers)

    @property
    def last(self) -> httpx.Request:
        """The most recent request the product saw."""
        assert self.requests, "product was never called"
        return self.requests[-1]


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> _Upstream:
    """Route the shared adapter transport at an in-process fake product."""
    import app.adapters.transport as transport_module

    fake = _Upstream()

    # Named `request_timeout`, not `timeout` — ASYNC109 flags any async def
    # with a `timeout` parameter (it assumes the function implements its own
    # cancellation), which is a false positive here: this is a monkeypatch
    # replacement for get_transport() that only threads the value through to
    # Transport()/httpx.Timeout(), never awaits on it directly. Pre-existing,
    # fixed here only because this file's ruff hook now runs on every commit
    # touching it, this one included.
    async def _get_transport(request_timeout: float = 10.0) -> Any:
        instance = transport_module.Transport(timeout=request_timeout)
        instance._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake.handler),
            timeout=httpx.Timeout(request_timeout),
        )
        return instance

    monkeypatch.setattr(transport_module, "get_transport", _get_transport)
    monkeypatch.setattr("app.proxy.get_transport", _get_transport)
    return fake


def _proxy_url(connection_id: int, path: str) -> str:
    """Build the proxy URL for a connection and downstream path."""
    return f"/api/v1/products/{connection_id}/proxy{path}"


@pytest.mark.usefixtures("app_context")
class TestKillSwitch:
    """Deactivating a connection stops traffic, not just the UI badge."""

    @pytest.mark.asyncio
    async def test_deactivated_connection_is_refused_and_never_dispatched(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """403, and the product is never called.

        The status code alone would not prove the kill-switch works: a proxy
        that forwards and then reports 403 has already made the call it was
        told not to make.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "KillSwitch")
        conn_id = await _create_connection(app, tenant_id)

        # Premise: it works while active.
        ok = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        assert ok.status_code == 200, await ok.get_data()
        assert len(upstream.requests) == 1

        await _set_active(app, conn_id, False)

        denied = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert denied.status_code == 403
        assert "inactive" in (await denied.get_json())["error"].lower()
        assert len(upstream.requests) == 1, "deactivated connection still dispatched"

    @pytest.mark.asyncio
    async def test_reactivating_restores_traffic(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The kill-switch is reversible — enforcement is not a tombstone.

        Enforcing in the accessor instead of the proxy would hide the row
        from the management endpoints too, so the connection an operator
        deactivated could not be found to re-activate.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "KillSwitchBack")
        conn_id = await _create_connection(app, tenant_id)

        await _set_active(app, conn_id, False)
        assert (
            await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        ).status_code == 403

        # Still visible to its own management endpoint while deactivated.
        detail = await client.get(f"/api/v1/products/{conn_id}", headers=headers)
        assert detail.status_code == 200

        await _set_active(app, conn_id, True)
        restored = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        assert restored.status_code == 200


@pytest.mark.usefixtures("app_context")
class TestAuditOnEveryPath:
    """Success and every class of refusal reach the audit trail."""

    @pytest.mark.asyncio
    async def test_successful_call_is_audited_with_rule_and_scope(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A forwarded call records the rule it matched and the scope it needed."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditOk")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        assert response.status_code == 200

        rows = await _audit_rows(app, conn_id)
        assert _outcomes(rows) == ["allowed"]
        entry = json.loads(rows[0]["metadata"])
        assert rows[0]["action_type"] == "proxy.get"
        assert rows[0]["tenant_id"] == tenant_id
        # The per-product form, not the coarse one: the audit trail records
        # the scope the RULE demanded, so an auditor can tell a Gough-scoped
        # grant from a blanket products:read without re-reading the code.
        assert entry["scope_required"] == "products:gough:read"
        assert entry["route_matched"].startswith("GET ")
        assert entry["status_code"] == 200

    @pytest.mark.asyncio
    async def test_route_not_allowed_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Somebody mapping the allowlist leaves a trail."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditRoute")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/admin/users"), headers=headers)

        assert response.status_code == 404
        rows = await _audit_rows(app, conn_id)
        assert _outcomes(rows) == ["route_not_allowed"]
        assert rows[0]["action_type"] == "proxy.get.denied"
        assert json.loads(rows[0]["metadata"])["path"] == "/admin/users"

    @pytest.mark.asyncio
    async def test_unauthorized_tenant_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """An outsider's attempt is filed against the tenant they targeted."""
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "AuditOutsider")
        conn_id = await _create_connection(app, tenant_id)

        _, outsider_email = await _register(client)
        outsider_headers = await _headers(client, outsider_email)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=outsider_headers)

        assert response.status_code == 403
        rows = await _audit_rows(app, conn_id)
        assert _outcomes(rows) == ["unauthorized_tenant"]
        # Filed under the owning tenant: that is the tenant whose admins
        # need to see that someone tried.
        assert rows[0]["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_inactive_connection_denial_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """An operator can see the kill-switch being tested."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditInactive")
        conn_id = await _create_connection(app, tenant_id)
        await _set_active(app, conn_id, False)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 403
        assert _outcomes(await _audit_rows(app, conn_id)) == ["connection_inactive"]

    @pytest.mark.asyncio
    async def test_traversal_denial_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A traversal attempt is the loudest signal there is."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditTraversal")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz/../admin"), headers=headers)

        assert response.status_code == 400
        assert _outcomes(await _audit_rows(app, conn_id)) == ["malformed_path"]

    @pytest.mark.asyncio
    async def test_undersized_credential_denial_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A connection that cannot be proxied safely is recorded as such."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditShort")

        async with app.app_context():
            from app.models import create_product_connection, set_product_tenant_map

            conn_id_raw = await create_product_connection(
                tenant_id=tenant_id,
                product_type="gough",
                display_name="Short Cred",
                base_url="https://product.invalid",
                auth_type="bearer",
                api_key="ab",
                api_secret="",
            )
            assert conn_id_raw is not None
            conn_id = int(conn_id_raw)
            await set_product_tenant_map(conn_id, tenant_id, "tenant_id", "ext-short")

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 502
        assert _outcomes(await _audit_rows(app, conn_id)) == ["credential_too_short_to_redact"]

    @pytest.mark.asyncio
    async def test_oversize_request_denial_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A rejected upload is recorded, not silently dropped."""
        import app.proxy as proxy_module

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditBig")
        conn_id = await _create_connection(app, tenant_id)

        original = proxy_module.MAX_REQUEST_SIZE
        proxy_module.MAX_REQUEST_SIZE = 16
        try:
            response = await client.get(
                _proxy_url(conn_id, "/healthz"), headers=headers, data=b"x" * 512
            )
        finally:
            proxy_module.MAX_REQUEST_SIZE = original

        assert response.status_code == 413
        assert _outcomes(await _audit_rows(app, conn_id)) == ["request_too_large"]

    @pytest.mark.asyncio
    async def test_oversize_response_denial_is_audited(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A product flooding the portal is recorded against its connection."""
        import app.adapters.transport as transport_module

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "AuditBigResp")
        conn_id = await _create_connection(app, tenant_id)

        upstream.body = b"y" * 4096
        original = transport_module.MAX_RESPONSE_SIZE
        transport_module.MAX_RESPONSE_SIZE = 128
        try:
            response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        finally:
            transport_module.MAX_RESPONSE_SIZE = original

        assert response.status_code == 502
        assert _outcomes(await _audit_rows(app, conn_id)) == ["response_too_large"]

    @pytest.mark.asyncio
    async def test_insufficient_scope_is_denied_and_audited(
        self, client: Any, app: Quart, upstream: _Upstream, monkeypatch: Any
    ) -> None:
        """Authority present, scope absent — the RBACEnforcer branch itself.

        Every other refusal in the matrix is caught earlier: an outsider has
        no effective role at all and never reaches the scope check, so the
        enforcer's own failure path had no test. Here the caller IS a member
        (so ``resolve_effective_role`` succeeds) but holds the ``member``
        bundle, which grants ``products:read`` and not ``products:manage``.
        """
        from app.adapters import ADAPTER_REGISTRY
        from app.adapters.base import RouteRule

        monkeypatch.setattr(
            ADAPTER_REGISTRY["gough"],
            "route_allowlist",
            [RouteRule("GET", r"^/healthz\Z", "products:manage")],
        )

        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "AuditScope")
        conn_id = await _create_connection(app, tenant_id)

        member_id, member_email = await _register(client)
        add = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=owner_headers,
            json={"user_id": member_id, "role": "member"},
        )
        assert add.status_code == 201, await add.get_json()
        member_headers = await _headers(client, member_email)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=member_headers)

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "Insufficient permissions"
        assert upstream.requests == [], "scope-denied request still dispatched"

        rows = await _audit_rows(app, conn_id)
        assert _outcomes(rows) == ["insufficient_scope"]
        entry = json.loads(rows[0]["metadata"])
        assert entry["scope_required"] == "products:manage"
        # The granted set is deliberately NOT recorded: an audit row an
        # ordinary member can read back would otherwise enumerate authority.
        assert "scopes_granted" not in entry


@pytest.mark.usefixtures("app_context")
class TestPathTraversal:
    """A declared route cannot be reached sideways."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/healthz/../admin",
            "/./healthz",
            "/healthz/..",
            "/%2e%2e/admin",
            "/healthz//../admin",
        ],
    )
    async def test_traversal_variants_are_refused_before_dispatch(
        self, client: Any, app: Quart, upstream: _Upstream, path: str
    ) -> None:
        """Dot-segments and their encodings are refused, not resolved.

        Refused rather than normalised: if the portal resolved the path, the
        allowlist would judge one string and the product would receive
        another, and any disagreement between the two normalisers is a bypass.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "Traverse")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, path), headers=headers)

        assert response.status_code in (400, 404), path
        assert upstream.requests == [], f"{path} reached the product"


@pytest.mark.usefixtures("app_context")
class TestRequestHeaderAllowList:
    """Only named headers cross to the product."""

    @pytest.mark.asyncio
    async def test_unlisted_auth_headers_do_not_reach_the_product(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Every credential-ish header a deny-list would have had to name.

        This is the case the previous deny-list got wrong: it stripped seven
        header names and forwarded everything else, so any product honouring
        ``X-Auth-Token`` or ``Api-Key`` could be authenticated as whoever the
        caller claimed to be — and ``X-Forwarded-For`` / ``X-Original-URL``
        let a caller lie to the product's own access checks.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "HdrAllow")
        conn_id = await _create_connection(app, tenant_id)

        smuggled = {
            "X-Auth-Token": "smuggled-token",
            "Api-Key": "smuggled-key",
            "Authentication": "smuggled-auth",
            "X-Forwarded-For": "10.0.0.1",
            "X-Forwarded-Host": "internal.invalid",
            "X-Original-URL": "/admin",
            "X-Real-IP": "10.0.0.2",
            "Cookie": "session=abc",
            "X-Api-Key": "another-key",
            "Accept": "application/json",
        }

        response = await client.get(
            _proxy_url(conn_id, "/healthz"), headers={**headers, **smuggled}
        )
        assert response.status_code == 200, await response.get_data()

        forwarded = {name.lower() for name in upstream.last.headers}
        for name in smuggled:
            if name.lower() == "accept":
                continue
            assert name.lower() not in forwarded, f"{name} reached the product"
        for value in upstream.last.headers.values():
            assert "smuggled" not in value

    @pytest.mark.asyncio
    async def test_content_negotiation_headers_are_forwarded(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The allow-list is not a wall — negotiation still works.

        A filter that dropped everything would be trivially safe and useless;
        the point is that what crosses is chosen, not defaulted.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "HdrPass")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(
            _proxy_url(conn_id, "/healthz"),
            headers={
                **headers,
                "Accept": "application/vnd.gough+json",
                "Accept-Language": "en-GB",
                "If-None-Match": '"etag-1"',
            },
        )
        assert response.status_code == 200

        seen = upstream.last.headers
        assert seen.get("accept") == "application/vnd.gough+json"
        assert seen.get("accept-language") == "en-GB"
        assert seen.get("if-none-match") == '"etag-1"'


@pytest.mark.usefixtures("app_context")
class TestResponseHeaderStripping:
    """What comes back cannot borrow the portal's origin."""

    @pytest.mark.asyncio
    async def test_location_is_not_relayed(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A product cannot redirect the portal's users off-site.

        Relaying ``Location`` makes the portal an open redirect wearing its
        own origin: a link to the portal, followed by an authenticated user,
        lands on whatever host the product named.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "HdrLoc")
        conn_id = await _create_connection(app, tenant_id)

        upstream.status = 302
        upstream.body = b""
        upstream.headers = {
            "location": "https://phishing.invalid/login",
            "content-location": "https://phishing.invalid/x",
            "refresh": "0;url=https://phishing.invalid/",
            "set-cookie": "portal_session=stolen",
        }

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 302
        returned = {key.lower() for key in response.headers.keys()}
        for name in ("location", "content-location", "refresh", "set-cookie"):
            assert name not in returned


@pytest.mark.usefixtures("app_context")
class TestUpstreamProvenanceHeader:
    """`UPSTREAM_RESPONSE_HEADER` marks a body as forwarded from a product.

    services/webui/src/client/lib/mutationError.ts trusts this header to
    decide whether a response body is safe to show an operator verbatim: a
    portal-generated error (auth failure, validation error, a `_deny()`
    refusal) is shown as-is, but anything carrying this header is ALWAYS
    replaced with a generic message, regardless of content — a hostname, an
    internal IP, or a raw credential in an upstream error body is exactly
    what a content-shape denylist could never fully enumerate.
    """

    @pytest.mark.asyncio
    async def test_forwarded_response_carries_the_marker(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A body that reached the product and came back is marked."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "Provenance")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 200
        assert response.headers.get("X-Portal-Upstream-Response") == "true"

    @pytest.mark.asyncio
    async def test_portal_denial_does_not_carry_the_marker(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A refusal the portal generated itself is never marked upstream.

        `{"error": "Route not allowed"}` never reached the product — the
        request was refused before dispatch — so the webui client must be
        free to show it verbatim.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProvenanceDenied")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/admin/users"), headers=headers)

        assert response.status_code == 404
        assert upstream.requests == [], "denied request still reached the product"
        assert "X-Portal-Upstream-Response" not in response.headers

    @pytest.mark.asyncio
    async def test_a_product_cannot_forge_the_marker_on_its_own_response(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The product's own header of the same name never survives.

        If a product could set this header on its OWN response, it could
        mark its body "portal-native" and have the client trust content it
        never wrote — the header only means something because the PROXY is
        the sole writer of it, always last, always "true".
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProvenanceForge")
        conn_id = await _create_connection(app, tenant_id)

        upstream.headers = {
            "content-type": "application/json",
            "x-portal-upstream-response": "forged-by-product",
        }

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 200
        assert response.headers.get("X-Portal-Upstream-Response") == "true"


@pytest.mark.usefixtures("app_context")
class TestCorrelationId:
    """A caller-supplied trace id is validated, never trusted verbatim."""

    @pytest.mark.asyncio
    async def test_well_formed_correlation_id_is_honoured(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Stitching a caller's trace to ours is the reason to accept one."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "CorrOk")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(
            _proxy_url(conn_id, "/healthz"),
            headers={**headers, "X-Correlation-ID": "trace-abc.123:9"},
        )

        assert response.headers["X-Correlation-ID"] == "trace-abc.123:9"
        assert upstream.last.headers["x-correlation-id"] == "trace-abc.123:9"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "supplied",
        [
            "bad\r\nX-Injected: yes",
            "spaces are not allowed",
            "x" * 400,
            "<script>alert(1)</script>",
        ],
    )
    async def test_malformed_correlation_id_is_replaced_server_side(
        self, client: Any, app: Quart, upstream: _Upstream, supplied: str
    ) -> None:
        """An unvalidated id is echoed into logs and two headers.

        CR/LF is log injection and header splitting; an unbounded value
        bloats every line it touches. Substituting a server-generated id
        keeps the request working while guaranteeing nothing unvalidated is
        propagated — failing the whole call over a diagnostic header would
        reject a request for a reason unrelated to what it asked for.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "CorrBad")
        conn_id = await _create_connection(app, tenant_id)

        # The pattern is asserted directly as well as end-to-end: an HTTP
        # client may refuse to transmit a raw CR/LF header at all, which
        # would make the end-to-end case pass for the wrong reason.
        from app.proxy import _CORRELATION_ID_RE

        assert _CORRELATION_ID_RE.match(supplied) is None

        try:
            response = await client.get(
                _proxy_url(conn_id, "/healthz"),
                headers={**headers, "X-Correlation-ID": supplied},
            )
        except ValueError:
            # The client itself rejected it — still a refusal, and the
            # pattern assertion above already pinned the portal's behaviour.
            return

        echoed = response.headers["X-Correlation-ID"]
        assert echoed != supplied
        assert uuid.UUID(echoed)  # server-generated
