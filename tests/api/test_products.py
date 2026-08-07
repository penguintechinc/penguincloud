"""Product connection API tests — credential masking on every egress path.

Regression coverage for the masking that `get_product_connection_by_id` and
`get_tenant_product_connections` lost during the Quart migration: both
returned `dict(row)` unmodified, so the stored api_key/api_secret ciphertext
was serialised straight into responses.
"""

from typing import Any

import pytest

PLAINTEXT_KEY = "sekrit-api-key-value"
PLAINTEXT_SECRET = "sekrit-api-secret-value"
MASK = "***"


async def _register_product(
    client: Any,
    headers: dict[str, str],
    tenant: int,
    **overrides: Any,
) -> dict[str, Any]:
    """Register a product connection carrying real credentials."""
    payload: dict[str, Any] = {
        "tenant_id": tenant,
        "product_type": "squawk",
        "display_name": "Masking Test Product",
        "base_url": "https://squawk.example.com",
        "auth_type": "bearer",
        "api_key": PLAINTEXT_KEY,
        "api_secret": PLAINTEXT_SECRET,
    }
    payload.update(overrides)
    response = await client.post("/api/v1/products", headers=headers, json=payload)
    assert (
        response.status_code == 201
    ), f"Failed to register product: {await response.get_json()}"
    body: dict[str, Any] = await response.get_json()
    return body


def _assert_masked(conn: dict[str, Any]) -> None:
    """Assert credentials are masked and no plaintext/ciphertext leaked.

    Checks the whole serialised record, not just the two known fields: a
    leak via a renamed or newly added column is exactly the case a
    field-specific assertion would miss.
    """
    assert conn["api_key"] == MASK
    assert conn["api_secret"] == MASK

    serialised = repr(conn)
    assert PLAINTEXT_KEY not in serialised
    assert PLAINTEXT_SECRET not in serialised
    # encrypt_value() output is Fernet — versioned, base64, always "gAAAAA"-prefixed.
    assert "gAAAAA" not in serialised


