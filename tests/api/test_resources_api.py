"""Typed resource create/update/delete: the routes Nest's writes had no path to.

Nest's proxy allowlist is deliberately GET-only — every Nest write answers
``202`` with an ``operationId``, which :mod:`app.adapters.base` puts on a typed
adapter method rather than the byte-pipe proxy. ``create_resource`` and
``delete_resource`` were therefore implemented and verified against a live
Nest in Session 1, and reachable by nothing: no HTTP route exposed them, so a
Databases screen could list and act but not create or delete. ``update_resource``
was added later, for Gough's manifest-console ``edit`` capability, and had the
same gap: implemented and tested at the adapter layer, unreachable over HTTP.

These tests cover the route layer only. What the adapter does with Nest is
covered exhaustively in ``test_nest_adapter.py`` (including against a live
service); repeating it here would test httpx twice and the route logic once.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest import mock

import pytest
from app.adapters.base import (
    RESOURCE_OPERATION_ID_KEY,
    AdapterCapabilityError,
    Resource,
    ResourceConflictError,
)
from quart import Quart

PRODUCT_SECRET = "-".join(("not", "a", "real", "resources", "credential"))

#: Patch target for scope resolution — the binding ``has_tenant_scope`` looks
#: up at call time. See the note in ``test_operations_api.py``.
_AUTHZ_MODULE = "app.authz"


async def _register(client: Any) -> tuple[int, str]:
    """Register a user; return (id, email)."""
    email = f"res-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Res User"},
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


async def _create_tenant(client: Any, headers: dict[str, str]) -> int:
    """Create a tenant owned by the caller."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": "Res", "slug": f"res-{uuid.uuid4().hex[:6]}", "plan": "free"},
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _create_connection(
    app: Quart,
    tenant_id: int,
    *,
    is_active: bool = True,
    product_type: str = "nest",
) -> int:
    """Create a product connection plus its tenant mapping."""
    async with app.app_context():
        from app.models import create_product_connection, get_db, set_product_tenant_map

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type=product_type,
            display_name=f"Res {product_type}",
            base_url="https://product.invalid",
            auth_type="bearer",
            api_key=PRODUCT_SECRET,
            api_secret="",
        )
        assert conn_id is not None
        await set_product_tenant_map(conn_id, tenant_id, "tenant_id", "ext-res")
        if not is_active:
            db = get_db()
            await db(db.product_connections.id == conn_id).update(is_active=False)
            await db.commit()
        return int(conn_id)


@contextmanager
def _patched_scopes(replacement: Any) -> Iterator[None]:
    """Run a block with a specific scope set granted to every caller."""
    with mock.patch(f"{_AUTHZ_MODULE}.resolve_scopes", replacement):
        yield


def _resource(**overrides: Any) -> Resource:
    """A Nest data-resource as the adapter returns it."""
    defaults: dict[str, Any] = {
        "id": "orders-primary",
        "kind": "database",
        "name": "orders-primary",
        "status": "pending",
        "created_at": datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        "metadata": {"nest_id": "uuid-1", "resourceType": "postgres"},
    }
    defaults.update(overrides)
    return Resource(**defaults)


class StubAdapter:
    """Adapter double recording what the route handed it."""

    seen_ctx: Any = None
    seen_create: Any = None
    seen_update: Any = None
    seen_delete: Any = None
    resource: Resource | None = None
    raises: Exception | None = None

    def __init__(self) -> None:
        """Match the registry's zero-argument construction."""

    async def create_resource(self, kind: str, payload: dict[str, Any], ctx: Any) -> Resource:
        """Return the staged resource or raise the staged error."""
        StubAdapter.seen_ctx = ctx
        StubAdapter.seen_create = (kind, payload)
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        assert StubAdapter.resource is not None
        return StubAdapter.resource

    async def update_resource(
        self, kind: str, resource_id: str, payload: dict[str, Any], ctx: Any
    ) -> Resource:
        """Return the staged resource or raise the staged error."""
        StubAdapter.seen_ctx = ctx
        StubAdapter.seen_update = (kind, resource_id, payload)
        if StubAdapter.raises is not None:
            raise StubAdapter.raises
        assert StubAdapter.resource is not None
        return StubAdapter.resource

    async def delete_resource(self, kind: str, resource_id: str, ctx: Any) -> None:
        """Record the delete or raise the staged error."""
        StubAdapter.seen_ctx = ctx
        StubAdapter.seen_delete = (kind, resource_id)
        if StubAdapter.raises is not None:
            raise StubAdapter.raises


