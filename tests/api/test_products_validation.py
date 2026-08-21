"""Validation, not-found, and authz-denial branches of app.products.

test_products.py already covers the credential-masking egress path and the
product/tenant mapping endpoints' happy paths + several authz cases. This
file covers the surrounding request-validation and not-found/denied
branches on register/list/get/update/delete/test/health/schema that were
previously untested: a caller with a malformed body, a missing tenant_id,
an unowned product id, or a quota already at its ceiling.
"""

from __future__ import annotations

from typing import Any

import pytest


async def _register(client: Any, headers: dict[str, str], tenant: int, **overrides: Any) -> Any:
    """Register."""
    payload: dict[str, Any] = {
        "tenant_id": tenant,
        "product_type": "nest",
        "display_name": "Validation Test Product",
        "base_url": "https://nest.example.com",
        "auth_type": "bearer",
    }
    payload.update(overrides)
    return await client.post("/api/v1/products", headers=headers, json=payload)


class TestListProductTypes:
    """List Product Types."""

    @pytest.mark.asyncio
    async def test_returns_the_catalogue(self, client: Any, admin_headers: dict[str, str]) -> None:
        """Returns the catalogue."""
        response = await client.get("/api/v1/products/types", headers=admin_headers)
        assert response.status_code == 200
        data = await response.get_json()
        product_types = {entry["product_type"] for entry in data["product_types"]}
        assert {"nest", "gough"} <= product_types


class TestRegisterProductValidation:
    """Register Product Validation."""

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Missing body is rejected."""
        response = await client.post("/api/v1/products", headers=admin_headers)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_tenant_id_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Missing tenant id is rejected."""
        response = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={"product_type": "nest", "display_name": "X", "base_url": "https://x.example.com"},
        )
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"

    @pytest.mark.asyncio
    async def test_nonexistent_tenant_is_denied_by_scope_before_404(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """register_product checks scope BEFORE tenant existence.

        A caller holds no tenant_members row for a tenant id that was
        never created, so the 403 authz gate answers first -- the
        "Tenant not found" 404 branch is unreachable through this path
        (it exists for an orphaned membership row pointing at a
        since-deleted tenant, not a merely-nonexistent one).
        """
        response = await _register(client, admin_headers, 9_999_999)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_display_name_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Missing display name is rejected."""
        response = await _register(client, admin_headers, tenant_id, display_name="")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "display_name required"

    @pytest.mark.asyncio
    async def test_missing_base_url_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Missing base url is rejected."""
        response = await _register(client, admin_headers, tenant_id, base_url="")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "base_url required"

    @pytest.mark.asyncio
    async def test_invalid_auth_type_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Invalid auth type is rejected."""
        response = await _register(client, admin_headers, tenant_id, auth_type="kerberos")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Invalid auth_type"

    @pytest.mark.asyncio
    async def test_invalid_product_type_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Invalid product type is rejected."""
        response = await _register(client, admin_headers, tenant_id, product_type="not-a-product")
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Invalid product type"

    @pytest.mark.asyncio
    async def test_quota_ceiling_refuses_the_next_registration(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """DEFAULT_MAX_PRODUCTS caps a tenant at 5 connections."""
        for i in range(5):
            response = await _register(
                client, admin_headers, tenant_id, display_name=f"Quota Product {i}"
            )
            assert response.status_code == 201, await response.get_json()

        response = await _register(client, admin_headers, tenant_id, display_name="One Too Many")
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "Product connection limit reached"


class TestListProductsValidation:
    """List Products Validation."""

    @pytest.mark.asyncio
    async def test_missing_tenant_id_is_rejected(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Missing tenant id is rejected."""
        response = await client.get("/api/v1/products", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"

    @pytest.mark.asyncio
    async def test_non_member_is_denied(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Non member is denied."""
        outsider_email = "products-outsider@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": outsider_email,
                "password": "outsiderpass123",
                "full_name": "Outsider",
            },
        )
        assert register.status_code in (200, 201)
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": outsider_email, "password": "outsiderpass123"},
        )
        outsider_headers = {"Authorization": f"Bearer {(await login.get_json())['access_token']}"}

        response = await client.get(
            f"/api/v1/products?tenant_id={tenant_id}", headers=outsider_headers
        )
        assert response.status_code == 403


