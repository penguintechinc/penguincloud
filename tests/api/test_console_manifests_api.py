"""``GET /api/v1/console/manifests`` — route-level behaviour.

Uses the REAL ``GoughAdapter`` rather than a stub: :meth:`GoughAdapter.capabilities`
makes no outbound call (a hardcoded list — see ``adapters/gough/adapter.py``),
so nothing here needs network stubbing the way ``test_resources_api.py`` and
``test_operations_api.py`` do for routes that actually reach a product.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app import flags
from app.adapters import MANIFEST_REGISTRY
from conftest import _FakeFlagServer
from quart import Quart

_FEATURE = "declarative_console"


@pytest.fixture
def console_flag_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in: enable ``declarative_console`` on top of every product flag.

    Not autouse — a genuinely new feature defaults OFF (general.md), and
    ``test_flag_disabled_refuses_with_403`` below exercises exactly that
    default with no extra setup.
    """
    monkeypatch.setattr(
        flags, "_client", _FakeFlagServer(flags.PRODUCT_FLAGS | frozenset({_FEATURE}))
    )
    monkeypatch.setattr(flags, "_client_built", True)


async def _register(client: Any) -> str:
    email = f"cm-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Console User"},
    )
    assert response.status_code in (200, 201), await response.get_json()
    return email


