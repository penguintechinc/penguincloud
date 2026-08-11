"""The audit trail is tenant-private, on every route that serves it.

``GET /api/v1/users/audit-logs`` read ``db(db.audit_logs.id > 0)`` — every
row in the deployment — behind a scope check with no tenant predicate, and
with no licence gate either. Any caller holding ``audit:read`` in any tenant
read every other tenant's trail: who did what, to which resource, under
which user id. In a portal whose premise is provider/customer isolation that
is the worst-shaped disclosure available, because audit rows describe other
customers' activity by name.

The tests below put REAL ROWS FOR TWO TENANTS in the table and assert the
caller sees only their own. Asserting that a filter expression appears in
the source would pass against a filter that is present and wrong; only rows
that exist and are not returned prove isolation.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app import licensing
from penguin_dal.quart_ext import get_db
from quart import Quart

pytestmark = pytest.mark.usefixtures("enterprise_license")


async def _make_tenant(client: Any, headers: dict[str, str], name: str) -> int:
    """Create a tenant owned by the caller; return its id."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": name,
            "slug": f"{name}-{uuid.uuid4().hex[:8]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _seed_audit_row(app: Quart, tenant_id: int, marker: str) -> None:
    """Insert one audit row belonging to ``tenant_id``."""
    async with app.app_context():
        db = get_db()
        await db.audit_logs.async_insert(
            user_id=None,
            tenant_id=tenant_id,
            action_type="secret.action",
            resource_type="secret_resource",
            resource_id=marker,
            ip_address="203.0.113.9",
        )


class TestUsersAuditRouteIsTenantScoped:
    """Two tenants, real rows in each, one caller."""

    @pytest.mark.asyncio
    async def test_one_tenants_rows_are_invisible_to_another(
        self, client: Any, app: Quart, admin_headers: dict[str, str]
    ) -> None:
        """The caller sees their tenant's rows and nobody else's."""
        mine = await _make_tenant(client, admin_headers, "mine")
        theirs = await _make_tenant(client, admin_headers, "theirs")

        my_marker = f"mine-{uuid.uuid4().hex[:8]}"
        their_marker = f"theirs-{uuid.uuid4().hex[:8]}"
        await _seed_audit_row(app, mine, my_marker)
        await _seed_audit_row(app, theirs, their_marker)

        response = await client.get(
            f"/api/v1/users/audit-logs?tenant_id={mine}&limit=1000",
            headers=admin_headers,
        )

        assert response.status_code == 200
        returned = {row["resource_id"] for row in (await response.get_json())["logs"]}

        # Both halves matter. Without the first, a route returning nothing
        # at all would "pass" isolation; without the second, the leak is
        # not detected.
        assert my_marker in returned, "the caller's own audit rows must be visible"
        assert their_marker not in returned, (
            "another tenant's audit rows were returned — this route serves "
            "the whole deployment's trail"
        )

    @pytest.mark.asyncio
    async def test_the_other_tenants_rows_are_visible_to_its_own_owner(
        self, client: Any, app: Quart, admin_headers: dict[str, str]
    ) -> None:
        """Non-vacuity: the hidden rows really do exist and are readable.

        Without this, a filter that dropped everything for everyone would
        satisfy the isolation assertion above.
        """
        theirs = await _make_tenant(client, admin_headers, "theirs")
        their_marker = f"theirs-{uuid.uuid4().hex[:8]}"
        await _seed_audit_row(app, theirs, their_marker)

        response = await client.get(
            f"/api/v1/users/audit-logs?tenant_id={theirs}&limit=1000",
            headers=admin_headers,
        )

        assert response.status_code == 200
        returned = {row["resource_id"] for row in (await response.get_json())["logs"]}
        assert their_marker in returned

    @pytest.mark.asyncio
    async def test_a_caller_without_authority_over_the_tenant_is_refused(
        self, client: Any, app: Quart, admin_headers: dict[str, str]
    ) -> None:
        """Naming another tenant is not the same as being allowed to read it.

        The tenant now comes from the request, so the authority check over
        that tenant is what stops the parameter from becoming the leak the
        missing predicate used to be.
        """
        outsider = await _make_tenant(client, admin_headers, "outsider")

        # A second admin with no membership or delegated authority anywhere
        # near `outsider`.
        email = f"stranger-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-long-enough-password"},
        )
        assert register.status_code in (200, 201)
        stranger_id = (await register.get_json())["user"]["id"]
        async with app.app_context():
            from app.models import update_user

            await update_user(stranger_id, role="admin")
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "a-long-enough-password"},
        )
        stranger = {"Authorization": f"Bearer {(await login.get_json())['access_token']}"}

        response = await client.get(
            f"/api/v1/users/audit-logs?tenant_id={outsider}", headers=stranger
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_named_is_refused_rather_than_answered_globally(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """The unscoped call used to be the deployment-wide one."""
        response = await client.get("/api/v1/users/audit-logs", headers=admin_headers)

        assert response.status_code == 400
        assert "tenant_id" in (await response.get_json())["error"]


class TestUsersAuditRouteIsLicensed:
    """The third door onto the audit trail is gated like the other two."""

    @pytest.mark.asyncio
    async def test_an_unlicensed_deployment_is_refused(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without this gate, the Enterprise wall on /audit/logs is optional.

        A caller who wanted the trail on a Community licence simply called
        this route instead.
        """
        monkeypatch.setattr(licensing, "is_feature_entitled_blocking", lambda feature: False)
        monkeypatch.setattr(licensing, "resolve_tier_blocking", lambda: licensing.TIER_COMMUNITY)

        response = await client.get(
            f"/api/v1/users/audit-logs?tenant_id={tenant_id}", headers=admin_headers
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_not_entitled"
        assert body["feature"] == "audit_logs"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE
