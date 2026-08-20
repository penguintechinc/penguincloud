"""What the ten previously-unschema'd endpoints publish, field by field.

Ten routes had no documented 200/201 JSON response, so quart-schema emitted
no response schema for them: ``auth/login``, ``auth/me``, ``auth/refresh``,
``auth/logout``, ``dashboard/overview``, ``dashboard/health``,
``products`` (list), ``status``, ``audit/logs`` and ``users`` (list).
security.md's Output Validation is explicit about why that matters:

    a bug meant an endpoint that was only supposed to return a single string
    ended up returning the entire database object it came from ... Nothing
    crashed, no error, no signal anything was wrong.

There is a second consequence beyond the rule: the webui's generated
``ApiResponse<path, method>`` type falls back to ``unknown`` when no
response schema exists, and ``x satisfies unknown`` can never fail — so the
frontend's drift guard was vacuous on exactly these ten endpoints. Fixing
the response schemas here (``@validate_response`` + a typed DTO on each
route) is what makes that guard real; this module is the backend half.

Two layers, deliberately (mirrors test_audit_response_shape.py)
=================================================================
* A literal-field-name assertion on each DTO — fails if someone adds a
  field to the dataclass (e.g. accidentally re-adding ``id_token`` to
  ``LoginResponse``, or ``password_hash`` to ``MeResponse``).
* A live-endpoint assertion that the actual JSON response's key set equals
  the DTO's — fails if a route stops projecting through its DTO.

Auth is the sharp edge
=======================
``auth/login``, ``auth/refresh`` and ``auth/me`` return bearer credentials
and profile data on every call, unauthenticated or self-authenticated, so an
over-broad field here is the most costly leak in the service. Each DTO's
field set is asserted here as a literal list — see app/auth.py for the
per-field justification (why LoginResponse excludes id_token, why
RefreshResponse excludes user, why MeResponse is wider than the login user
summary).
"""

from __future__ import annotations

import uuid
from dataclasses import fields
from typing import Any

import pytest
from app.audit_view import AUDIT_RECORD_FIELDS
from app.auth import AuthenticatedUser, LoginResponse, LogoutResponse, MeResponse, RefreshResponse
from app.dashboard_api import (
    DashboardOverviewResponse,
    DashboardStats,
    HealthCounts,
    HealthMatrixEntry,
    HealthMatrixResponse,
    TenantSummary,
)
from app.hello import StatusResponse
from app.product_view import ProductConnection
from app.products import ProductsListResponse
from app.users import Pagination, UsersListResponse, UserSummary
from penguin_dal.quart_ext import get_db
from quart import Quart

PASSWORD = "responsetestpass123"


def _field_names(dto: type) -> set[str]:
    return {f.name for f in fields(dto)}


async def _register_only(client: Any, **overrides: Any) -> str:
    """Register a unique user; return its email. No login performed."""
    email: str = overrides.pop("email", f"resptest-{uuid.uuid4().hex[:8]}@example.com")
    payload = {"email": email, "password": PASSWORD, "full_name": "Response Test"}
    payload.update(overrides)
    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, await register.get_json()
    return email


async def _register_and_login(client: Any, **overrides: Any) -> tuple[dict[str, Any], Any]:
    """Register a unique user, log in, return (login body, response)."""
    email = overrides.pop("email", f"resptest-{uuid.uuid4().hex[:8]}@example.com")
    payload = {"email": email, "password": PASSWORD, "full_name": "Response Test"}
    payload.update(overrides)
    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, await register.get_json()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, await login.get_json()
    body: dict[str, Any] = await login.get_json()
    return body, login