async def _headers(client: Any, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert response.status_code == 200, await response.get_json()
    return {"Authorization": f"Bearer {(await response.get_json())['access_token']}"}


async def _create_tenant(client: Any, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": "Console", "slug": f"console-{uuid.uuid4().hex[:6]}", "plan": "free"},
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _create_connection(
    app: Quart,
    tenant_id: int,
    *,
    is_active: bool = True,
    product_type: str = "gough",
) -> int:
    async with app.app_context():
        from app.models import create_product_connection, get_db, set_product_tenant_map

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type=product_type,
            display_name=f"Console {product_type}",
            base_url="https://product.invalid",
            auth_type="bearer",
            api_key="-".join(("not", "a", "real", "console", "credential")),
            api_secret="",
        )
        assert conn_id is not None
        await set_product_tenant_map(conn_id, tenant_id, "tenant_id", "ext-console")
        if not is_active:
            db = get_db()
            await db(db.product_connections.id == conn_id).update(is_active=False)
            await db.commit()
        return int(conn_id)


async def _setup(
    client: Any, app: Quart, *, is_active: bool = True, product_type: str = "gough"
) -> tuple[int, dict[str, str], int]:
    """Register, create a tenant and a connection; return (conn_id, headers, tenant_id)."""
    email = await _register(client)
    headers = await _headers(client, email)
    tenant_id = await _create_tenant(client, headers)
    conn_id = await _create_connection(
        app, tenant_id, is_active=is_active, product_type=product_type
    )
    return conn_id, headers, tenant_id


@pytest.mark.asyncio
async def test_flag_disabled_refuses_with_403(client: Any, app: Quart) -> None:
    """No ``console_flag_enabled`` fixture here — the default is what is tested."""
    _, headers, tenant_id = await _setup(client, app)

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 403
    body = await response.get_json()
    assert body["error"] == "feature_disabled"
    assert body["feature"] == _FEATURE


@pytest.mark.asyncio
async def test_missing_tenant_id_is_a_400(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Missing tenant id is a 400."""
    _, headers, _ = await _setup(client, app)

    response = await client.get("/api/v1/console/manifests", headers=headers)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_malformed_tenant_id_is_also_a_400(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """A non-integer tenant_id is also a 400, not a 500."""
    _, headers, _ = await _setup(client, app)

    response = await client.get("/api/v1/console/manifests?tenant_id=not-a-number", headers=headers)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_gough_connection_yields_one_manifest_entry(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Gough connection yields one manifest entry."""
    conn_id, headers, tenant_id = await _setup(client, app, product_type="gough")

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 200
    body = await response.get_json()
    assert body["count"] == 1
    assert len(body["manifests"]) == 1
    entry = body["manifests"][0]
    assert entry["product_id"] == conn_id
    assert entry["product_type"] == "gough"
    assert entry["manifest"]["product_type"] == "gough"
    kinds = {resource["kind"] for resource in entry["manifest"]["resources"]}
    assert kinds == {"nodes", "biomes", "biome_groups", "agents"}


@pytest.mark.asyncio
async def test_gough_manifest_survives_the_wire_round_trip_unchanged(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Gough's capabilities() reports everything.

    So the overlay must not have dropped anything the committed manifest
    declared.
    """
    _, headers, tenant_id = await _setup(client, app, product_type="gough")
    committed = MANIFEST_REGISTRY["gough"]

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    body = await response.get_json()
    served = body["manifests"][0]["manifest"]
    served_nodes = next(r for r in served["resources"] if r["kind"] == "nodes")
    committed_nodes = committed.resource("nodes")
    assert committed_nodes is not None
    assert {a["verb"] for a in served_nodes["actions"]} == {a.verb for a in committed_nodes.actions}
    assert served_nodes["delete"] is not None
    assert {item["kind"] for item in served["nav"]["items"]} == {
        item.kind for item in committed.nav.items
    }


@pytest.mark.asyncio
async def test_deactivated_connection_is_excluded(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Deactivated connection is excluded."""
    _, headers, tenant_id = await _setup(client, app, is_active=False, product_type="gough")

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"manifests": [], "count": 0}


@pytest.mark.asyncio
async def test_a_product_with_no_committed_manifest_is_excluded(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Nest has an adapter but (as of Phase 8 Step 3) no manifest yet."""
    assert "nest" not in MANIFEST_REGISTRY  # the fact this test depends on
    _, headers, tenant_id = await _setup(client, app, product_type="nest")

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"manifests": [], "count": 0}


@pytest.mark.asyncio
async def test_a_non_member_tenant_id_yields_the_same_empty_body_as_no_products(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Oracle safety.

    A stranger to ``tenant_id`` and a member with zero eligible products
    must be indistinguishable — see the module docstring in
    ``app/console_manifests.py``.
    """
    # A real tenant with a real, eligible Gough connection ...
    _owner_conn_id, _owner_headers, tenant_id = await _setup(client, app, product_type="gough")
    # ... queried by a completely unrelated, newly registered caller.
    stranger_email = await _register(client)
    stranger_headers = await _headers(client, stranger_email)

    response = await client.get(
        f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=stranger_headers
    )

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"manifests": [], "count": 0}


@pytest.mark.asyncio
async def test_response_publishes_only_declared_top_level_fields(
    client: Any, app: Quart, console_flag_enabled: None
) -> None:
    """Response publishes only declared top level fields."""
    _, headers, tenant_id = await _setup(client, app, product_type="gough")

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    body = await response.get_json()
    assert set(body) == {"manifests", "count"}
    assert set(body["manifests"][0]) == {"product_id", "product_type", "manifest"}


@pytest.mark.asyncio
async def test_a_connection_whose_capabilities_call_raises_is_skipped_not_fatal(
    client: Any, app: Quart, console_flag_enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One connection's adapter failure must not blank the whole response."""
    from app.adapter_errors import AdapterCapabilityError
    from app.adapters import ADAPTER_REGISTRY
    from app.adapters.gough import GoughAdapter

    class _FailingCapabilitiesAdapter(GoughAdapter):
        async def capabilities(self, ctx: Any) -> list[str]:
            raise AdapterCapabilityError("simulated capabilities failure")

    monkeypatch.setitem(ADAPTER_REGISTRY, "gough", _FailingCapabilitiesAdapter)
    _, headers, tenant_id = await _setup(client, app, product_type="gough")

    response = await client.get(f"/api/v1/console/manifests?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {"manifests": [], "count": 0}