@pytest.fixture(autouse=True)
def _stub_adapter(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Swap the Nest adapter for the stub, and reset staged state."""
    StubAdapter.resource = _resource()
    StubAdapter.raises = None
    StubAdapter.seen_ctx = None
    StubAdapter.seen_create = None
    StubAdapter.seen_delete = None
    StubAdapter.seen_update = None
    monkeypatch.setitem(
        __import__("app.adapters", fromlist=["ADAPTER_REGISTRY"]).ADAPTER_REGISTRY,
        "nest",
        StubAdapter,
    )
    return StubAdapter


async def _setup(
    client: Any,
    app: Quart,
    *,
    is_active: bool = True,
    product_type: str = "nest",
) -> tuple[int, dict[str, str]]:
    """Register, create a tenant and a connection; return (conn_id, headers)."""
    _, email = await _register(client)
    headers = await _headers(client, email)
    tenant_id = await _create_tenant(client, headers)
    conn_id = await _create_connection(
        app, tenant_id, is_active=is_active, product_type=product_type
    )
    return conn_id, headers


@pytest.mark.asyncio
class TestCreate:
    """What a create publishes, and what it must not."""

    async def test_create_returns_the_row_and_its_poll_handle(
        self, client: Any, app: Quart
    ) -> None:
        """An async create hands back something to poll.

        Nest answers ``202`` and keeps provisioning. Without the handle the UI
        can only render the row as ready the moment creation was accepted,
        which is provisioning state it never checked.
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.resource = _resource(
            metadata={RESOURCE_OPERATION_ID_KEY: "op-9", "nest_id": "uuid-1"}
        )

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders-primary", "resourceType": "postgres"},
        )

        assert response.status_code == 201
        body = await response.get_json()
        assert body["id"] == "orders-primary"
        assert body["kind"] == "database"
        assert body["status"] == "pending"
        assert body["operation_id"] == "op-9"

    async def test_a_synchronous_create_reports_no_handle(self, client: Any, app: Quart) -> None:
        """``None`` is how the UI tells "nothing to poll" from "poll this"."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.resource = _resource(metadata={})

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders-primary"},
        )

        assert response.status_code == 201
        assert (await response.get_json())["operation_id"] is None

    async def test_response_publishes_only_declared_fields(self, client: Any, app: Quart) -> None:
        """The wire shape is an explicit DTO, not the dataclass.

        ``metadata`` is the adapter's free-form bag with no declared schema.
        Publishing it wholesale would make every key an adapter happens to
        stash there part of the portal's wire contract by accident — here that
        would leak Nest's internal ``nest_id`` and its raw record fields.
        """
        conn_id, headers = await _setup(client, app)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders-primary"},
        )

        body = await response.get_json()
        assert set(body) == {
            "id",
            "kind",
            "name",
            "status",
            "parent_id",
            "parent_kind",
            "operation_id",
            "created_at",
            "updated_at",
        }
        assert "metadata" not in body
        assert "nest_id" not in body

    async def test_the_handle_is_read_under_the_contract_key(self, client: Any, app: Quart) -> None:
        """The route and the adapter must agree on one spelling.

        Asserted through the constant rather than the literal: an adapter that
        stashed the handle under its own private key would publish
        ``operation_id: null`` while believing it had set one, and nothing else
        in the suite would notice.
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.resource = _resource(metadata={RESOURCE_OPERATION_ID_KEY: "op-contract"})

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "n"},
        )

        assert (await response.get_json())["operation_id"] == "op-contract"

    async def test_payload_reaches_the_adapter_unmodified(self, client: Any, app: Quart) -> None:
        """The route does not rewrite a create body.

        Nest's create/read field-name asymmetry is normalised in the ADAPTER
        (``mapping.to_create_payload``), which is the layer that knows the
        product. A second rewrite here would apply it twice.
        """
        conn_id, headers = await _setup(client, app)

        await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders", "resourceType": "postgres"},
        )

        assert StubAdapter.seen_create == (
            "database",
            {"name": "orders", "resourceType": "postgres"},
        )

    async def test_a_non_object_body_is_refused(self, client: Any, app: Quart) -> None:
        """A list or a bare string is not a create payload."""
        conn_id, headers = await _setup(client, app)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json=["not", "an", "object"],
        )

        assert response.status_code == 400
        assert StubAdapter.seen_create is None

    async def test_an_unsupported_kind_is_not_implemented(self, client: Any, app: Quart) -> None:
        """501, from the adapter's own literal table — never a built URL."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = AdapterCapabilityError("nest does not serve 'widget'")

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/widget",
            headers=headers,
            json={"name": "w"},
        )

        assert response.status_code == 501
        # Every AdapterError response is marked, this subclass included —
        # see adapters/base.py UPSTREAM_RESPONSE_HEADER on why it is not
        # worth excepting the ones that happen not to carry upstream text.
        assert response.headers.get("X-Portal-Upstream-Response") == "true"


@pytest.mark.asyncio
class TestUpdate:
    """The route the manifest console's ``edit`` capability calls.

    Typed for the same reason create is — see the module docstring — and
    required ``manage``, since an update mutates product state exactly as
    create does.
    """

    async def test_update_returns_the_updated_row(self, client: Any, app: Quart) -> None:
        """A successful update reports the resource the product returned."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.resource = _resource(name="orders-renamed", status="active")

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
            json={"name": "orders-renamed"},
        )

        assert response.status_code == 200, await response.get_json()
        body = await response.get_json()
        assert body["id"] == "orders-primary"
        assert body["name"] == "orders-renamed"
        assert body["status"] == "active"
        assert StubAdapter.seen_update == (
            "database",
            "orders-primary",
            {"name": "orders-renamed"},
        )

    async def test_a_non_object_body_is_refused(self, client: Any, app: Quart) -> None:
        """A list or a bare string is not an update payload."""
        conn_id, headers = await _setup(client, app)

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
            json=["not", "an", "object"],
        )

        assert response.status_code == 400
        assert StubAdapter.seen_update is None

    async def test_an_unsupported_update_is_not_implemented(self, client: Any, app: Quart) -> None:
        """501, the same clean error create's unsupported-kind case uses."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = AdapterCapabilityError("nest does not support updating 'widget'")

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/widget/w1",
            headers=headers,
            json={"name": "w"},
        )

        assert response.status_code == 501
        assert response.headers.get("X-Portal-Upstream-Response") == "true"

    async def test_a_still_referenced_resource_answers_409(self, client: Any, app: Quart) -> None:
        """The same conflict taxonomy delete uses applies to update."""
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = ResourceConflictError("resource is still referenced")

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
            json={"name": "n"},
        )

        assert response.status_code == 409

    async def test_a_non_member_gets_404_not_403(self, client: Any, app: Quart) -> None:
        """Same tenant-isolation oracle guard create and delete get."""
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers)
        conn_id = await _create_connection(app, tenant_id)

        _, other_email = await _register(client)
        other_headers = await _headers(client, other_email)

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/n",
            headers=other_headers,
            json={"name": "n"},
        )

        assert response.status_code == 404
        assert StubAdapter.seen_update is None

    async def test_read_scope_cannot_update(self, client: Any, app: Quart) -> None:
        """Update mutates product state, so it requires ``manage`` too."""
        conn_id, headers = await _setup(client, app)

        async def _read_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:nest:read"]

        with _patched_scopes(_read_only):
            response = await client.put(
                f"/api/v1/products/{conn_id}/resources/database/n",
                headers=headers,
                json={"name": "n"},
            )

        assert response.status_code == 403, "read scope reached a mutating route"
        assert StubAdapter.seen_update is None

    async def test_a_deactivated_connection_is_refused(self, client: Any, app: Quart) -> None:
        """The kill switch the proxy honours applies here too."""
        conn_id, headers = await _setup(client, app, is_active=False)

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/n",
            headers=headers,
            json={"name": "n"},
        )

        assert response.status_code == 403
        assert StubAdapter.seen_update is None

    async def test_an_anonymous_caller_is_rejected(self, client: Any, app: Quart) -> None:
        """No token, no route."""
        conn_id, _ = await _setup(client, app)

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/n", json={"name": "n"}
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestDelete:
    """Deletion, and the conflict a confirm dialog has to distinguish."""

    async def test_delete_acknowledges_the_resource_it_removed(
        self, client: Any, app: Quart
    ) -> None:
        """Echoed kind and id let a client attribute concurrent deletions."""
        conn_id, headers = await _setup(client, app)

        response = await client.delete(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
        )

        assert response.status_code == 200
        body = await response.get_json()
        assert body == {"kind": "database", "id": "orders-primary", "deleted": True}
        assert StubAdapter.seen_delete == ("database", "orders-primary")

    async def test_a_still_referenced_resource_answers_409(self, client: Any, app: Quart) -> None:
        """Both "Still referenced" and "already gone" are different answers.

        This is why delete is typed rather than proxied: the adapter maps
        Nest's 409 onto ``ResourceConflictError`` and the shared taxonomy
        renders it product-neutrally. A proxied 409 body is product-specific,
        so the dialog cannot tell the two apart.
        """
        conn_id, headers = await _setup(client, app)
        StubAdapter.raises = ResourceConflictError("resource is still referenced")

        response = await client.delete(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
        )

        assert response.status_code == 409
        # This exact message is the concrete regression the header closes:
        # the adapter's own raise_for_status interpolates Nest's response
        # body into it (see adapters/nest/responses.py), so it must never
        # be treated as portal-native by the webui client.
        assert response.headers.get("X-Portal-Upstream-Response") == "true"


@pytest.mark.asyncio
class TestAuthorisation:
    """Membership, scope and the kill switch, in that order."""

    async def test_a_non_member_gets_404_not_403(self, client: Any, app: Quart) -> None:
        """403 would confirm the id exists in someone else's tenant.

        A caller could then walk product_ids and map every connection in the
        deployment. The answer is byte-identical to "no such connection".
        """
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers)
        conn_id = await _create_connection(app, tenant_id)

        _, other_email = await _register(client)
        other_headers = await _headers(client, other_email)

        created = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=other_headers,
            json={"name": "n"},
        )
        deleted = await client.delete(
            f"/api/v1/products/{conn_id}/resources/database/n",
            headers=other_headers,
        )

        assert created.status_code == 404
        assert deleted.status_code == 404
        assert StubAdapter.seen_create is None
        assert StubAdapter.seen_delete is None

    async def test_read_scope_cannot_create_or_delete(self, client: Any, app: Quart) -> None:
        """Both verbs change product state, so both require ``manage``."""
        conn_id, headers = await _setup(client, app)

        async def _read_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:nest:read"]

        with _patched_scopes(_read_only):
            created = await client.post(
                f"/api/v1/products/{conn_id}/resources/database",
                headers=headers,
                json={"name": "n"},
            )
            deleted = await client.delete(
                f"/api/v1/products/{conn_id}/resources/database/n", headers=headers
            )

        assert created.status_code == 403, "read scope reached a mutating route"
        assert deleted.status_code == 403, "read scope reached a mutating route"

    async def test_a_nest_only_manage_scope_is_sufficient(self, client: Any, app: Quart) -> None:
        """The per-product model must not stop at the proxy.

        The principal these scopes exist for holds ``products:nest:manage`` and
        no coarse grant. Requiring ``products:manage`` here would refuse them
        the ability to create the very resource they were authorised to manage.
        """
        conn_id, headers = await _setup(client, app)

        async def _nest_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:nest:manage"]

        with _patched_scopes(_nest_only):
            created = await client.post(
                f"/api/v1/products/{conn_id}/resources/database",
                headers=headers,
                json={"name": "n"},
            )

        assert created.status_code == 201

    async def test_another_products_scope_cannot_write_to_nest(
        self, client: Any, app: Quart
    ) -> None:
        """A Gough grant is not a Nest grant."""
        conn_id, headers = await _setup(client, app)

        async def _gough_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:gough:manage"]

        with _patched_scopes(_gough_only):
            created = await client.post(
                f"/api/v1/products/{conn_id}/resources/database",
                headers=headers,
                json={"name": "n"},
            )

        assert created.status_code == 403

    async def test_a_deactivated_connection_is_refused(self, client: Any, app: Quart) -> None:
        """The kill switch the proxy honours applies here too.

        A deactivated connection must not have its credential decrypted, let
        alone used — so the adapter is never reached.
        """
        conn_id, headers = await _setup(client, app, is_active=False)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "n"},
        )

        assert response.status_code == 403
        assert StubAdapter.seen_create is None

    async def test_an_anonymous_caller_is_rejected(self, client: Any, app: Quart) -> None:
        """No token, no route."""
        conn_id, _ = await _setup(client, app)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database", json={"name": "n"}
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestProductCoverage:
    """These routes are open to EVERY adapter, not only the one they were for.

    ``resources_bp`` is registered once and matches ``/products/<id>/...`` for
    any connection, so shipping it for Nest simultaneously exposed a typed
    create and delete for Gough, Tobogganing and the generic fallback — none of
    which this phase exercised.

    ``test_adapter_registry`` has the registry-wide counterpart of the first
    half of this ("only integrated products may PROXY a mutating verb"), but
    that guard reads ``route_allowlist`` and says nothing about a typed route,
    which does not consult it at all.
    """

    #: Products whose adapter has a reviewed write path. Kept as a literal, in
    #: the same spirit as the proxy guard's own list: adding a product here is
    #: the reviewed act, and doing so without covering its writes is what the
    #: tests below are meant to make uncomfortable.
    INTEGRATED = ("gough", "nest")

    async def test_the_route_exists_for_every_registered_product(self) -> None:
        """Establishes the premise the rest of this class rests on.

        If these routes were somehow product-scoped, everything below would be
        testing a situation that cannot arise — and would pass while covering
        nothing.
        """
        from app.adapters import ADAPTER_REGISTRY

        assert set(ADAPTER_REGISTRY) - set(self.INTEGRATED), (
            "every registered product is integrated, so there is no "
            "non-integrated case left to guard — narrow or delete this class "
            "rather than leaving it passing vacuously"
        )

    @pytest.mark.parametrize("product_type", ["tobogganing", "generic"])
    async def test_a_non_integrated_product_refuses_a_typed_write(
        self, product_type: str, client: Any, app: Quart
    ) -> None:
        """501, and specifically not 200, 404 or 500.

        A product with no write implementation must answer "this portal cannot
        do that for this product" — the same fail-closed default the proxy
        allowlist gives, asserted at the layer that does not read it. A 500
        would read as an outage; a 200 would mean something wrote.
        """
        conn_id, headers = await _setup(client, app, product_type=product_type)

        created = await client.post(
            f"/api/v1/products/{conn_id}/resources/thing",
            headers=headers,
            json={"name": "x"},
        )
        updated = await client.put(
            f"/api/v1/products/{conn_id}/resources/thing/x",
            headers=headers,
            json={"name": "x"},
        )
        deleted = await client.delete(
            f"/api/v1/products/{conn_id}/resources/thing/x", headers=headers
        )

        assert created.status_code == 501, await created.get_json()
        assert updated.status_code == 501, await updated.get_json()
        assert deleted.status_code == 501, await deleted.get_json()

    @pytest.mark.parametrize("product_type", ["tobogganing", "generic"])
    async def test_a_non_integrated_product_still_enforces_scope_first(
        self, product_type: str, client: Any, app: Quart
    ) -> None:
        """Authorisation is not skipped on the way to a 501.

        A 501 reached BEFORE the scope check would be a route that tells an
        unauthorised caller which products the portal cannot write to — minor
        on its own, and an ordering bug that a future implementation of that
        adapter would turn into a real one.
        """
        conn_id, headers = await _setup(client, app, product_type=product_type)

        async def _read_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:read"]

        with _patched_scopes(_read_only):
            response = await client.post(
                f"/api/v1/products/{conn_id}/resources/thing",
                headers=headers,
                json={"name": "x"},
            )

        assert response.status_code == 403, await response.get_json()


@pytest.mark.asyncio
class TestGoughThroughTheTypedRoutes:
    """Gough's create and delete, which this route exposed and 4N never drove.

    Gough's adapter had `create_resource`/`delete_resource` before these routes
    existed; adding them made both reachable over HTTP for the first time. The
    adapter itself is covered in ``test_gough_adapter.py`` — what is asserted
    here is the route layer for a SECOND product, so the coupling between
    ``ResourceView`` and any one adapter's metadata conventions shows up.
    """

    @pytest.fixture(autouse=True)
    def _gough_stub(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Swap Gough's adapter for the recording stub."""
        StubAdapter.resource = _resource(
            id="biome-1", kind="biomes", name="edge", status="active", metadata={}
        )
        StubAdapter.raises = None
        StubAdapter.seen_create = None
        StubAdapter.seen_update = None
        StubAdapter.seen_delete = None
        monkeypatch.setitem(
            __import__("app.adapters", fromlist=["ADAPTER_REGISTRY"]).ADAPTER_REGISTRY,
            "gough",
            StubAdapter,
        )
        return StubAdapter

    async def test_create_reaches_the_gough_adapter_with_its_own_kind(
        self, client: Any, app: Quart
    ) -> None:
        """``kind`` is the product's vocabulary and is passed through as-is."""
        conn_id, headers = await _setup(client, app, product_type="gough")

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/biomes",
            headers=headers,
            json={"name": "edge"},
        )

        assert response.status_code == 201, await response.get_json()
        assert StubAdapter.seen_create == ("biomes", {"name": "edge"})
        assert (await response.get_json())["kind"] == "biomes"

    async def test_a_synchronous_create_reports_no_handle_for_gough_either(
        self, client: Any, app: Quart
    ) -> None:
        """Gough's creates are synchronous, so ``operation_id`` must be null.

        ``ResourceView`` lifts the poll handle out of ``metadata`` under a key
        the CONTRACT names. A second product proves that projection is not
        wired to Nest's conventions: Gough sets no such key and must report
        ``None`` rather than inventing a handle or 500ing on a missing one.
        """
        conn_id, headers = await _setup(client, app, product_type="gough")

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/biomes",
            headers=headers,
            json={"name": "edge"},
        )

        assert (await response.get_json())["operation_id"] is None

    async def test_update_reaches_the_gough_adapter(self, client: Any, app: Quart) -> None:
        """The route the manifest console's biome ``edit`` capability calls.

        Gough's adapter has ``update_resource`` (nodes take PATCH, biomes and
        groups take PUT internally) — this is what the frontend's edit action
        had no HTTP route to reach before this route existed.
        """
        conn_id, headers = await _setup(client, app, product_type="gough")

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/biomes/biome-1",
            headers=headers,
            json={"name": "edge-renamed"},
        )

        assert response.status_code == 200, await response.get_json()
        assert StubAdapter.seen_update == ("biomes", "biome-1", {"name": "edge-renamed"})

    async def test_delete_reaches_the_gough_adapter(self, client: Any, app: Quart) -> None:
        """The delete path is equally live for Gough, and equally untested."""
        conn_id, headers = await _setup(client, app, product_type="gough")

        response = await client.delete(
            f"/api/v1/products/{conn_id}/resources/biomes/biome-1", headers=headers
        )

        assert response.status_code == 200, await response.get_json()
        assert StubAdapter.seen_delete == ("biomes", "biome-1")

    async def test_an_unsupported_gough_kind_is_a_501_not_a_write(
        self, client: Any, app: Quart
    ) -> None:
        """Gough refuses to "create" a node — they are discovered, not made.

        Reached through the route rather than the adapter, because the route is
        what an operator can call.
        """
        conn_id, headers = await _setup(client, app, product_type="gough")
        StubAdapter.raises = AdapterCapabilityError("gough does not create nodes")

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/nodes",
            headers=headers,
            json={"name": "n1"},
        )

        assert response.status_code == 501

    async def test_read_scope_cannot_create_update_or_delete_for_gough(
        self, client: Any, app: Quart
    ) -> None:
        """The manage requirement is per-route, not per-product."""
        conn_id, headers = await _setup(client, app, product_type="gough")

        async def _read_only(user_id: int, tenant_id: int) -> list[str]:
            return ["products:gough:read"]

        with _patched_scopes(_read_only):
            created = await client.post(
                f"/api/v1/products/{conn_id}/resources/biomes",
                headers=headers,
                json={"name": "edge"},
            )
            updated = await client.put(
                f"/api/v1/products/{conn_id}/resources/biomes/b1",
                headers=headers,
                json={"name": "edge"},
            )
            deleted = await client.delete(
                f"/api/v1/products/{conn_id}/resources/biomes/b1", headers=headers
            )

        assert created.status_code == 403
        assert updated.status_code == 403
        assert deleted.status_code == 403
        assert StubAdapter.seen_create is None
        assert StubAdapter.seen_update is None
        assert StubAdapter.seen_delete is None


