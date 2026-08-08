"""Scope enforcement on the portal's own endpoints.

Phase 2B issued scopes at token time but nothing consumed them: every route
re-derived a role and compared it against a name list. These tests pin the
consuming half down, and in particular pin the property that made the
migration risky — **delegated administration must survive**.

The delegated-admin case is the one a naive "check the token's scope claim"
implementation silently breaks. An MSP admin's authority over a customer
tenant comes from an ancestor membership; they hold no ``tenant_members``
row in the customer tenant at all. A token minted for the MSP's own tenant
therefore says nothing about the customer's, so any gate that consults only
the claim either denies them (delegation broken, invisibly, for the exact
operator the hierarchy exists to serve) or is forced to enumerate every
descendant id into the token. Resolving the target tenant's scopes through
``resolve_scopes`` is what avoids both.
"""

from typing import Any
import uuid

import pytest
from quart import Quart


async def _register(client: Any, password: str = "testpass123") -> tuple[int, str]:
    """Register a fresh user; return (user_id, email)."""
    email = f"scope-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Scope User"},
    )
    assert response.status_code in (200, 201), await response.get_json()
    return int((await response.get_json())["user"]["id"]), email


async def _login(client: Any, email: str, password: str = "testpass123") -> str:
    """Log in and return the raw access token."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, await response.get_json()
    return str((await response.get_json())["access_token"])


async def _headers(client: Any, email: str) -> dict[str, str]:
    """Authorization headers for a freshly minted (unscoped) token."""
    return {"Authorization": f"Bearer {await _login(client, email)}"}


async def _create_tenant(client: Any, headers: dict[str, str], name: str) -> int:
    """Create a tenant owned by the caller; return its id."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": name,
            "slug": f"{name.lower()}-{uuid.uuid4().hex[:6]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _attach_child(app: Quart, child_id: int, parent_id: int) -> None:
    """Make child a descendant of parent, at the schema level.

    Deliberately writes ``parent_tenant_id`` directly rather than going
    through PUT /tenants/<id>/parent: that endpoint requires authority on
    BOTH sides of the move, which would force the MSP user to already hold a
    membership row in the child — destroying the very premise these tests
    exist to exercise (delegation *without* direct membership). The same
    approach is used in test_hierarchical_tenancy.py.
    """
    async with app.app_context():
        from app.models import get_db
        from app.tenancy import invalidate_tenant

        db = get_db()
        await db(db.tenants.id == child_id).update(parent_tenant_id=parent_id)
        await db.commit()
        await invalidate_tenant(child_id)
        await invalidate_tenant(parent_id)


