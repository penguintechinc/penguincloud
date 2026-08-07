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
