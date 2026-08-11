"""GET /api/v1/products/health — endpoint DTO + tenant scoping.

Requirement 3: cached-only response, provider-scope (include_children)
subtree rollup respecting the Phase 2 rule. Requirement 5: "endpoint DTO +
tenant scoping". Poller/cache internals are covered by
test_health_poller.py and test_health_cache.py respectively.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from app.adapters.generic_adapter import GenericAdapter
from app.health_cache import CachedHealth, set_health


async def _register_connection(
    client: Any,
    headers: dict[str, str],
    tenant_id: int,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "product_type": "generic",
        "display_name": "Health API Test Product",
        "base_url": "https://example.invalid",
        "auth_type": "none",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/products", headers=headers, json=payload)
    assert response.status_code == 201, f"Failed to register product: {await response.get_json()}"
    body: dict[str, Any] = await response.get_json()
    return body


async def _create_tenant(client: Any, headers: dict[str, str], name: str) -> int:
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": name, "slug": f"{name.lower()}-{uuid.uuid4().hex[:8]}", "plan": "free"},
    )
    assert response.status_code == 201, await response.get_json()
    body: dict[str, Any] = await response.get_json()
    return int(body["id"])


async def _register_member(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    role: str = "member",
) -> dict[str, str]:
    """Register + login a second user, add them to tenant_id with `role`."""
    import jwt

    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Member"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert login.status_code == 200
    token = (await login.get_json())["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    user_id = int(payload["sub"])

    add = await client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=admin_headers,
        json={"user_id": user_id, "role": role},
    )
    assert add.status_code in (200, 201), await add.get_json()

    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_requires_authentication(client: Any, tenant_id: int) -> None:
    """No bearer token -> 401, not a 200 with an empty list."""
    response = await client.get(f"/api/v1/products/health?tenant_id={tenant_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_requires_tenant_id(client: Any, admin_headers: dict[str, str]) -> None:
    """No tenant claim and no ?tenant_id= -> 400, never a silent empty page."""
    response = await client.get("/api/v1/products/health", headers=admin_headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_forbidden_without_products_read_scope(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """A caller with no relationship to the tenant is refused, not emptied."""
    email = f"stranger-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Stranger"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    stranger_headers = {"Authorization": f"Bearer {(await login.get_json())['access_token']}"}

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=stranger_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_never_polled_connection_reports_unknown(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """No poller sweep has run yet -> "unknown", not a fabricated status."""
    conn = await _register_connection(client, admin_headers, tenant_id)

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200
    body = await response.get_json()

    entries = [p for p in body["products"] if p["connection_id"] == conn["id"]]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "unknown"
    assert entry["latency_ms"] is None
    assert entry["checked_at"] is None
    assert entry["error"] is None


@pytest.mark.asyncio
async def test_reflects_what_the_poller_cached(
    app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """The endpoint reads exactly what app.health_cache.set_health wrote.

    Written directly (not via a real sweep) so this test is about the
    ENDPOINT's read path, independent of the poller's own logic.
    """
    conn = await _register_connection(client, admin_headers, tenant_id)

    checked_at = datetime.now(UTC).isoformat()
    async with app.app_context():
        await set_health(
            int(conn["id"]),
            CachedHealth(
                status="degraded",
                latency_ms=250,
                checked_at=checked_at,
                error="upstream 503",
            ),
        )

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200
    body = await response.get_json()

    entries = [p for p in body["products"] if p["connection_id"] == conn["id"]]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "degraded"
    assert entry["latency_ms"] == 250
    assert entry["checked_at"] == checked_at
    assert entry["error"] == "upstream 503"


@pytest.mark.asyncio
async def test_never_triggers_a_live_poll(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement 3: "never triggers live polls".

    adapter.health() is monkeypatched to fail loudly if it is ever called;
    the endpoint must still answer 200 by reading the cache (or its
    "unknown" default) instead.
    """

    async def must_not_be_called(self: Any, ctx: Any) -> Any:
        raise AssertionError("GET /products/health must never call adapter.health() directly")

    monkeypatch.setattr(GenericAdapter, "health", must_not_be_called)

    await _register_connection(client, admin_headers, tenant_id)

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_only_returns_the_scoped_tenants_connections(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """A second tenant's connections never leak into the first's response."""
    other_tenant_id = await _create_tenant(client, admin_headers, "OtherTenant")

    own_conn = await _register_connection(client, admin_headers, tenant_id)
    await _register_connection(client, admin_headers, other_tenant_id)

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200
    body = await response.get_json()

    connection_ids = {p["connection_id"] for p in body["products"]}
    assert own_conn["id"] in connection_ids
    assert all(p["tenant_id"] == tenant_id for p in body["products"])


@pytest.mark.asyncio
async def test_include_children_expands_for_a_tenant_manager(
    app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """tenants:manage (owner/admin) + include_children=true sees the subtree."""
    child_id = await _create_tenant(client, admin_headers, "ChildTenant")

    from app.models import get_db

    async with app.app_context():
        db = get_db()
        await db(db.tenants.id == child_id).update(parent_tenant_id=tenant_id)
        await db.commit()

    child_conn = await _register_connection(client, admin_headers, child_id)

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}&include_children=true",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = await response.get_json()

    connection_ids = {p["connection_id"] for p in body["products"]}
    assert child_conn["id"] in connection_ids


@pytest.mark.asyncio
async def test_include_children_ignored_without_tenants_manage(
    app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """products:read alone (a plain member) must not expand into the subtree.

    Mirrors tenants.list_user_tenants' own include_children gate: seeing a
    descendant tenant's connections requires administering the PARENT, not
    merely reading products in it.
    """
    child_id = await _create_tenant(client, admin_headers, "ChildTenant2")

    from app.models import get_db

    async with app.app_context():
        db = get_db()
        await db(db.tenants.id == child_id).update(parent_tenant_id=tenant_id)
        await db.commit()

    child_conn = await _register_connection(client, admin_headers, child_id)

    member_headers = await _register_member(client, admin_headers, tenant_id, role="member")

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}&include_children=true",
        headers=member_headers,
    )
    assert response.status_code == 200
    body = await response.get_json()

    connection_ids = {p["connection_id"] for p in body["products"]}
    assert child_conn["id"] not in connection_ids


@pytest.mark.asyncio
async def test_response_entry_field_set_is_exact(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """The DTO's field set, no more and no less -- see security.md output validation."""
    await _register_connection(client, admin_headers, tenant_id)

    response = await client.get(
        f"/api/v1/products/health?tenant_id={tenant_id}", headers=admin_headers
    )
    body = await response.get_json()

    assert set(body.keys()) == {"products", "count"}
    assert body["count"] == len(body["products"])
    entry = body["products"][0]
    assert set(entry.keys()) == {
        "connection_id",
        "tenant_id",
        "product_type",
        "display_name",
        "status",
        "latency_ms",
        "checked_at",
        "error",
    }
