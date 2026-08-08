"""Deny-by-default proxy: allowlist, scope, credential containment.

The proxy is the one place in the portal that decrypts a stored third-party
credential and makes an outbound call with it. Three properties have to hold
simultaneously, and each has a different failure mode:

1. **Deny by default.** Only a route an adapter explicitly declared is
   forwarded. The old catch-all ``/<product_id>/<path>`` relayed anything to
   anywhere with the credential attached.
2. **Scope, not role.** The rule's ``required_scope`` is checked against the
   caller's authority *in the connection's tenant*, so a delegated MSP admin
   reaches their customer's products and an outsider does not.
3. **The credential never comes back.** The caller is authorized to *use* a
   connection, never to *read* its secret. A product that echoes its auth
   header — on an error page, a debug route, a reflected parameter — would
   otherwise hand it to them.

Outbound calls are intercepted with ``httpx.MockTransport``, which is httpx's
own hook, so the real client, real header assembly and real retry loop are
all exercised; only the socket is replaced.
"""

from typing import Any
import uuid

import httpx
import pytest
from quart import Quart

# Synthetic credentials, assembled rather than written as literals.
# A high-entropy string spelled out in source is exactly what secret
# scanners exist to catch, and teaching the scanner to ignore this file
# would blind it to a real credential landing here later. Joining
# obviously-fake words keeps entropy low while staying distinctive
# enough that finding it in a response body means the proxy leaked it.
PRODUCT_SECRET = "-".join(("not", "a", "real", "product", "credential"))
PRODUCT_SECRET_2 = "-".join(("not", "a", "real", "product", "secondary"))


async def _register(client: Any) -> tuple[int, str]:
    """Register a user; return (id, email)."""
    email = f"proxy-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Proxy User"},
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


async def _create_connection(
    app: Quart,
    tenant_id: int,
    *,
    product_type: str = "gough",
    external_id: str = "ext-tenant-42",
    api_key: str = PRODUCT_SECRET,
    api_secret: str = "",
    auth_type: str = "bearer",
) -> int:
    """Create a product connection plus its tenant mapping."""
    async with app.app_context():
        from app.models import create_product_connection, set_product_tenant_map

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type=product_type,
            display_name="Test Product",
            base_url="https://product.invalid",
            auth_type=auth_type,
            api_key=api_key,
            api_secret=api_secret,
        )
        assert conn_id is not None
        # "tenant_id" is the server-derived external_kind for the three
        # active products (see products._validate_external_kind); the
        # column carries a CHECK constraint, so it is not free text.
        await set_product_tenant_map(conn_id, tenant_id, "tenant_id", external_id)
        return int(conn_id)


async def _attach_child(app: Quart, child_id: int, parent_id: int) -> None:
    """Make child a descendant of parent at the schema level."""
    async with app.app_context():
        from app.models import get_db
        from app.tenancy import invalidate_tenant

        db = get_db()
        await db(db.tenants.id == child_id).update(parent_tenant_id=parent_id)
        await db.commit()
        await invalidate_tenant(child_id)
        await invalidate_tenant(parent_id)


