"""Hierarchy construction, delegated authority, middleware order, and DTOs.

Covers the efficacy gap the audit flagged: before this, nothing in the API
could construct a parent/child relationship at all (tests had to UPDATE
``parent_tenant_id`` through the DAL by hand), and delegated authority
stopped working the moment a caller left the switch endpoint.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt
import pytest
from quart import Quart


async def _new_user(client: Any) -> tuple[dict[str, str], int]:
    """Register and log in a fresh user; return (auth headers, user id)."""
    email = f"h-{uuid.uuid4().hex[:10]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "H User"},
    )
    assert register.status_code in (200, 201), await register.get_json()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    user_id = int(jwt.decode(token, options={"verify_signature": False})["sub"])
    return {"Authorization": f"Bearer {token}"}, user_id


async def _create_tenant(
    client: Any,
    headers: dict[str, str],
    name: str,
    parent_tenant_id: int | None = None,
    kind: str = "customer",
) -> int:
    """Create a tenant through the API; return its id."""
    body: dict[str, Any] = {
        "name": name,
        "slug": f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        "plan": "free",
        "kind": kind,
    }
    if parent_tenant_id is not None:
        body["parent_tenant_id"] = parent_tenant_id

    response = await client.post("/api/v1/tenants", headers=headers, json=body)
    payload = await response.get_json()
    assert response.status_code == 201, payload
    return int(payload["id"])


async def _add_member(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: int,
    user_id: int,
    role: str,
) -> None:
    """Add a user to a tenant with an explicit role."""
    response = await client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=admin_headers,
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201, await response.get_json()


@pytest.mark.usefixtures("app_context")
class TestHierarchyConstruction:
    """I4: the API can build and reshape a tenant tree."""

    @pytest.mark.asyncio
    async def test_create_tenant_with_parent_sets_depth_and_lineage(
        self, client: Any
    ) -> None:
        """A tenant created under a parent records depth = parent.depth + 1."""
        headers, _ = await _new_user(client)

        provider_id = await _create_tenant(client, headers, "Prov", kind="provider")
        customer_id = await _create_tenant(
            client, headers, "Cust", parent_tenant_id=provider_id
        )
        grandchild_id = await _create_tenant(
            client, headers, "Grand", parent_tenant_id=customer_id
        )

        for tenant_id, expected_depth, expected_parent in (
            (provider_id, 0, None),
            (customer_id, 1, provider_id),
            (grandchild_id, 2, customer_id),
        ):
            response = await client.get(
                f"/api/v1/tenants/{tenant_id}", headers=headers
            )
            assert response.status_code == 200
            body = await response.get_json()
            assert body["depth"] == expected_depth
            assert body["parent_tenant_id"] == expected_parent

    @pytest.mark.asyncio
    async def test_create_tenant_rejects_unknown_parent(self, client: Any) -> None:
        """A parent that does not exist is a 404, not a silent root tenant."""
        headers, _ = await _new_user(client)

        response = await client.post(
            "/api/v1/tenants",
            headers=headers,
            json={
                "name": "Orphan",
                "slug": f"orphan-{uuid.uuid4().hex[:6]}",
                "parent_tenant_id": 987_654,
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_tenant_rejects_parent_without_admin(
        self, client: Any
    ) -> None:
        """Parenting under someone else's tenant requires authority in it."""
        owner_headers, _ = await _new_user(client)
        outsider_headers, _ = await _new_user(client)

        provider_id = await _create_tenant(client, owner_headers, "Prov")

        response = await client.post(
            "/api/v1/tenants",
            headers=outsider_headers,
            json={
                "name": "Sneaky",
                "slug": f"sneaky-{uuid.uuid4().hex[:6]}",
                "parent_tenant_id": provider_id,
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reparent_rejects_cycle(self, client: Any) -> None:
        """A tenant may not be moved beneath its own descendant."""
        headers, _ = await _new_user(client)

        root_id = await _create_tenant(client, headers, "Root")
        child_id = await _create_tenant(
            client, headers, "Child", parent_tenant_id=root_id
        )

        response = await client.put(
            f"/api/v1/tenants/{root_id}/parent",
            headers=headers,
            json={"parent_tenant_id": child_id},
        )
        assert response.status_code == 400
        assert "cycle" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_reparent_rejects_self_as_parent(self, client: Any) -> None:
        """The degenerate one-node cycle is rejected too."""
        headers, _ = await _new_user(client)
        tenant_id = await _create_tenant(client, headers, "Solo")

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}/parent",
            headers=headers,
            json={"parent_tenant_id": tenant_id},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_reparent_moves_subtree_and_updates_depth(
        self, client: Any
    ) -> None:
        """Moving a node rewrites depth for everything beneath it."""
        headers, _ = await _new_user(client)

        root_a = await _create_tenant(client, headers, "RootA", kind="provider")
        root_b = await _create_tenant(client, headers, "RootB", kind="provider")
        mid = await _create_tenant(client, headers, "Mid", parent_tenant_id=root_a)
        leaf = await _create_tenant(client, headers, "Leaf", parent_tenant_id=mid)

        # Deepen: RootA -> RootB -> Mid -> Leaf
        response = await client.put(
            f"/api/v1/tenants/{mid}/parent",
            headers=headers,
            json={"parent_tenant_id": root_b},
        )
        assert response.status_code == 200, await response.get_json()

        mid_body = await (
            await client.get(f"/api/v1/tenants/{mid}", headers=headers)
        ).get_json()
        leaf_body = await (
            await client.get(f"/api/v1/tenants/{leaf}", headers=headers)
        ).get_json()

        assert mid_body["parent_tenant_id"] == root_b
        assert mid_body["depth"] == 1
        # The leaf never moved explicitly; its depth must still track the tree.
        assert leaf_body["depth"] == 2

    @pytest.mark.asyncio
    async def test_reparent_to_root_detaches(self, client: Any) -> None:
        """Passing a null parent promotes the tenant back to a root."""
        headers, _ = await _new_user(client)
        root_id = await _create_tenant(client, headers, "Root")
        child_id = await _create_tenant(
            client, headers, "Child", parent_tenant_id=root_id
        )

        response = await client.put(
            f"/api/v1/tenants/{child_id}/parent",
            headers=headers,
            json={"parent_tenant_id": None},
        )
        assert response.status_code == 200

        body = await (
            await client.get(f"/api/v1/tenants/{child_id}", headers=headers)
        ).get_json()
        assert body["parent_tenant_id"] is None
        assert body["depth"] == 0


@pytest.mark.usefixtures("app_context")
class TestReparentOriginAuthority:
    """A move must be authorized at the ORIGIN, not only the destination."""

    @pytest.mark.asyncio
    async def test_mid_tier_admin_cannot_detach_subtree_from_provider(
        self, client: Any
    ) -> None:
        """Admin on the moved node alone cannot sever the provider above it.

        Detaching to a root passes `parent_tenant_id: null`, which has no
        destination to validate — so with only the destination checked, this
        was entirely ungated and a mid-tier admin could cut the provider out
        of their own customer tree.
        """
        provider_headers, _ = await _new_user(client)
        mid_admin_headers, mid_admin_id = await _new_user(client)

        provider_id = await _create_tenant(
            client, provider_headers, "Prov", kind="provider"
        )
        mid_id = await _create_tenant(
            client, provider_headers, "Mid", parent_tenant_id=provider_id
        )
        await _create_tenant(client, provider_headers, "Leaf", parent_tenant_id=mid_id)

        # Admin on the mid tier ONLY.
        await _add_member(client, provider_headers, mid_id, mid_admin_id, "admin")

        detach = await client.put(
            f"/api/v1/tenants/{mid_id}/parent",
            headers=mid_admin_headers,
            json={"parent_tenant_id": None},
        )
        assert detach.status_code == 403, await detach.get_json()

        # The tree is unchanged.
        still = await client.get(
            f"/api/v1/tenants/{mid_id}", headers=provider_headers
        )
        assert (await still.get_json())["parent_tenant_id"] == provider_id

    @pytest.mark.asyncio
    async def test_provider_owner_can_detach_subtree(self, client: Any) -> None:
        """Authority in the current parent is what makes a detach legitimate."""
        provider_headers, _ = await _new_user(client)

        provider_id = await _create_tenant(
            client, provider_headers, "Prov", kind="provider"
        )
        mid_id = await _create_tenant(
            client, provider_headers, "Mid", parent_tenant_id=provider_id
        )

        detach = await client.put(
            f"/api/v1/tenants/{mid_id}/parent",
            headers=provider_headers,
            json={"parent_tenant_id": None},
        )
        assert detach.status_code == 200, await detach.get_json()

        body = await detach.get_json()
        assert body["parent_tenant_id"] is None
        assert body["depth"] == 0

    @pytest.mark.asyncio
    async def test_move_between_providers_requires_authority_in_both(
        self, client: Any
    ) -> None:
        """Origin authority and destination authority are both mandatory."""
        alice_headers, alice_id = await _new_user(client)
        bob_headers, bob_id = await _new_user(client)

        provider_a = await _create_tenant(
            client, alice_headers, "ProvA", kind="provider"
        )
        provider_b = await _create_tenant(
            client, bob_headers, "ProvB", kind="provider"
        )
        child = await _create_tenant(
            client, alice_headers, "Child", parent_tenant_id=provider_a
        )

        # Alice owns the origin but has no authority in the destination.
        alice_move = await client.put(
            f"/api/v1/tenants/{child}/parent",
            headers=alice_headers,
            json={"parent_tenant_id": provider_b},
        )
        assert alice_move.status_code == 403

        # Bob owns the destination but has no authority over the child or
        # its current parent.
        bob_move = await client.put(
            f"/api/v1/tenants/{child}/parent",
            headers=bob_headers,
            json={"parent_tenant_id": provider_b},
        )
        assert bob_move.status_code == 403

        # Grant Alice admin in the destination: now she holds both sides.
        await _add_member(client, bob_headers, provider_b, alice_id, "admin")
        both = await client.put(
            f"/api/v1/tenants/{child}/parent",
            headers=alice_headers,
            json={"parent_tenant_id": provider_b},
        )
        assert both.status_code == 200, await both.get_json()
        assert (await both.get_json())["parent_tenant_id"] == provider_b

    @pytest.mark.asyncio
    async def test_root_tenant_has_no_origin_to_guard(self, client: Any) -> None:
        """A tenant with no parent can be parented without an origin check."""
        owner_headers, _ = await _new_user(client)
        root = await _create_tenant(client, owner_headers, "Root")
        destination = await _create_tenant(
            client, owner_headers, "Dest", kind="provider"
        )

        response = await client.put(
            f"/api/v1/tenants/{root}/parent",
            headers=owner_headers,
            json={"parent_tenant_id": destination},
        )
        assert response.status_code == 200, await response.get_json()


@pytest.mark.usefixtures("app_context")
class TestEffectiveRoleResolution:
    """Pin resolve_effective_role's precedence so it stays deliberate."""

    @pytest.mark.asyncio
    async def test_direct_role_wins_even_when_weaker_than_delegated(
        self, client: Any, app: Quart
    ) -> None:
        """A direct membership beats inherited admin, even a weaker one.

        Someone who administers a provider AND is enrolled as a plain
        `viewer` in one of its customers resolves to `viewer` there, not
        admin. Current, intended behaviour: the explicit local grant is a
        deliberate statement about that tenant and overrides what the
        hierarchy would otherwise confer. Pinned so a future change to the
        precedence order has to be a decision rather than an accident.
        """
        from app.tenancy import resolve_effective_role

        owner_headers, _ = await _new_user(client)
        delegate_headers, delegate_id = await _new_user(client)

        provider_id = await _create_tenant(
            client, owner_headers, "Prov", kind="provider"
        )
        customer_id = await _create_tenant(
            client, owner_headers, "Cust", parent_tenant_id=provider_id
        )

        await _add_member(client, owner_headers, provider_id, delegate_id, "admin")

        async with app.app_context():
            # With no local row, the hierarchy confers admin.
            assert (
                await resolve_effective_role(delegate_id, customer_id)
                == "delegated_admin"
            )

        await _add_member(client, owner_headers, customer_id, delegate_id, "viewer")

        async with app.app_context():
            assert await resolve_effective_role(delegate_id, customer_id) == "viewer"

        # And the endpoint honours it: a viewer cannot manage the tenant.
        blocked = await client.put(
            f"/api/v1/tenants/{customer_id}",
            headers=delegate_headers,
            json={"display_name": "nope"},
        )
        assert blocked.status_code == 403


@pytest.mark.usefixtures("app_context")
class TestDeleteDoesNotLeakTenantExistence:
    """Cheap adjacent: align DELETE with switch/GET authz-before-existence."""

    @pytest.mark.asyncio
    async def test_unknown_and_unowned_tenants_are_indistinguishable(
        self, client: Any
    ) -> None:
        caller_headers, _ = await _new_user(client)
        other_headers, _ = await _new_user(client)

        real_but_unowned = await _create_tenant(client, other_headers, "Theirs")

        unknown = await client.delete(
            "/api/v1/tenants/987654", headers=caller_headers
        )
        existing = await client.delete(
            f"/api/v1/tenants/{real_but_unowned}", headers=caller_headers
        )

        assert unknown.status_code == 403
        assert existing.status_code == 403
        assert await unknown.get_json() == await existing.get_json()


@pytest.mark.usefixtures("app_context")
class TestCacheInvalidation:
    """C1/I9: a structural change must not leave a stale subtree set."""

    @pytest.mark.asyncio
    async def test_moving_a_subtree_clears_the_stale_descendant_set(
        self, client: Any, app: Quart
    ) -> None:
        """Build a 3-level tree, move a subtree, assert the stale set is gone.

        The named acceptance test for the invalidation defect: before this,
        invalidate_subtree/invalidate_ancestors had zero call sites and the
        local cache had no TTL, so the old parent kept reporting the moved
        subtree as its own descendants indefinitely.
        """
        from app.tenancy import get_descendants

        headers, _ = await _new_user(client)

        root_a = await _create_tenant(client, headers, "OldRoot", kind="provider")
        root_b = await _create_tenant(client, headers, "NewRoot", kind="provider")
        mid = await _create_tenant(client, headers, "Mid", parent_tenant_id=root_a)
        leaf = await _create_tenant(client, headers, "Leaf", parent_tenant_id=mid)

        # Warm the cache: root_a owns the whole subtree.
        async with app.app_context():
            assert await get_descendants(root_a) == {mid, leaf}
            assert await get_descendants(root_b) == set()

        response = await client.put(
            f"/api/v1/tenants/{mid}/parent",
            headers=headers,
            json={"parent_tenant_id": root_b},
        )
        assert response.status_code == 200, await response.get_json()

        async with app.app_context():
            # The stale set must be gone, not merely superseded elsewhere.
            assert await get_descendants(root_a) == set()
            assert await get_descendants(root_b) == {mid, leaf}

    @pytest.mark.asyncio
    async def test_creating_a_child_clears_the_parents_cached_set(
        self, client: Any, app: Quart
    ) -> None:
        """A newly created child appears in an already-warmed parent set."""
        from app.tenancy import get_descendants

        headers, _ = await _new_user(client)
        root_id = await _create_tenant(client, headers, "Root", kind="provider")

        async with app.app_context():
            assert await get_descendants(root_id) == set()

        child_id = await _create_tenant(
            client, headers, "Child", parent_tenant_id=root_id
        )

        async with app.app_context():
            assert await get_descendants(root_id) == {child_id}


@pytest.mark.usefixtures("app_context")
class TestDelegatedAuthority:
    """I2/I3: delegated admin is real past the switch endpoint."""

    @pytest.mark.asyncio
    async def test_switch_token_carries_resolved_scopes(self, client: Any) -> None:
        """Scopes are resolved at issue time and land in the token."""
        headers, _ = await _new_user(client)
        provider_id = await _create_tenant(client, headers, "Prov", kind="provider")
        await _create_tenant(client, headers, "Cust", parent_tenant_id=provider_id)

        response = await client.post(
            f"/api/v1/tenants/{provider_id}/switch", headers=headers
        )
        assert response.status_code == 200
        body = await response.get_json()

        payload = jwt.decode(
            body["access_token"], options={"verify_signature": False}
        )
        assert payload["scope"] == body["scope"]
        assert "tenants:manage" in payload["scope"]
        assert "products:manage" in payload["scope"]
        # Owner of a tenant that HAS descendants gets the delegation scope,
        # and it names the capability -- never the descendant id list.
        assert "tenants:manage:descendants" in payload["scope"]
        assert not any(str(provider_id) in s for s in payload["scope"])

    @pytest.mark.asyncio
    async def test_member_scopes_exclude_management(self, client: Any) -> None:
        """A plain member's resolved scopes are read-only."""
        owner_headers, _ = await _new_user(client)
        member_headers, member_id = await _new_user(client)

        tenant_id = await _create_tenant(client, owner_headers, "T")
        await _add_member(client, owner_headers, tenant_id, member_id, "member")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=member_headers
        )
        assert response.status_code == 200
        scopes = (await response.get_json())["scope"]

        assert "tenants:read" in scopes
        assert "tenants:manage" not in scopes
        assert "products:manage" not in scopes

    @pytest.mark.asyncio
    async def test_delegated_admin_can_manage_descendant_after_switch(
        self, client: Any
    ) -> None:
        """An ancestor admin can operate on a descendant via normal routes.

        This is the efficacy check: switching used to be the ONLY place
        delegated authority was honoured, so a provider admin could switch
        into a customer tenant and then be refused by every endpoint there.
        """
        owner_headers, _ = await _new_user(client)
        delegate_headers, delegate_id = await _new_user(client)
        subject_headers, subject_id = await _new_user(client)

        provider_id = await _create_tenant(
            client, owner_headers, "Prov", kind="provider"
        )
        customer_id = await _create_tenant(
            client, owner_headers, "Cust", parent_tenant_id=provider_id
        )

        # The delegate administers the PROVIDER only -- never enrolled in the
        # customer tenant.
        await _add_member(client, owner_headers, provider_id, delegate_id, "admin")

        members = await client.get(
            f"/api/v1/tenants/{customer_id}/members", headers=owner_headers
        )
        member_ids = {m["user_id"] for m in (await members.get_json())["members"]}
        assert delegate_id not in member_ids

        # Switch into the descendant.
        switch = await client.post(
            f"/api/v1/tenants/{customer_id}/switch", headers=delegate_headers
        )
        assert switch.status_code == 200, await switch.get_json()
        switched = {
            "Authorization": f"Bearer {(await switch.get_json())['access_token']}"
        }

        # ... and then actually operate on that tenant's data.
        read = await client.get(
            f"/api/v1/tenants/{customer_id}", headers=switched
        )
        assert read.status_code == 200, await read.get_json()
        assert (await read.get_json())["user_role"] == "delegated_admin"

        update = await client.put(
            f"/api/v1/tenants/{customer_id}",
            headers=switched,
            json={"display_name": "Managed By MSP"},
        )
        assert update.status_code == 200, await update.get_json()
        assert (await update.get_json())["display_name"] == "Managed By MSP"

        add = await client.post(
            f"/api/v1/tenants/{customer_id}/members",
            headers=switched,
            json={"user_id": subject_id, "role": "viewer"},
        )
        assert add.status_code == 201, await add.get_json()

    @pytest.mark.asyncio
    async def test_ancestor_member_gets_no_delegated_authority(
        self, client: Any
    ) -> None:
        """Membership in an ancestor is not admin over its descendants.

        The admin-vs-member boundary, proven with a real MEMBER of the
        ancestor rather than a total outsider -- an outsider would be
        rejected by the membership check and prove nothing about the role
        gate.
        """
        owner_headers, _ = await _new_user(client)
        member_headers, member_id = await _new_user(client)

        provider_id = await _create_tenant(
            client, owner_headers, "Prov", kind="provider"
        )
        customer_id = await _create_tenant(
            client, owner_headers, "Cust", parent_tenant_id=provider_id
        )
        await _add_member(client, owner_headers, provider_id, member_id, "member")

        switch = await client.post(
            f"/api/v1/tenants/{customer_id}/switch", headers=member_headers
        )
        assert switch.status_code == 403

        read = await client.get(
            f"/api/v1/tenants/{customer_id}", headers=member_headers
        )
        assert read.status_code == 403


