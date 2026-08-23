"""Cross-tenant authz-denial branches on individual product CRUD endpoints.

test_products_validation.py already covers request-validation and
not-found branches, and list_products' own denial (TestListProductsValidation
.test_non_member_is_denied). What it does not cover is the SAME denial
shape repeated on get/update/delete/test/health/schema -- each of those
functions has its own ``if denied: return denied`` after its own
``require_tenant_scope`` call, and coverage.py tracks each occurrence
independently, so covering it on one endpoint does not cover it on
another.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


async def _new_owner(client: Any) -> dict[str, str]:
    """Register a fresh user with no relationship to any existing tenant."""
    email = f"outsider-{uuid.uuid4().hex[:10]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Outsider"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert login.status_code == 200
    token = (await login.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _register_product(client: Any, headers: dict[str, str], tenant: int) -> int:
    """Create a real product connection under `tenant`; return its id."""
    response = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "tenant_id": tenant,
            "product_type": "nest",
            "display_name": "Cross Tenant Denial Target",
            "base_url": "https://nest.example.com",
            "auth_type": "bearer",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


class TestCrossTenantDenial:
    """A caller with no scope over the connection's tenant is denied, per-route."""

    @pytest.mark.asyncio
    async def test_get_product_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """GET /products/<id> denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.get(f"/api/v1/products/{product_id}", headers=outsider)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_product_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """PUT /products/<id> denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.put(
            f"/api/v1/products/{product_id}", headers=outsider, json={"display_name": "Hijack"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_product_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """DELETE /products/<id> denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.delete(f"/api/v1/products/{product_id}", headers=outsider)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_connection_test_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """POST /products/<id>/test denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.post(f"/api/v1/products/{product_id}/test", headers=outsider)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_health_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """GET /products/<id>/health denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.get(f"/api/v1/products/{product_id}/health", headers=outsider)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_tenant_mapping_conn_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """GET .../tenants/<tid>/map 404s for a nonexistent product id.

        Distinct from "mapping not found" (a real product, no mapping
        row), which test_products.py already covers.
        """
        response = await client.get(
            "/api/v1/products/999999999/tenants/1/map", headers=admin_headers
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Product connection not found"

    @pytest.mark.asyncio
    async def test_update_tenant_mapping_conn_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """PUT .../tenants/<tid>/map 404s for a nonexistent product id."""
        response = await client.put(
            "/api/v1/products/999999999/tenants/1/map",
            headers=admin_headers,
            json={"external_id": "ext-1"},
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Product connection not found"

    @pytest.mark.asyncio
    async def test_schema_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """GET /products/<id>/schema denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.get(f"/api/v1/products/{product_id}/schema", headers=outsider)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_tenant_mapping_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """GET .../tenants/<tid>/map denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.get(
            f"/api/v1/products/{product_id}/tenants/{tenant_id}/map", headers=outsider
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_tenant_mapping_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """PUT .../tenants/<tid>/map denies a caller outside the owning tenant."""
        product_id = await _register_product(client, admin_headers, tenant_id)
        outsider = await _new_owner(client)

        response = await client.put(
            f"/api/v1/products/{product_id}/tenants/{tenant_id}/map",
            headers=outsider,
            json={"external_id": "ext-1"},
        )
        assert response.status_code == 403