class _Upstream:
    """Records what the product actually received, and replies as told."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body = b'{"ok": true}'
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.fail_times = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        """MockTransport handler."""
        self.requests.append(request)
        if self.fail_times > 0:
            self.fail_times -= 1
            return httpx.Response(503, content=b"upstream down")
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

    async def _get_transport(timeout: float = 10.0) -> Any:
        instance = transport_module.Transport(timeout=timeout)
        instance._client = httpx.AsyncClient(
            transport=httpx.MockTransport(fake.handler),
            timeout=httpx.Timeout(timeout),
        )
        return instance

    monkeypatch.setattr(transport_module, "get_transport", _get_transport)
    monkeypatch.setattr("app.proxy.get_transport", _get_transport)
    return fake


def _proxy_url(connection_id: int, path: str) -> str:
    """Build the proxy URL for a connection and downstream path."""
    return f"/api/v1/products/{connection_id}/proxy{path}"


@pytest.mark.usefixtures("app_context")
class TestAllowlistMatrix:
    """One allowed case, and every way of being refused."""

    @pytest.mark.asyncio
    async def test_allowed_rule_is_forwarded(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A declared route with sufficient scope reaches the product."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyAllowed")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 200, await response.get_data()
        assert upstream.requests, "allowed route never reached the product"
        assert upstream.last.url.path == "/healthz"

    @pytest.mark.asyncio
    async def test_unlisted_path_is_denied(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A path no rule declares is refused — and never dispatched.

        Asserting the product was not called matters more than the status
        code: a proxy that forwards first and judges afterwards has already
        leaked the request.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyUnlisted")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(
            _proxy_url(conn_id, "/admin/users"), headers=headers
        )

        assert response.status_code == 404
        assert upstream.requests == [], "denied route still reached the product"

    @pytest.mark.asyncio
    async def test_method_mismatch_is_denied(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The allowlist is (method, path) — a declared path is not a free pass."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyMethod")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.post(
            _proxy_url(conn_id, "/healthz"), headers=headers, json={}
        )

        assert response.status_code == 404
        assert upstream.requests == []

    @pytest.mark.asyncio
    async def test_insufficient_scope_is_denied(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A caller with no authority in the connection's tenant is refused."""
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "ProxyScope")
        conn_id = await _create_connection(app, tenant_id)

        _, outsider_email = await _register(client)
        outsider_headers = await _headers(client, outsider_email)

        response = await client.get(
            _proxy_url(conn_id, "/healthz"), headers=outsider_headers
        )

        assert response.status_code == 403
        assert upstream.requests == []

    @pytest.mark.asyncio
    async def test_generic_adapter_forwards_nothing(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The empty allowlist on `generic` is enforced, not decorative."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyGeneric")
        conn_id = await _create_connection(app, tenant_id, product_type="generic")

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 404
        assert upstream.requests == []

    @pytest.mark.asyncio
    async def test_unauthenticated_request_is_refused(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """No token, no proxying."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyAnon")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz"))

        assert response.status_code == 401
        assert upstream.requests == []

    @pytest.mark.asyncio
    async def test_oversize_request_body_rejected_before_dispatch(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A body over the cap is refused by the portal, not relayed."""
        import app.proxy as proxy_module

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyBig")
        conn_id = await _create_connection(app, tenant_id)

        # Shrink the cap rather than building a 10MB body in a unit test.
        original = proxy_module.MAX_REQUEST_SIZE
        proxy_module.MAX_REQUEST_SIZE = 16
        try:
            response = await client.get(
                _proxy_url(conn_id, "/healthz"),
                headers=headers,
                data=b"x" * 512,
            )
        finally:
            proxy_module.MAX_REQUEST_SIZE = original

        assert response.status_code == 413
        assert upstream.requests == []

    @pytest.mark.asyncio
    async def test_oversize_response_body_rejected(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A product returning more than the cap yields 502, not the body."""
        import app.adapters.transport as transport_module

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyBigResp")
        conn_id = await _create_connection(app, tenant_id)

        upstream.body = b"y" * 4096
        original = transport_module.MAX_RESPONSE_SIZE
        transport_module.MAX_RESPONSE_SIZE = 128
        try:
            response = await client.get(
                _proxy_url(conn_id, "/healthz"), headers=headers
            )
        finally:
            transport_module.MAX_RESPONSE_SIZE = original

        assert response.status_code == 502
        assert b"yyyy" not in await response.get_data()

    @pytest.mark.asyncio
    async def test_missing_connection_is_not_an_oracle(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """An unknown connection id 404s without touching the network."""
        _, email = await _register(client)
        headers = await _headers(client, email)

        response = await client.get(_proxy_url(999999, "/healthz"), headers=headers)

        assert response.status_code == 404
        assert upstream.requests == []


@pytest.mark.usefixtures("app_context")
class TestCredentialContainment:
    """The injected credential goes out and never comes back."""

    @pytest.mark.asyncio
    async def test_inbound_authorization_is_stripped_and_replaced(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The product sees its own credential, never the caller's portal JWT.

        Forwarding the caller's token would hand a third-party product a
        live credential for THIS portal — a far worse leak than anything the
        proxy is protecting downstream.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyAuth")
        conn_id = await _create_connection(app, tenant_id)

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        assert response.status_code == 200

        forwarded = upstream.last.headers.get("authorization", "")
        assert forwarded == f"Bearer {PRODUCT_SECRET}"
        portal_token = headers["Authorization"].removeprefix("Bearer ")
        assert portal_token not in forwarded
        for raw in upstream.last.headers.values():
            assert portal_token not in raw, "portal JWT reached the product"

    @pytest.mark.asyncio
    async def test_echoed_credential_is_redacted_from_the_body(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A product echoing its auth header must not leak it to the caller.

        THE regression test for this phase. Some products reflect the
        Authorization header into error text or a debug payload; the caller
        is authorized to use the connection, never to read its secret.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyEcho")
        conn_id = await _create_connection(app, tenant_id)

        upstream.body = (
            b'{"error": "unauthorized", "received_header": '
            b'"Bearer ' + PRODUCT_SECRET.encode() + b'"}'
        )

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        body = await response.get_data()

        assert PRODUCT_SECRET.encode() not in body
        assert b"[REDACTED]" in body

    @pytest.mark.asyncio
    async def test_credential_redacted_on_the_error_path(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Redaction is unconditional — a 5xx body gets it too.

        Error pages are the MOST likely place for a product to spill a
        request header, so exempting non-2xx responses would exempt the
        common case.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyErr")
        conn_id = await _create_connection(app, tenant_id)

        upstream.status = 500
        upstream.body = b"traceback: auth=" + PRODUCT_SECRET.encode() + b" failed"

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        body = await response.get_data()

        assert response.status_code == 500
        assert PRODUCT_SECRET.encode() not in body

    @pytest.mark.asyncio
    async def test_credential_redacted_from_response_headers(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A reflected header leaks exactly as much as a reflected body."""
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyHdr")
        conn_id = await _create_connection(app, tenant_id)

        upstream.headers = {
            "content-type": "application/json",
            "x-echo-auth": f"Bearer {PRODUCT_SECRET}",
        }

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        for value in response.headers.values():
            assert PRODUCT_SECRET not in value

    @pytest.mark.asyncio
    async def test_basic_auth_blob_is_redacted(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """The base64 form is redacted too — encoded is just as usable.

        Redacting only the plaintext would miss the exact string a product
        is most likely to echo, since basic auth travels encoded.
        """
        import base64

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyBasic")
        conn_id = await _create_connection(
            app,
            tenant_id,
            auth_type="basic",
            api_key=PRODUCT_SECRET,
            api_secret=PRODUCT_SECRET_2,
        )

        blob = base64.b64encode(
            f"{PRODUCT_SECRET}:{PRODUCT_SECRET_2}".encode()
        ).decode()
        upstream.body = f'{{"echo": "Basic {blob}"}}'.encode()

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)
        body = await response.get_data()

        assert blob.encode() not in body
        assert PRODUCT_SECRET.encode() not in body
        assert PRODUCT_SECRET_2.encode() not in body

    @pytest.mark.asyncio
    async def test_no_proxy_response_ever_contains_the_secret(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Sweep every reachable proxy outcome for the credential.

        Deliberately broad: allowed, denied, errored and oversized paths all
        share one assertion, so a future branch that returns early without
        redacting is caught by this test rather than by a customer.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxySweep")
        conn_id = await _create_connection(app, tenant_id)

        _, outsider_email = await _register(client)
        outsider_headers = await _headers(client, outsider_email)

        upstream.body = b'{"echo": "' + PRODUCT_SECRET.encode() + b'"}'

        cases = [
            ("get", _proxy_url(conn_id, "/healthz"), headers),
            ("get", _proxy_url(conn_id, "/capabilities"), headers),
            ("get", _proxy_url(conn_id, "/not-allowed"), headers),
            ("post", _proxy_url(conn_id, "/healthz"), headers),
            ("get", _proxy_url(conn_id, "/healthz"), outsider_headers),
            ("get", _proxy_url(999999, "/healthz"), headers),
        ]

        for method, url, hdrs in cases:
            response = await getattr(client, method)(url, headers=hdrs)
            payload = await response.get_data()
            assert PRODUCT_SECRET.encode() not in payload, f"{method} {url}"
            for value in response.headers.values():
                assert PRODUCT_SECRET not in value, f"{method} {url} (header)"

    @pytest.mark.asyncio
    async def test_undersized_credential_refuses_to_proxy(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """A credential too short to redact safely fails closed.

        Redacting a 2-character secret would corrupt unrelated content;
        NOT redacting it would leak. Refusing the call is the only option
        that is neither, and a 2-character API key is a misconfiguration.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxyShort")
        conn_id = await _create_connection(app, tenant_id, api_key="ab")

        response = await client.get(_proxy_url(conn_id, "/healthz"), headers=headers)

        assert response.status_code == 502
        assert upstream.requests == []


@pytest.mark.usefixtures("app_context")
class TestDelegatedAdminThroughProxy:
    """Delegated authority reaches a descendant's products."""

    @pytest.mark.asyncio
    async def test_delegated_admin_proxies_to_descendant_product(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """An MSP admin reaches a customer's product without membership.

        The connection belongs to the customer tenant; the MSP user has no
        tenant_members row there. Authorization comes from the ancestor, via
        the same resolve_scopes the token issuer uses.
        """
        _, msp_email = await _register(client)
        msp_headers = await _headers(client, msp_email)
        _, customer_email = await _register(client)
        customer_headers = await _headers(client, customer_email)

        parent_id = await _create_tenant(client, msp_headers, "MspProxy")
        child_id = await _create_tenant(client, customer_headers, "CustProxy")
        await _attach_child(app, child_id, parent_id)

        conn_id = await _create_connection(app, child_id)

        async with app.app_context():
            from app.models import get_user_by_email, get_user_tenant_role

            msp_user = await get_user_by_email(msp_email)
            assert msp_user is not None
            # The premise: authority is delegated, not direct.
            assert await get_user_tenant_role(int(msp_user["id"]), child_id) is None

        response = await client.get(
            _proxy_url(conn_id, "/healthz"), headers=msp_headers
        )

        assert response.status_code == 200, await response.get_data()
        assert upstream.requests, "delegated admin was not proxied through"

    @pytest.mark.asyncio
    async def test_sibling_tenant_admin_is_refused(
        self, client: Any, app: Quart, upstream: _Upstream
    ) -> None:
        """Delegation flows down the tree, never sideways.

        An admin of one customer must not reach a sibling customer's
        product just because they share a provider.
        """
        _, msp_email = await _register(client)
        msp_headers = await _headers(client, msp_email)
        _, a_email = await _register(client)
        a_headers = await _headers(client, a_email)
        _, b_email = await _register(client)
        b_headers = await _headers(client, b_email)

        parent_id = await _create_tenant(client, msp_headers, "MspSib")
        a_id = await _create_tenant(client, a_headers, "CustA")
        b_id = await _create_tenant(client, b_headers, "CustB")
        await _attach_child(app, a_id, parent_id)
        await _attach_child(app, b_id, parent_id)

        b_conn = await _create_connection(app, b_id)

        response = await client.get(_proxy_url(b_conn, "/healthz"), headers=a_headers)

        assert response.status_code == 403
        assert upstream.requests == []


@pytest.mark.usefixtures("app_context")
class TestTenantSubstitution:
    """The product is addressed by ITS identifier, never the portal's."""

    @pytest.mark.asyncio
    async def test_placeholder_is_replaced_with_mapped_external_id(
        self, client: Any, app: Quart, upstream: _Upstream, monkeypatch: Any
    ) -> None:
        """{tenant} in the path resolves from product_tenant_map, server-side.

        Server-derived on purpose: if the caller supplied the identifier
        they could address another customer's data inside the product by
        editing the path.
        """
        from app.adapters import ADAPTER_REGISTRY
        from app.adapters.base import RouteRule

        monkeypatch.setattr(
            ADAPTER_REGISTRY["gough"],
            "route_allowlist",
            [RouteRule("GET", r"^/orgs/\{tenant\}/vms$", "products:read")],
        )

        _, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "ProxySub")
        conn_id = await _create_connection(app, tenant_id, external_id="acme-corp-9000")

        response = await client.get(
            _proxy_url(conn_id, "/orgs/{tenant}/vms"), headers=headers
        )

        assert response.status_code == 200, await response.get_data()
        assert upstream.last.url.path == "/orgs/acme-corp-9000/vms"
        assert str(tenant_id) not in upstream.last.url.path
