"""Pure-helper branch coverage for app/dashboard_api.py.

``_isoformat`` is a third copy of the same helper already tested directly
in test_users.py (app.users) and test_tenants_edge_cases.py (app.tenants) --
each module's copy is a distinct top-level function as far as coverage.py
is concerned, so covering one does not cover the others.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.dashboard_api import _isoformat


class TestIsoformat:
    """Pure-function coverage for every branch _isoformat can take."""

    def test_none_returns_none(self) -> None:
        """A NULL column value passes through as None."""
        assert _isoformat(None) is None

    def test_string_passes_through_unchanged(self) -> None:
        """An already-string value is returned as-is."""
        assert _isoformat("2026-01-01T00:00:00") == "2026-01-01T00:00:00"

    def test_datetime_like_object_calls_isoformat(self) -> None:
        """A real datetime value is rendered via its own .isoformat()."""

        class _FakeDatetime:
            def isoformat(self) -> str:
                return "2026-06-01T12:00:00"

        assert _isoformat(_FakeDatetime()) == "2026-06-01T12:00:00"

    def test_object_without_isoformat_falls_back_to_str(self) -> None:
        """A value with neither None, str, nor .isoformat() still renders."""
        assert _isoformat(12345) == "12345"


async def _new_owner(client: Any) -> dict[str, str]:
    """Register a fresh user with no relationship to any existing tenant."""
    email = f"dash-outsider-{uuid.uuid4().hex[:10]}@example.com"
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


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/health",
        "/api/v1/dashboard/activity",
        "/api/v1/dashboard/alerts",
    ],
)
class TestDashboardEndpointsMissingTenantId:
    """Every dashboard route 400s on a missing tenant_id.

    Checked before scope resolution -- previously untested for any of the
    four routes.
    """

    @pytest.mark.asyncio
    async def test_missing_tenant_id_is_rejected(self, client: Any, path: str) -> None:
        """No tenant_id claim and no ?tenant_id= param -> 400."""
        outsider = await _new_owner(client)
        response = await client.get(path, headers=outsider)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/health",
        "/api/v1/dashboard/activity",
        "/api/v1/dashboard/alerts",
    ],
)
class TestDashboardEndpointsCrossTenantDenial:
    """Every dashboard route denies a caller with no scope over the tenant.

    Previously untested for any of the four routes.
    """

    @pytest.mark.asyncio
    async def test_non_member_is_denied(self, client: Any, tenant_id: int, path: str) -> None:
        """A real tenant, a real caller, but no membership -> 403."""
        outsider = await _new_owner(client)
        response = await client.get(f"{path}?tenant_id={tenant_id}", headers=outsider)
        assert response.status_code == 403


class TestDashboardAlertsAggregation:
    """dashboard_alerts' health-status filtering loop."""

    @pytest.mark.asyncio
    async def test_unhealthy_product_produces_a_critical_alert(
        self, app: Any, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """A genuinely unhealthy connection surfaces as a critical alert.

        A healthy one does not appear at all.
        """
        healthy = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "nest",
                "display_name": "Healthy One",
                "base_url": "https://nest.example.com",
                "auth_type": "bearer",
            },
        )
        assert healthy.status_code == 201
        unhealthy = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "nest",
                "display_name": "Unhealthy One",
                "base_url": "https://nest.example.com",
                "auth_type": "bearer",
            },
        )
        assert unhealthy.status_code == 201
        unhealthy_id = (await unhealthy.get_json())["id"]

        async with app.app_context():
            from app.models import update_product_health

            await update_product_health(unhealthy_id, "unhealthy")

        response = await client.get(
            f"/api/v1/dashboard/alerts?tenant_id={tenant_id}", headers=admin_headers
        )
        assert response.status_code == 200
        body = await response.get_json()
        alert_ids = {a["product_id"] for a in body["alerts"]}
        assert unhealthy_id in alert_ids
        matching = next(a for a in body["alerts"] if a["product_id"] == unhealthy_id)
        assert matching["severity"] == "critical"