@pytest.mark.asyncio
class TestTheModuleKillSwitchReachesTheTypedSurface:
    """`penguincloud.{product}` false must stop the routes that do the work.

    The gate ran at connection create and in the proxy only, so with a
    module switched off resource create still created and resource actions
    still executed. "Disable a module without a redeploy" was not true of
    the typed surface.

    These are behavioural: the structural guard in
    ``test_gate_coverage_is_derived.py`` proves no route ESCAPES the gate;
    these two prove the gate actually refuses.
    """

    @staticmethod
    def _kill(monkeypatch: pytest.MonkeyPatch, product: str = "nest") -> None:
        from app import flags
        from conftest import _FakeFlagServer

        monkeypatch.setattr(
            flags,
            "_client",
            _FakeFlagServer(flags.PRODUCT_FLAGS - {product}, disabled=frozenset({product})),
        )
        monkeypatch.setattr(flags, "_client_built", True)
        flags._CACHE.clear()

    async def test_resource_create_is_refused(
        self, client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A killed product flag refuses resource creation before the adapter builds."""
        conn_id, headers = await _setup(client, app)
        self._kill(monkeypatch)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders-primary", "resourceType": "postgres"},
        )

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "feature_disabled"
        # And nothing reached the product: the refusal happens before the
        # adapter is built, so a disabled module's credential is never even
        # decrypted.
        assert StubAdapter.seen_create is None

    async def test_resource_update_is_refused(
        self, client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A killed product flag refuses resource update before the adapter builds."""
        conn_id, headers = await _setup(client, app)
        self._kill(monkeypatch)

        response = await client.put(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
            json={"name": "orders-renamed"},
        )

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "feature_disabled"
        assert StubAdapter.seen_update is None

    async def test_resource_delete_is_refused(
        self, client: Any, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A killed product flag refuses resource deletion before the adapter builds."""
        conn_id, headers = await _setup(client, app)
        self._kill(monkeypatch)

        response = await client.delete(
            f"/api/v1/products/{conn_id}/resources/database/orders-primary",
            headers=headers,
        )

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "feature_disabled"
        assert StubAdapter.seen_delete is None

    async def test_an_enabled_module_still_works(self, client: Any, app: Quart) -> None:
        """The positive case, so the refusals above are not vacuous."""
        conn_id, headers = await _setup(client, app)

        response = await client.post(
            f"/api/v1/products/{conn_id}/resources/database",
            headers=headers,
            json={"name": "orders-primary", "resourceType": "postgres"},
        )

        assert response.status_code == 201