@pytest.mark.usefixtures("app_context")
class TestDelegatedAdminThroughScopeGates:
    """An MSP admin reaches a descendant's data through scope-gated routes."""

    @pytest.mark.asyncio
    async def test_delegated_admin_manages_descendant_tenant(
        self, client: Any, app: Quart
    ) -> None:
        """Owner of a parent may manage a child they are not a member of.

        This is the acceptance property for the whole migration: the caller
        has NO tenant_members row in the child, so every gate they pass
        below was answered by delegation resolved from the hierarchy.
        """
        _, msp_email = await _register(client)
        msp_headers = await _headers(client, msp_email)

        _, customer_email = await _register(client)
        customer_headers = await _headers(client, customer_email)

        parent_id = await _create_tenant(client, msp_headers, "MspParent")
        child_id = await _create_tenant(client, customer_headers, "CustomerChild")

        await _attach_child(app, child_id, parent_id)

        async with app.app_context():
            from app.models import get_user_tenant_role
            from app.tenancy.authz import resolve_scopes
            from app.models import get_user_by_email

            msp_user = await get_user_by_email(msp_email)
            assert msp_user is not None
            msp_id = int(msp_user["id"])

            # The premise: no direct membership in the child whatsoever.
            assert await get_user_tenant_role(msp_id, child_id) is None

            # ...yet the resolved scope set for the child grants management.
            child_scopes = await resolve_scopes(msp_id, child_id)
            assert "tenants:manage" in child_scopes
            assert "members:manage" in child_scopes
            assert "products:manage" in child_scopes
            # Delegation confers management, never destruction or billing.
            assert "tenants:delete" not in child_scopes
            assert "tenants:billing" not in child_scopes

        # A @require_scope(tenant_arg=...) gated read of the descendant.
        detail = await client.get(f"/api/v1/tenants/{child_id}", headers=msp_headers)
        assert detail.status_code == 200, await detail.get_json()

        # A @require_scope(SCOPE_MEMBERS_READ) gated read.
        members = await client.get(
            f"/api/v1/tenants/{child_id}/members", headers=msp_headers
        )
        assert members.status_code == 200, await members.get_json()

        # A @require_scope(SCOPE_TENANTS_MANAGE) gated WRITE — the case that
        # would 403 under a token-claim-only implementation.
        updated = await client.put(
            f"/api/v1/tenants/{child_id}",
            headers=msp_headers,
            json={"display_name": "Managed By MSP"},
        )
        assert updated.status_code == 200, await updated.get_json()
        assert (await updated.get_json())["display_name"] == "Managed By MSP"

    @pytest.mark.asyncio
    async def test_delegated_admin_cannot_delete_or_bill_descendant(
        self, client: Any, app: Quart
    ) -> None:
        """Delegation stops short of destroying or re-pricing the tenant.

        tenants:delete and tenants:billing live in the owner bundle alone.
        Without this, "manage my customer" would quietly include "delete my
        customer" and "change what my customer pays".
        """
        _, msp_email = await _register(client)
        msp_headers = await _headers(client, msp_email)
        _, customer_email = await _register(client)
        customer_headers = await _headers(client, customer_email)

        parent_id = await _create_tenant(client, msp_headers, "MspBilling")
        child_id = await _create_tenant(client, customer_headers, "ChildBilling")
        await _attach_child(app, child_id, parent_id)

        # Delete is refused outright.
        deleted = await client.delete(
            f"/api/v1/tenants/{child_id}", headers=msp_headers
        )
        assert deleted.status_code == 403, await deleted.get_json()

        # An update naming `plan` succeeds as a request but must NOT move the
        # plan: the billing field is dropped, not the whole call rejected,
        # so a delegated admin can still rename what they manage.
        update = await client.put(
            f"/api/v1/tenants/{child_id}",
            headers=msp_headers,
            json={"display_name": "Renamed", "plan": "enterprise"},
        )
        assert update.status_code == 200, await update.get_json()
        body = await update.get_json()
        assert body["display_name"] == "Renamed"
        assert body["plan"] == "free", "delegated admin must not change plan"

    @pytest.mark.asyncio
    async def test_outsider_denied_by_scope_gate(self, client: Any) -> None:
        """A user with no path to the tenant gets 403, not 404.

        Authorization runs before existence disclosure, so an unauthorized
        caller cannot use the status code to probe the tenant id space.
        """
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "Private")

        _, outsider_email = await _register(client)
        outsider_headers = await _headers(client, outsider_email)

        for method, path in (
            ("get", f"/api/v1/tenants/{tenant_id}"),
            ("get", f"/api/v1/tenants/{tenant_id}/members"),
            ("get", f"/api/v1/tenants/{tenant_id}/usage"),
        ):
            response = await getattr(client, method)(path, headers=outsider_headers)
            assert response.status_code == 403, f"{method} {path}"
            assert (await response.get_json())["error"] == "insufficient_scope"

    @pytest.mark.asyncio
    async def test_member_denied_manage_scope_but_granted_read(
        self, client: Any
    ) -> None:
        """A plain member reads but does not manage — the scope split itself."""
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "SplitScope")

        member_user_id, member_email = await _register(client)
        added = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=owner_headers,
            json={"user_id": member_user_id, "role": "member"},
        )
        assert added.status_code == 201, await added.get_json()
        member_headers = await _headers(client, member_email)

        readable = await client.get(
            f"/api/v1/tenants/{tenant_id}", headers=member_headers
        )
        assert readable.status_code == 200, await readable.get_json()

        refused = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=member_headers,
            json={"display_name": "Nope"},
        )
        assert refused.status_code == 403
        body = await refused.get_json()
        assert body["error"] == "insufficient_scope"
        assert body["required_scope"] == ["tenants:manage"]


