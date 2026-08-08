"""Per-product scopes: minted for real, and selective between products.

``products:manage`` grants management of every product a tenant has
connected. With one integration that was indistinguishable from per-product
authority; with three it is not, and an MSP portal is where the difference
bites — a junior admin managing Tobogganing firewall rules must not thereby
be able to delete Gough VMs.

The whole point of this file is the half that is easy to skip. Task 4G's
original brief specified ``gough:{resource}:{read|write}`` scopes, and had
they been implemented, **every Gough route would have answered 403 to every
token the portal can issue** — because nothing mints a ``gough:*`` scope. A
scope is only enforceable if something issues it, so these tests assert
issuance against a real token and real database rows, not just that a
constant exists.

Four properties, in the order they can fail:

1. A real token carries ``products:gough:{read,manage}`` (mint side).
2. A rule requiring one is satisfied by it (enforce side).
3. A principal holding ONLY the Gough scope reaches Gough's rules and no
   other product's — the junior-admin case the model exists for.
4. The coarse ``products:*`` grant still satisfies every per-product rule,
   so nothing that worked before this change stopped working.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt
import pytest
from quart import Quart

from app.adapters.base import PRODUCT_SCOPE_NAMESPACE, RBACEnforcer, product_scope
from app.adapters.gough import GOUGH_ROUTE_ALLOWLIST, PRODUCT_TYPE
from app.tenancy.authz import (
    PRODUCT_SCOPE_ACTIONS,
    is_valid_product_type_for_scope,
)

GOUGH_READ = product_scope(PRODUCT_TYPE, "read")
GOUGH_MANAGE = product_scope(PRODUCT_TYPE, "manage")
NEST_MANAGE = product_scope("nest", "manage")


async def _register(client: Any) -> tuple[int, str]:
    """Register a user; return (id, email)."""
    email = f"psc-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Scope User"},
    )
    assert response.status_code in (200, 201), await response.get_json()
    return int((await response.get_json())["user"]["id"]), email


async def _headers(client: Any, email: str) -> dict[str, str]:
    """Log in and build Authorization headers."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert response.status_code == 200, await response.get_json()
    return {"Authorization": f"Bearer {(await response.get_json())['access_token']}"}


async def _create_tenant(
    client: Any,
    headers: dict[str, str],
    name: str,
    *,
    kind: str | None = None,
    parent_tenant_id: int | None = None,
) -> int:
    """Create a tenant owned by the caller."""
    payload: dict[str, Any] = {
        "name": name,
        "slug": f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        "plan": "free",
    }
    if kind:
        payload["kind"] = kind
    if parent_tenant_id is not None:
        payload["parent_tenant_id"] = parent_tenant_id

    response = await client.post("/api/v1/tenants", headers=headers, json=payload)
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _connect(app: Quart, tenant_id: int, product_type: str) -> int:
    """Give a tenant a connection to a product type."""
    async with app.app_context():
        from app.models import create_product_connection

        conn_id = await create_product_connection(
            tenant_id=tenant_id,
            product_type=product_type,
            display_name=f"{product_type} conn",
            base_url="https://product.invalid",
            auth_type="bearer",
            api_key="-".join(("not", "a", "real", "scope", "credential")),
            api_secret="",
        )
        assert conn_id is not None
        return int(conn_id)


async def _scopes(app: Quart, user_id: int, tenant_id: int) -> list[str]:
    """Resolve a user's scopes in a tenant through the real minter."""
    async with app.app_context():
        from app.tenancy.authz import resolve_scopes

        return await resolve_scopes(user_id, tenant_id)