async def _register_product(
    client: Any, headers: dict[str, str], tenant: int, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tenant_id": tenant,
        "product_type": "nest",
        "display_name": "Response Shape Test Product",
        "base_url": "https://nest.example.com",
        "auth_type": "bearer",
        "api_key": "irrelevant-key",
        "api_secret": "irrelevant-secret",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/products", headers=headers, json=payload)
    assert response.status_code == 201, await response.get_json()
    body: dict[str, Any] = await response.get_json()
    return body


class TestThePublishedFieldSetsArePinned:
    """Every DTO's fields, spelled out. Adding a field must fail here."""

    def test_authenticated_user(self) -> None:
        """Login's embedded user summary."""
        assert _field_names(AuthenticatedUser) == {"id", "email", "full_name", "role"}

    def test_login_response(self) -> None:
        """No id_token — see AuthenticatedUser docstring in app/auth.py."""
        assert _field_names(LoginResponse) == {
            "access_token",
            "refresh_token",
            "token_type",
            "expires_in",
            "user",
        }

    def test_refresh_response(self) -> None:
        """No user — a refresh is not a re-authentication."""
        assert _field_names(RefreshResponse) == {
            "access_token",
            "refresh_token",
            "token_type",
            "expires_in",
        }

    def test_logout_response(self) -> None:
        """Logout's DTO fields."""
        assert _field_names(LogoutResponse) == {"message", "tokens_revoked"}

    def test_me_response(self) -> None:
        """No password_hash, no MFA secret."""
        assert _field_names(MeResponse) == {
            "id",
            "email",
            "full_name",
            "role",
            "is_active",
            "created_at",
        }
        assert "password_hash" not in _field_names(MeResponse)

    def test_product_connection(self) -> None:
        """No metadata_json — same free-form hazard as audit's request_body."""
        assert _field_names(ProductConnection) == {
            "id",
            "tenant_id",
            "product_type",
            "display_name",
            "base_url",
            "api_key",
            "api_secret",
            "auth_type",
            "health_endpoint",
            "api_version",
            "is_active",
            "health_status",
            "discovered",
            "last_health_check",
            "created_at",
            "updated_at",
        }
        assert "metadata_json" not in _field_names(ProductConnection)

    def test_products_list_response(self) -> None:
        """GET /api/v1/products' envelope."""
        assert _field_names(ProductsListResponse) == {"products", "count"}

    def test_dashboard_overview_response(self) -> None:
        """The overview envelope and its nested DTOs."""
        assert _field_names(DashboardOverviewResponse) == {"tenant", "stats", "products"}
        assert _field_names(TenantSummary) == {"id", "name", "plan"}
        assert _field_names(DashboardStats) == {
            "total_products",
            "total_members",
            "health",
            "categories",
        }
        assert _field_names(HealthCounts) == {"healthy", "degraded", "unhealthy", "unknown"}

    def test_health_matrix_response(self) -> None:
        """dashboard/health's DTO fields."""
        assert _field_names(HealthMatrixResponse) == {"health", "count"}
        assert _field_names(HealthMatrixEntry) == {
            "id",
            "product_type",
            "display_name",
            "health_status",
            "last_health_check",
            "base_url",
        }

    def test_status_response(self) -> None:
        """The public, unauthenticated status endpoint's DTO fields."""
        assert _field_names(StatusResponse) == {"status", "service", "version", "timestamp"}

    def test_users_list_response(self) -> None:
        """The admin users listing's envelope and pagination DTO fields."""
        assert _field_names(UsersListResponse) == {"users", "pagination"}
        assert _field_names(Pagination) == {"page", "per_page", "total", "pages"}

    def test_user_summary(self) -> None:
        """No password_hash — see UserSummary docstring in app/users.py."""
        assert _field_names(UserSummary) == {
            "id",
            "email",
            "full_name",
            "role",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert "password_hash" not in _field_names(UserSummary)


@pytest.mark.asyncio
class TestEveryLiveResponseMatchesItsDto:
    """Live responses, asserted against the same field sets as above."""

    async def test_login(self, client: Any) -> None:
        """No id_token, no extra user fields, no password_hash anywhere."""
        body, _ = await _register_and_login(client)
        assert set(body) == _field_names(LoginResponse)
        assert set(body["user"]) == _field_names(AuthenticatedUser)
        assert "id_token" not in body
        assert "password_hash" not in str(body)

    async def test_refresh(self, client: Any) -> None:
        """No user field — a refresh is not a re-authentication."""
        login_body, _ = await _register_and_login(client)
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_body["refresh_token"]}
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(RefreshResponse)
        assert "user" not in body

    async def test_logout(self, client: Any, auth_headers: dict[str, str]) -> None:
        """Logout's field set."""
        response = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(LogoutResponse)

    async def test_me(self, client: Any, auth_headers: dict[str, str]) -> None:
        """No password_hash, no MFA secret, no extra row internals."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(MeResponse)
        assert "password_hash" not in body

    async def test_status(self, client: Any) -> None:
        """The unauthenticated status endpoint's field set."""
        response = await client.get("/api/v1/status")
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(StatusResponse)

    async def test_products_list(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """No metadata_json, credentials masked, on every connection row."""
        await _register_product(client, admin_headers, tenant_id)
        response = await client.get(
            f"/api/v1/products?tenant_id={tenant_id}", headers=admin_headers
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(ProductsListResponse)
        assert body["count"] >= 1
        for conn in body["products"]:
            assert set(conn) == _field_names(ProductConnection)
        assert "metadata_json" not in str(body)

    async def test_dashboard_overview(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The nested product connections use the same masked projection."""
        await _register_product(client, admin_headers, tenant_id)
        response = await client.get(
            f"/api/v1/dashboard/overview?tenant_id={tenant_id}", headers=admin_headers
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(DashboardOverviewResponse)
        assert set(body["tenant"]) == _field_names(TenantSummary)
        assert set(body["stats"]) == _field_names(DashboardStats)
        assert set(body["stats"]["health"]) == _field_names(HealthCounts)
        assert body["products"], "seeded connection not returned"
        for conn in body["products"]:
            assert set(conn) == _field_names(ProductConnection)

    async def test_dashboard_health(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """The hand-curated health matrix's field set."""
        await _register_product(client, admin_headers, tenant_id)
        response = await client.get(
            f"/api/v1/dashboard/health?tenant_id={tenant_id}", headers=admin_headers
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(HealthMatrixResponse)
        assert body["health"], "seeded connection not returned"
        for entry in body["health"]:
            assert set(entry) == _field_names(HealthMatrixEntry)

    async def test_users_list(self, client: Any, admin_headers: dict[str, str]) -> None:
        """No password_hash on any user row — the vacuous-empty-list trap fixed.

        list_users previously called db.users.select() -- not a valid
        penguin-dal query (AttributeError: Table 'users' has no column
        'select') -- which the function's own broad except silently turned
        into "no users", always, on every call. A body["users"] non-empty
        check alone would NOT have caught that: it is exactly as vacuous
        against an endpoint that always returns [] as it is against one
        that works, since the truthiness check tests the endpoint's own
        (broken) output rather than a known fact about what should be
        there. This asserts against KNOWN users registered in this test,
        by email -- an endpoint frozen at [] fails this deterministically,
        regardless of what other tests happened to insert first.
        """
        known_emails = {await _register_only(client) for _ in range(2)}

        response = await client.get("/api/v1/users?per_page=100", headers=admin_headers)
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == _field_names(UsersListResponse)
        assert set(body["pagination"]) == _field_names(Pagination)

        returned_emails = {user["email"] for user in body["users"]}
        missing = known_emails - returned_emails
        assert not missing, (
            f"users just registered are absent from the listing: {missing} "
            f"(returned {len(body['users'])} of {body['pagination']['total']} total)"
        )
        assert body["pagination"]["total"] >= len(known_emails)

        for user in body["users"]:
            assert set(user) == _field_names(UserSummary)
            assert "password_hash" not in user

    async def test_audit_logs_envelope(
        self,
        client: Any,
        app: Quart,
        admin_headers: dict[str, str],
        tenant_id: int,
        enterprise_license: None,
    ) -> None:
        """The outer envelope, pinned.

        Inner row coverage already lives in test_audit_response_shape.py
        (AUDIT_RECORD_FIELDS). That module never asserted the OUTER key set
        was exact, only that each row matched the published projection.
        """
        marker = f"resp-{uuid.uuid4().hex[:8]}"
        async with app.app_context():
            db = get_db()
            await db.audit_logs.async_insert(
                user_id=None,
                tenant_id=tenant_id,
                action_type="response.shape.test",
                resource_type="marker",
                resource_id=marker,
                ip_address="203.0.113.10",
            )

        response = await client.get(
            f"/api/v1/audit/logs?tenant_id={tenant_id}", headers=admin_headers
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert set(body) == {"logs", "total", "page", "per_page", "pages"}
        assert body["logs"], "seeded row not returned"
        for row in body["logs"]:
            assert set(row) == set(AUDIT_RECORD_FIELDS)