@pytest.mark.usefixtures("app_context")
class TestSwitchDoesNotLeakTenantExistence:
    """Minor: authorize before the existence check."""

    @pytest.mark.asyncio
    async def test_unknown_and_unreachable_tenants_are_indistinguishable(
        self, client: Any
    ) -> None:
        """403 for both, so the path parameter is not an existence oracle."""
        caller_headers, _ = await _new_user(client)
        other_headers, _ = await _new_user(client)

        real_but_unreachable = await _create_tenant(client, other_headers, "Theirs")

        unknown = await client.post(
            "/api/v1/tenants/987654/switch", headers=caller_headers
        )
        existing = await client.post(
            f"/api/v1/tenants/{real_but_unreachable}/switch",
            headers=caller_headers,
        )

        assert unknown.status_code == 403
        assert existing.status_code == 403
        assert await unknown.get_json() == await existing.get_json()


@pytest.mark.usefixtures("app_context")
class TestTenancyMiddlewareOrdering:
    """I1: tenancy resolves before the view's own authorization logic."""

    @pytest.mark.asyncio
    async def test_missing_tenant_claim_is_403_before_the_view_runs(
        self, app: Quart
    ) -> None:
        """No tenant claim short-circuits with 403; the view never executes."""
        from quart import g

        from app.tenancy import tenancy_aware

        ran = {"view": False}

        @tenancy_aware
        async def _view() -> tuple[dict[str, str], int]:  # pragma: no cover
            ran["view"] = True
            return {"ok": "yes"}, 200

        async with app.test_request_context("/", method="GET"):
            g.current_claims = {"sub": "1"}  # authenticated, but no tenant
            body, status = await _view()

        assert status == 403
        assert ran["view"] is False

    @pytest.mark.asyncio
    async def test_unknown_tenant_claim_is_403_before_the_view_runs(
        self, app: Quart
    ) -> None:
        """A tenant claim naming no row is rejected before any scope logic."""
        from quart import g

        from app.tenancy import tenancy_aware

        ran = {"view": False}

        @tenancy_aware
        async def _view() -> tuple[dict[str, str], int]:  # pragma: no cover
            ran["view"] = True
            return {"ok": "yes"}, 200

        async with app.app_context():
            async with app.test_request_context("/", method="GET"):
                g.current_claims = {"sub": "1", "tenant": "987654"}
                body, status = await _view()

        assert status == 403
        assert ran["view"] is False

    @pytest.mark.asyncio
    async def test_scoped_token_attaches_hierarchy_context(
        self, client: Any, app: Quart
    ) -> None:
        """A real tenant claim yields a context carrying the subtree."""
        from quart import g

        from app.tenancy import tenancy_aware

        headers, _ = await _new_user(client)
        provider_id = await _create_tenant(client, headers, "Prov", kind="provider")
        customer_id = await _create_tenant(
            client, headers, "Cust", parent_tenant_id=provider_id
        )

        seen: dict[str, Any] = {}

        @tenancy_aware
        async def _view() -> tuple[dict[str, str], int]:
            from app.tenancy import get_tenancy_context

            seen["context"] = get_tenancy_context()
            return {"ok": "yes"}, 200

        async with app.app_context():
            async with app.test_request_context("/", method="GET"):
                g.current_claims = {"sub": "1", "tenant": str(provider_id)}
                _, status = await _view()

        assert status == 200
        context = seen["context"]
        assert context is not None
        assert context.tenant_id == provider_id
        assert context.hierarchy.descendants == {customer_id}
        assert context.covers(customer_id) is True
        assert context.covers(987_654) is False