@pytest.mark.asyncio
async def test_register_product_response_masks_credentials(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """POST /products must not echo back the credentials it just stored."""
    conn = await _register_product(client, admin_headers, tenant_id)
    _assert_masked(conn)


@pytest.mark.asyncio
async def test_get_product_masks_credentials(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """GET /products/<id> masks api_key and api_secret."""
    created = await _register_product(client, admin_headers, tenant_id)

    response = await client.get(
        f"/api/v1/products/{created['id']}", headers=admin_headers
    )
    assert response.status_code == 200
    _assert_masked(await response.get_json())


@pytest.mark.asyncio
async def test_list_products_masks_credentials(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """GET /products masks credentials on every row in the collection."""
    await _register_product(client, admin_headers, tenant_id)

    response = await client.get(
        f"/api/v1/products?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["count"] >= 1
    for conn in body["products"]:
        _assert_masked(conn)


@pytest.mark.asyncio
async def test_update_product_response_masks_credentials(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """PUT /products/<id> returns the updated record with credentials masked."""
    created = await _register_product(client, admin_headers, tenant_id)

    response = await client.put(
        f"/api/v1/products/{created['id']}",
        headers=admin_headers,
        json={"api_key": "rotated-key-value", "display_name": "Renamed"},
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["display_name"] == "Renamed"
    assert body["api_key"] == MASK
    assert "rotated-key-value" not in repr(body)


@pytest.mark.asyncio
async def test_absent_credentials_are_empty_not_masked(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """A connection with no credentials reports "" — not a bogus mask.

    Masking an absent value would tell a client a credential exists when
    none does, which is what the pre-migration behaviour deliberately avoided.
    """
    created = await _register_product(
        client,
        admin_headers,
        tenant_id,
        auth_type="none",
        api_key="",
        api_secret="",
    )
    assert created["api_key"] == ""
    assert created["api_secret"] == ""


@pytest.mark.asyncio
async def test_health_check_records_status_and_timestamp(
    app: Any,
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /products/<id>/test persists the health result.

    update_product_health wrote `health_check_at`; the column is
    `last_health_check` (models_sqlalchemy.ProductConnection:142), so the
    UPDATE raised "Unconsumed column names" and no health check was ever
    recorded. The endpoint's own 200 did not reveal it — the write is a
    side effect, so this reads the row back.

    The adapter is stubbed so the test exercises persistence rather than
    making a real outbound HTTP call.
    """
    created = await _register_product(client, admin_headers, tenant_id)

    from app.adapters.base_adapter import ProductAdapter

    monkeypatch.setattr(
        ProductAdapter,
        "health_check",
        lambda self: {"status": "healthy", "status_code": 200, "response_time_ms": 7},
    )

    response = await client.post(
        f"/api/v1/products/{created['id']}/test", headers=admin_headers
    )
    assert response.status_code == 200
    assert (await response.get_json())["status"] == "healthy"

    async with app.app_context():
        from app.models import get_product_connection_by_id

        conn = await get_product_connection_by_id(created["id"])

    assert conn is not None
    assert conn["health_status"] == "healthy"
    assert conn["last_health_check"] is not None, "health check time not recorded"


@pytest.mark.asyncio
async def test_health_endpoint_reports_recorded_check(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /products/<id>/health surfaces what the test run recorded."""
    created = await _register_product(client, admin_headers, tenant_id)

    from app.adapters.base_adapter import ProductAdapter

    monkeypatch.setattr(
        ProductAdapter,
        "health_check",
        lambda self: {"status": "degraded", "status_code": 429},
    )
    await client.post(f"/api/v1/products/{created['id']}/test", headers=admin_headers)

    response = await client.get(
        f"/api/v1/products/{created['id']}/health", headers=admin_headers
    )
    assert response.status_code == 200

    body = await response.get_json()
    assert body["health_status"] == "degraded"
    assert body["last_health_check"] is not None


@pytest.mark.asyncio
async def test_raw_accessor_still_returns_ciphertext(
    app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """get_product_connection_raw stays the one path to stored ciphertext.

    The proxy and adapter paths decrypt these values to authenticate
    outbound calls, so masking must NOT be applied there.
    """
    created = await _register_product(client, admin_headers, tenant_id)

    async with app.app_context():
        from app.models import get_product_connection_raw

        raw = await get_product_connection_raw(created["id"])

    assert raw is not None
    assert raw["api_key"] not in (MASK, "")
    # Stored encrypted, so neither the mask nor the plaintext appears.
    assert raw["api_key"] != PLAINTEXT_KEY
    assert raw["api_secret"] != PLAINTEXT_SECRET


# Product Tenant Mapping Tests


@pytest.mark.asyncio
async def test_set_product_tenant_mapping_creates_new_mapping(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """POST /products/<id>/tenants/<id>/map creates a new mapping."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "my-gough-tenant-123"},
    )
    assert response.status_code == 201
    body = await response.get_json()
    assert body["connection_id"] == product_id
    assert body["tenant_id"] == tenant_id
    assert body["external_kind"] == "tenant_id"
    assert body["external_id"] == "my-gough-tenant-123"


@pytest.mark.asyncio
async def test_get_product_tenant_mapping_returns_existing(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """GET /products/<id>/tenants/<id>/map returns existing mapping."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    # Create mapping first
    await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "my-gough-tenant-123"},
    )

    # Retrieve it
    response = await client.get(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["external_id"] == "my-gough-tenant-123"


@pytest.mark.asyncio
async def test_update_product_tenant_mapping_updates_external_id(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """PUT /products/<id>/tenants/<id>/map updates external_id."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    # Create mapping
    await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "old-id"},
    )

    # Update it
    response = await client.put(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "new-id"},
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["external_id"] == "new-id"


@pytest.mark.asyncio
async def test_delete_product_tenant_mapping_removes_mapping(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """DELETE /products/<id>/tenants/<id>/map removes the mapping."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    # Create mapping
    await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "my-id"},
    )

    # Delete it
    response = await client.delete(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
    )
    assert response.status_code == 200

    # Verify it's gone
    response = await client.get(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_product_tenant_mapping_validates_external_kind_for_gough(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """Gough product type requires tenant_id external_kind."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "test-id"},
    )
    assert response.status_code == 201
    body = await response.get_json()
    assert body["external_kind"] == "tenant_id"


@pytest.mark.asyncio
async def test_product_tenant_mapping_validates_external_kind_for_waddleai(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """WaddleAI product type requires organization_id external_kind."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="waddleai"
    )
    product_id = created["id"]

    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "org-123"},
    )
    assert response.status_code == 201
    body = await response.get_json()
    assert body["external_kind"] == "organization_id"


@pytest.mark.asyncio
async def test_product_tenant_mapping_validates_external_kind_for_waddlebot(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """WaddleBot product type requires namespace external_kind."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="waddlebot"
    )
    product_id = created["id"]

    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "my-namespace"},
    )
    assert response.status_code == 201
    body = await response.get_json()
    assert body["external_kind"] == "namespace"


@pytest.mark.asyncio
async def test_product_tenant_mapping_rejects_unsupported_product_type(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """Product types without mapping support return 400."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="squawk"
    )
    product_id = created["id"]

    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "test-id"},
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert "unsupported for mapping" in body["error"]


@pytest.mark.asyncio
async def test_product_tenant_mapping_requires_admin_for_write(
    client: Any,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
    tenant_id: int,
) -> None:
    """Non-admin users cannot create/update/delete mappings."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    # Non-admin cannot create
    response = await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=auth_headers,
        json={"external_id": "test-id"},
    )
    assert response.status_code == 403

    # Create as admin for delete test
    await client.post(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
        json={"external_id": "test-id"},
    )

    # Non-admin cannot delete
    response = await client.delete(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_product_tenant_mapping_get_not_found_returns_404(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """GET nonexistent mapping returns 404."""
    created = await _register_product(
        client, admin_headers, tenant_id, product_type="gough"
    )
    product_id = created["id"]

    response = await client.get(
        f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
        headers=admin_headers,
    )
    assert response.status_code == 404