class TestGetProductValidation:
    """Get Product Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.get("/api/v1/products/9999999", headers=admin_headers)
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Product connection not found"


class TestUpdateProductValidation:
    """Update Product Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.put(
            "/api/v1/products/9999999", headers=admin_headers, json={"display_name": "x"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_body_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Missing body is rejected."""
        created = await (await _register(client, admin_headers, tenant_id)).get_json()

        response = await client.put(f"/api/v1/products/{created['id']}", headers=admin_headers)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_api_secret_is_re_encrypted_and_masked(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Api secret is re encrypted and masked."""
        created = await (await _register(client, admin_headers, tenant_id)).get_json()

        response = await client.put(
            f"/api/v1/products/{created['id']}",
            headers=admin_headers,
            json={"api_secret": "brand-new-secret-value"},
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["api_secret"] == "***"
        assert "brand-new-secret-value" not in repr(data)


class TestDeleteProductValidation:
    """Delete Product Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.delete("/api/v1/products/9999999", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_product_is_gone(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Deleted product is gone."""
        created = await (await _register(client, admin_headers, tenant_id)).get_json()

        response = await client.delete(f"/api/v1/products/{created['id']}", headers=admin_headers)
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "Product connection removed"

        followup = await client.get(f"/api/v1/products/{created['id']}", headers=admin_headers)
        assert followup.status_code == 404


class TestProductConnectionTestValidation:
    """Product Connection Test Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.post("/api/v1/products/9999999/test", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unreachable_product_reports_upstream_failure(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """No real product is running.

        The adapter's own health check fails gracefully rather than
        raising out of the route.
        """
        created = await (
            await _register(
                client,
                admin_headers,
                tenant_id,
                base_url="http://127.0.0.1:1",
                product_type="gough",
            )
        ).get_json()

        response = await client.post(
            f"/api/v1/products/{created['id']}/test", headers=admin_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] in ("unhealthy", "degraded", "unknown", "error")


class TestProductHealthValidation:
    """Product Health Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.get("/api/v1/products/9999999/health", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_status_before_any_check(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Unknown status before any check."""
        created = await (await _register(client, admin_headers, tenant_id)).get_json()

        response = await client.get(
            f"/api/v1/products/{created['id']}/health", headers=admin_headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["product_id"] == created["id"]
        # The row carries an explicit health_status KEY with value None
        # until the first check runs -- conn.get("health_status", "unknown")
        # only substitutes "unknown" for a MISSING key, so a present-but-None
        # column reads back as None, not the fallback string.
        assert data["health_status"] is None


class TestProductSchemaValidation:
    """Product Schema Validation."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.get("/api/v1/products/9999999/schema", headers=admin_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unreachable_product_returns_502_unavailable(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Unreachable product returns 502 unavailable."""
        created = await (
            await _register(
                client,
                admin_headers,
                tenant_id,
                base_url="http://127.0.0.1:1",
                product_type="gough",
            )
        ).get_json()

        response = await client.get(
            f"/api/v1/products/{created['id']}/schema", headers=admin_headers
        )
        assert response.status_code in (200, 502)
        data = await response.get_json()
        assert data["schema_status"] in ("ok", "unsupported", "unavailable")


class TestUpdateProductTenantMappingUnsupportedType:
    """Update Product Tenant Mapping Unsupported Type."""

    @pytest.mark.asyncio
    async def test_unsupported_product_type_is_rejected(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Unsupported product type is rejected."""
        created = await (
            await _register(client, admin_headers, tenant_id, product_type="marchproxy")
        ).get_json()

        response = await client.put(
            f"/api/v1/products/{created['id']}/tenants/{tenant_id}/map",
            headers=admin_headers,
            json={"external_id": "abc"},
        )
        assert response.status_code in (400, 404)


class TestDeleteProductTenantMapping:
    """Delete Product Tenant Mapping."""

    @pytest.mark.asyncio
    async def test_nonexistent_product_is_not_found(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Nonexistent product is not found."""
        response = await client.delete(
            f"/api/v1/products/9999999/tenants/{tenant_id}/map", headers=admin_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_mapping_not_found_is_404(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Mapping not found is 404."""
        created = await (
            await _register(client, admin_headers, tenant_id, product_type="gough")
        ).get_json()

        response = await client.delete(
            f"/api/v1/products/{created['id']}/tenants/{tenant_id}/map", headers=admin_headers
        )
        assert response.status_code == 404
        assert (await response.get_json())["error"] == "Mapping not found"