@pytest.mark.usefixtures("app_context")
class TestScopesAreMinted:
    """The mint side. A rule may only require what something issues."""

    @pytest.mark.asyncio
    async def test_connecting_gough_mints_the_gough_scopes(
        self, client: Any, app: Quart
    ) -> None:
        """A tenant with a Gough connection resolves Gough scopes."""
        user_id, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "MintGough")

        before = await _scopes(app, user_id, tenant_id)
        assert GOUGH_READ not in before, "scope minted with no connection"

        await _connect(app, tenant_id, PRODUCT_TYPE)

        after = await _scopes(app, user_id, tenant_id)
        assert GOUGH_READ in after
        assert GOUGH_MANAGE in after

    @pytest.mark.asyncio
    async def test_access_token_actually_carries_the_per_product_scope(
        self, client: Any, app: Quart
    ) -> None:
        """The claim reaches a real JWT, not just resolve_scopes().

        This is the assertion the original brief would have failed. A scope
        constant that no token carries is a permanently unsatisfiable gate,
        and it looks *more* secure than what it replaced right up until
        someone tries to use the product.
        """
        user_id, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "MintToken")
        await _connect(app, tenant_id, PRODUCT_TYPE)

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/switch", headers=headers
        )
        assert response.status_code == 200, await response.get_json()
        body = await response.get_json()

        payload = jwt.decode(body["access_token"], options={"verify_signature": False})
        assert GOUGH_READ in payload["scope"]
        assert GOUGH_MANAGE in payload["scope"]
        assert payload["scope"] == body["scope"]

        # And the minted scope satisfies a real rule from the shipped
        # allowlist -- the mint and enforce halves meeting on live data.
        for rule in GOUGH_ROUTE_ALLOWLIST:
            assert RBACEnforcer(rule.required_scope).enforce(
                payload["scope"]
            ), rule.path_regex

    @pytest.mark.asyncio
    async def test_a_viewer_gets_read_but_never_manage(
        self, client: Any, app: Quart
    ) -> None:
        """Expansion is derived from the coarse grant, so it cannot widen.

        A bundle without ``products:manage`` must not acquire a per-product
        manage scope on the way through: the expansion re-expresses existing
        authority, it does not confer any.
        """
        owner_id, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        tenant_id = await _create_tenant(client, owner_headers, "MintViewer")
        await _connect(app, tenant_id, PRODUCT_TYPE)

        viewer_id, _ = await _register(client)
        add = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=owner_headers,
            json={"user_id": viewer_id, "role": "viewer"},
        )
        assert add.status_code == 201, await add.get_json()

        scopes = await _scopes(app, viewer_id, tenant_id)
        assert GOUGH_READ in scopes
        assert GOUGH_MANAGE not in scopes
        assert "products:manage" not in scopes

    @pytest.mark.asyncio
    async def test_delegated_msp_admin_gets_the_descendants_product_scopes(
        self, client: Any, app: Quart
    ) -> None:
        """Delegation is inherited, not re-implemented.

        ``resolve_scopes`` already routes through ``resolve_effective_role``,
        so a provider admin with no ``tenant_members`` row in the customer
        tenant resolves the same per-product scopes a direct admin there
        would. Asserting it here is what stops a future change forking the
        two paths.
        """
        _, owner_email = await _register(client)
        owner_headers = await _headers(client, owner_email)
        delegate_id, _ = await _register(client)

        provider_id = await _create_tenant(
            client, owner_headers, "MspProv", kind="provider"
        )
        customer_id = await _create_tenant(
            client, owner_headers, "MspCust", parent_tenant_id=provider_id
        )

        # The delegate administers the PROVIDER only, and is never enrolled
        # in the customer tenant -- that is what makes the authority below
        # delegated rather than direct.
        add = await client.post(
            f"/api/v1/tenants/{provider_id}/members",
            headers=owner_headers,
            json={"user_id": delegate_id, "role": "admin"},
        )
        assert add.status_code == 201, await add.get_json()

        # The connection belongs to the CUSTOMER, not the provider.
        await _connect(app, customer_id, PRODUCT_TYPE)

        async with app.app_context():
            from app.models import get_user_tenant_role

            assert await get_user_tenant_role(delegate_id, customer_id) is None

        scopes = await _scopes(app, delegate_id, customer_id)
        assert GOUGH_MANAGE in scopes

        # ...and not in the provider tenant, which has no Gough connection.
        assert GOUGH_MANAGE not in await _scopes(app, delegate_id, provider_id)


@pytest.mark.usefixtures("app_context")
class TestScopesAreSelective:
    """The reason the model exists: one product, not all of them."""

    def test_gough_scope_grants_gough_rules_and_not_another_products(self) -> None:
        """A principal holding only ``products:gough:manage``.

        No coarse ``products:manage``, so this is the junior-admin case: it
        must satisfy every rule Gough declares and none that another product
        declares. If this ever passes for both, per-product scopes have
        become decorative and the allowlist is back to all-or-nothing.
        """
        granted = [GOUGH_READ, GOUGH_MANAGE]

        for rule in GOUGH_ROUTE_ALLOWLIST:
            assert RBACEnforcer(rule.required_scope).enforce(
                granted
            ), f"gough scope denied its own rule: {rule.method} {rule.path_regex}"

        assert not RBACEnforcer(NEST_MANAGE).enforce(granted)
        assert not RBACEnforcer(product_scope("tobogganing", "read")).enforce(granted)

    def test_another_products_scope_does_not_reach_gough(self) -> None:
        """The converse, so the asymmetry is not an artefact of rule order."""
        granted = [NEST_MANAGE, product_scope("nest", "read")]

        for rule in GOUGH_ROUTE_ALLOWLIST:
            assert not RBACEnforcer(rule.required_scope).enforce(
                granted
            ), f"nest scope reached {rule.method} {rule.path_regex}"

    def test_read_scope_never_satisfies_a_mutating_rule(self) -> None:
        """Read/write remains the enforceable split within a product."""
        granted = [GOUGH_READ]
        mutating = {"POST", "PUT", "PATCH", "DELETE"}

        for rule in GOUGH_ROUTE_ALLOWLIST:
            allowed = RBACEnforcer(rule.required_scope).enforce(granted)
            assert allowed is (
                rule.method.upper() not in mutating
            ), f"{rule.method} {rule.path_regex}"