@pytest.mark.usefixtures("app_context")
class TestPlatformScopeGates:
    """User administration is gated on a scope, not on the role name."""

    @pytest.mark.asyncio
    async def test_platform_admin_token_carries_user_scopes(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """A platform admin can list users; the gate is users:read."""
        response = await client.get("/api/v1/users", headers=admin_headers)
        assert response.status_code == 200, await response.get_json()

    @pytest.mark.asyncio
    async def test_non_admin_refused_with_scope_error(self, client: Any) -> None:
        """A viewer is refused, and the refusal names the missing scope."""
        _, email = await _register(client)
        headers = await _headers(client, email)

        listed = await client.get("/api/v1/users", headers=headers)
        assert listed.status_code == 403
        body = await listed.get_json()
        assert body["error"] == "insufficient_scope"
        assert body["required_scope"] == ["users:read"]

        created = await client.post(
            "/api/v1/users",
            headers=headers,
            json={"email": "x@example.com", "password": "pw12345678"},
        )
        assert created.status_code == 403
        assert (await created.get_json())["required_scope"] == ["users:manage"]

    @pytest.mark.asyncio
    async def test_scope_gate_denies_before_the_view_body_runs(
        self, client: Any
    ) -> None:
        """An unauthorized caller cannot distinguish a missing resource.

        The decorator answers first, so a nonexistent tenant id and a real
        one the caller cannot reach are indistinguishable.
        """
        _, email = await _register(client)
        headers = await _headers(client, email)

        response = await client.get("/api/v1/tenants/999999", headers=headers)
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "insufficient_scope"


@pytest.mark.usefixtures("app_context")
class TestScopeHelpers:
    """Unit-level cover for the enforcement primitives themselves."""

    @pytest.mark.asyncio
    async def test_current_scopes_accepts_string_and_list_claims(
        self, app: Quart
    ) -> None:
        """RFC 6749's space-delimited form parses the same as the list form."""
        from app.authz import current_scopes
        from quart import g

        async with app.test_request_context("/", method="GET"):
            g.current_claims = {"scope": ["a:read", "b:write"]}
            assert current_scopes() == ["a:read", "b:write"]

            g.current_claims = {"scope": "a:read b:write"}
            assert current_scopes() == ["a:read", "b:write"]

            # A malformed claim yields nothing rather than something
            # accidentally truthy.
            g.current_claims = {"scope": 17}
            assert current_scopes() == []

            g.current_claims = {}
            assert current_scopes() == []

    @pytest.mark.asyncio
    async def test_rbac_enforcer_requires_all_scopes(self) -> None:
        """Multiple required scopes are AND, not OR."""
        from app.adapters.base import RBACEnforcer

        enforcer = RBACEnforcer(["a:read", "b:write"])
        assert enforcer.enforce(["a:read", "b:write", "c:x"]) is True
        assert enforcer.enforce(["a:read"]) is False
        assert enforcer.enforce([]) is False

    @pytest.mark.asyncio
    async def test_platform_scopes_unknown_role_grants_nothing(self) -> None:
        """An unrecognised role confers no authority — fail closed."""
        from app.tenancy.authz import platform_scopes

        assert platform_scopes("admin") == ["audit:read", "users:manage", "users:read"]
        assert platform_scopes("viewer") == []
        assert platform_scopes("wizard") == []
        assert platform_scopes(None) == []
        assert platform_scopes("") == []