@pytest.mark.usefixtures("app_context")
class TestResponseFieldSets:
    """I7: every tenant response is an explicit projection, exactly."""

    TENANT_DETAIL_FIELDS = {
        "id",
        "name",
        "slug",
        "display_name",
        "kind",
        "status",
        "plan",
        "parent_tenant_id",
        "depth",
        "owner_id",
        "max_users",
        "max_products",
        "user_role",
    }
    TENANT_SUMMARY_FIELDS = {"id", "name", "kind", "status"}

    @pytest.mark.asyncio
    async def test_get_tenant_returns_exactly_the_detail_fields(
        self, client: Any
    ) -> None:
        """Fails on an EXTRA field, not just a missing one."""
        headers, _ = await _new_user(client)
        tenant_id = await _create_tenant(client, headers, "T")

        response = await client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
        body = await response.get_json()

        assert set(body) == self.TENANT_DETAIL_FIELDS
        assert "settings" not in body
        assert "license_key" not in body

    @pytest.mark.asyncio
    async def test_create_tenant_returns_exactly_the_detail_fields(
        self, client: Any
    ) -> None:
        headers, _ = await _new_user(client)
        response = await client.post(
            "/api/v1/tenants",
            headers=headers,
            json={"name": "T", "slug": f"t-{uuid.uuid4().hex[:6]}"},
        )
        assert set(await response.get_json()) == self.TENANT_DETAIL_FIELDS

    TENANT_MEMBER_FIELDS = {
        "id",
        "tenant_id",
        "user_id",
        "role",
        "invited_by_id",
        "joined_at",
        "user_email",
        "user_full_name",
    }

    @pytest.mark.asyncio
    async def test_switch_response_has_exact_field_set(self, client: Any) -> None:
        """The switch payload must carry everything currentTenant needs.

        Cross-branch contract: webui tenantStore.ts populates the entire
        currentTenant from this one object, and LicenseGate.tsx reads
        `plan` off it — defaulting to "free" when absent, which hides every
        licensed feature from every user without erroring. TenantSwitcher.tsx
        additionally renders `slug` and `display_name`.
        """
        headers, _ = await _new_user(client)
        tenant_id = await _create_tenant(client, headers, "T")

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=headers
        )
        body = await response.get_json()

        assert set(body) == {"access_token", "tenant", "tenant_role", "scope"}
        assert set(body["tenant"]) == self.TENANT_DETAIL_FIELDS

        # The three fields the webui reads, asserted by name and value so a
        # future reshuffle of TenantDetail cannot silently drop them.
        assert body["tenant"]["plan"] == "free"
        assert body["tenant"]["slug"]
        assert body["tenant"]["display_name"] == "T"
        assert "settings" not in body["tenant"]

    @pytest.mark.asyncio
    async def test_switch_carries_non_default_plan(self, client: Any) -> None:
        """A paid plan survives the switch payload rather than reading free.

        The LicenseGate failure mode was silent: `plan` simply being absent
        produced a valid response and a wrongly-gated UI. Asserting a
        non-default value is what distinguishes "carries the plan" from
        "happens to match the fallback".
        """
        headers, _ = await _new_user(client)
        tenant_id = await _create_tenant(client, headers, "T")

        upgraded = await client.put(
            f"/api/v1/tenants/{tenant_id}",
            headers=headers,
            json={"plan": "enterprise"},
        )
        assert upgraded.status_code == 200
        assert (await upgraded.get_json())["plan"] == "enterprise"

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=headers
        )
        assert (await response.get_json())["tenant"]["plan"] == "enterprise"

    @pytest.mark.asyncio
    async def test_member_endpoints_share_one_exact_field_set(
        self, client: Any
    ) -> None:
        """List, add and update all return the same explicit member shape.

        add_tenant_member previously returned a raw dict(row) and the role
        update returned only three of the fields the webui's TenantMember
        interface declares.
        """
        owner_headers, _ = await _new_user(client)
        _, member_id = await _new_user(client)

        tenant_id = await _create_tenant(client, owner_headers, "T")

        added = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=owner_headers,
            json={"user_id": member_id, "role": "member"},
        )
        assert added.status_code == 201
        assert set(await added.get_json()) == self.TENANT_MEMBER_FIELDS

        updated = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/{member_id}",
            headers=owner_headers,
            json={"role": "admin"},
        )
        assert updated.status_code == 200
        updated_body = await updated.get_json()
        assert set(updated_body) == self.TENANT_MEMBER_FIELDS
        assert updated_body["role"] == "admin"
        assert updated_body["id"] is not None
        assert updated_body["joined_at"] is not None

        listed = await client.get(
            f"/api/v1/tenants/{tenant_id}/members", headers=owner_headers
        )
        assert listed.status_code == 200
        list_body = await listed.get_json()
        assert set(list_body) == {"members", "count"}
        for row in list_body["members"]:
            assert set(row) == self.TENANT_MEMBER_FIELDS

    @pytest.mark.asyncio
    async def test_member_list_exposes_contact_identity_and_nothing_more(
        self, client: Any
    ) -> None:
        """Email and full name are in; every other users column is out.

        Deliberate policy: administering a tenant means administering its
        member accounts, so an MSP admin needs contact identity. It does NOT
        extend to the rest of the users row.
        """
        owner_headers, _ = await _new_user(client)
        _, member_id = await _new_user(client)
        tenant_id = await _create_tenant(client, owner_headers, "T")
        await _add_member(client, owner_headers, tenant_id, member_id, "member")

        listed = await client.get(
            f"/api/v1/tenants/{tenant_id}/members", headers=owner_headers
        )
        rows = (await listed.get_json())["members"]
        subject = next(r for r in rows if r["user_id"] == member_id)

        assert subject["user_email"].endswith("@example.com")
        assert subject["user_full_name"] == "H User"
        for forbidden in (
            "password_hash",
            "is_active",
            "created_at",
            "updated_at",
            "email",
            "full_name",
        ):
            assert forbidden not in subject

    @pytest.mark.asyncio
    async def test_include_children_exposes_only_summary_for_non_members(
        self, client: Any
    ) -> None:
        """Descendant rows the caller is not a member of are summaries.

        A delegated admin may learn that a descendant exists and whether it
        is live; plan, quotas and owner require switching into it.
        """
        owner_headers, _ = await _new_user(client)
        delegate_headers, delegate_id = await _new_user(client)

        provider_id = await _create_tenant(
            client, owner_headers, "Prov", kind="provider"
        )
        customer_id = await _create_tenant(
            client, owner_headers, "Cust", parent_tenant_id=provider_id
        )
        await _add_member(
            client, owner_headers, provider_id, delegate_id, "admin"
        )

        response = await client.get(
            "/api/v1/tenants?include_children=true", headers=delegate_headers
        )
        assert response.status_code == 200
        rows = {int(r["id"]): r for r in (await response.get_json())["tenants"]}

        assert set(rows) == {provider_id, customer_id}
        assert set(rows[provider_id]) == self.TENANT_DETAIL_FIELDS
        assert set(rows[customer_id]) == self.TENANT_SUMMARY_FIELDS

    @pytest.mark.asyncio
    async def test_rollup_reports_real_product_type_and_exact_fields(
        self, client: Any
    ) -> None:
        """I6: the rollup's `product` is product_type, not a dead lookup.

        It previously read `external_id`, which is not a column on
        product_connections, so .get() returned the "unknown" fallback for
        every row and the rollup carried no product identity at all.
        """
        headers, _ = await _new_user(client)
        tenant_id = await _create_tenant(client, headers, "T")

        created = await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "gough",
                "display_name": "Gough One",
                "base_url": "https://gough.example.com",
                "auth_type": "bearer",
            },
        )
        assert created.status_code == 201, await created.get_json()

        response = await client.get(
            f"/api/v1/tenants/{tenant_id}/dashboard/rollup", headers=headers
        )
        assert response.status_code == 200
        body = await response.get_json()

        assert set(body) == {"rollup", "count"}
        entry = body["rollup"][0]
        assert set(entry) == {"tenant_id", "tenant_name", "products"}
        product = entry["products"][0]
        assert set(product) == {"connection_id", "product", "status"}
        assert product["product"] == "gough"

        # Cross-branch contract: the webui rollup consumer and its MSW
        # fixtures read the `rollup` envelope and index tenants by a NUMERIC
        # id. Serialising these as strings would typecheck fine here and
        # break the frontend at runtime, so the JSON types are pinned.
        assert isinstance(entry["tenant_id"], int)
        assert not isinstance(entry["tenant_id"], bool)
        assert isinstance(product["connection_id"], int)
        assert isinstance(entry["tenant_name"], str)