@pytest.mark.usefixtures("app_context")
class TestCoarseGrantStillWorks:
    """Nothing that worked before this change may have stopped working."""

    def test_coarse_manage_satisfies_every_gough_rule(self) -> None:
        """``products:manage`` alone — e.g. a token minted before this change."""
        granted = ["products:read", "products:manage"]
        for rule in GOUGH_ROUTE_ALLOWLIST:
            assert RBACEnforcer(rule.required_scope).enforce(
                granted
            ), f"{rule.method} {rule.path_regex}"

    def test_coarse_read_satisfies_reads_and_not_writes(self) -> None:
        """The coarse grant inherits the read/write split, it does not erase it."""
        granted = ["products:read"]
        mutating = {"POST", "PUT", "PATCH", "DELETE"}

        for rule in GOUGH_ROUTE_ALLOWLIST:
            allowed = RBACEnforcer(rule.required_scope).enforce(granted)
            assert allowed is (rule.method.upper() not in mutating)

    def test_implication_is_confined_to_the_products_namespace(self) -> None:
        """No other scope namespace gains an implication by accident.

        ``RBACEnforcer`` is the shared primitive behind portal routes and the
        proxy alike, so a loosely written implication here would widen every
        gate in the service, not just product ones.
        """
        assert not RBACEnforcer("tenants:billing:extra").enforce(["tenants:billing"])
        assert not RBACEnforcer("users:gough:manage").enforce(["users:manage"])
        # Four segments is not the per-product shape and must not resolve.
        assert not RBACEnforcer("products:gough:nodes:manage").enforce(
            ["products:manage"]
        )
        # A per-product scope must not imply the coarse one (one-directional).
        assert not RBACEnforcer("products:manage").enforce([GOUGH_MANAGE])


class TestScopeStringSafety:
    """A derived scope always has the shape it appears to have."""

    def test_the_two_definitions_of_the_namespace_agree(self) -> None:
        """base.py duplicates the literal to avoid an import cycle.

        ``app.authz`` imports ``app.adapters.base``, so the adapter side
        cannot import the authz side. Duplication is the sanctioned
        workaround; this is what stops the copies drifting.
        """
        from app.tenancy.authz import PRODUCT_SCOPE_NAMESPACE as MINTER_NAMESPACE
        from app.tenancy.authz import product_scope as minter_product_scope

        assert PRODUCT_SCOPE_NAMESPACE == MINTER_NAMESPACE
        assert product_scope(PRODUCT_TYPE, "manage") == minter_product_scope(
            PRODUCT_TYPE, "manage"
        )

    def test_every_action_the_minter_knows_has_a_coarse_counterpart(self) -> None:
        """Expansion keys off the coarse scope, so the names must line up."""
        from app.authz import SCOPE_PRODUCTS_MANAGE, SCOPE_PRODUCTS_READ

        coarse = {SCOPE_PRODUCTS_READ, SCOPE_PRODUCTS_MANAGE}
        assert {
            f"{PRODUCT_SCOPE_NAMESPACE}:{action}" for action in PRODUCT_SCOPE_ACTIONS
        } == coarse

    def test_a_product_type_cannot_forge_a_differently_shaped_scope(self) -> None:
        """product_type is operator-supplied at connection time.

        A value containing a colon would produce a four-segment string that
        reads like a scope of a different shape (``x:manage`` ->
        ``products:x:manage:read``). The charset guard is what keeps a
        derived scope at exactly three segments.
        """
        for hostile in (
            "gough:manage",
            "../gough",
            "gough manage",
            "GOUGH",
            "",
            "a" * 64,
            "products:gough:manage",
        ):
            assert not is_valid_product_type_for_scope(hostile), hostile

        for legitimate in ("gough", "nest", "tobogganing", "license_server", "a"):
            assert is_valid_product_type_for_scope(legitimate), legitimate

    @pytest.mark.asyncio
    async def test_a_hostile_product_type_mints_nothing(
        self, client: Any, app: Quart
    ) -> None:
        """The guard is applied by the minter, not merely available to it."""
        user_id, email = await _register(client)
        headers = await _headers(client, email)
        tenant_id = await _create_tenant(client, headers, "MintHostile")
        await _connect(app, tenant_id, "gough:manage")

        scopes = await _scopes(app, user_id, tenant_id)
        assert not any(s.count(":") > 2 for s in scopes), scopes
        assert GOUGH_MANAGE not in scopes
