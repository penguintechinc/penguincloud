"""Scale and structure limits: the paywall under the current tier model.

"The paywall gates scale and structure, not features." Every tier gets every
module with full features; what the licence buys is room to grow. So the
thing to test is not "is this capability missing" — it must never be — but
"is the Nth one allowed and the N+1th REFUSED, for the right reason".

Two requirements shape these tests:

* **Enforcement is a hard block.** Each boundary asserts the write did not
  happen, not merely that a warning appeared. A silent cap that drops the
  write looks identical to success from the client's side.
* **The numbers are licence-server-configurable defaults.** A deployment's
  licence may raise or lower any of them, so the resolution path is tested
  with payload overrides, not just against the fallback table.
"""

from __future__ import annotations

import uuid
from dataclasses import fields
from typing import Any

import pytest
from app import licensing, quotas
from penguin_dal.quart_ext import get_db
from quart import Quart

#: The REAL resolver, captured at import time.
#:
#: tests/conftest.py installs a session-scoped fixture that resolves limits
#: as Enterprise for the whole suite (its fixtures build multi-tenant
#: hierarchies that a Free licence hard-blocks). That fixture runs at first
#: test setup, after this module is imported, so this reference is the
#: unpatched function. The two domain-bypass tests below must exercise the
#: real resolution path or they would only be asserting the fixture.
_REAL_RESOLVE_LIMITS = quotas.resolve_limits


@pytest.fixture(autouse=True)
def _reset_license() -> Any:
    licensing.reset_client()
    yield
    licensing.reset_client()


def _limits(monkeypatch: pytest.MonkeyPatch, **overrides: int) -> None:
    """Pin the effective limits, so a test states its own preconditions."""
    base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY]
    resolved = quotas.TierLimits(
        **{
            field.name: overrides.get(field.name, getattr(base, field.name))
            for field in fields(quotas.TierLimits)
        }
    )

    async def _resolve() -> quotas.TierLimits:
        return resolved

    monkeypatch.setattr(quotas, "resolve_limits", _resolve)


class TestTheModelIsScaleNotFeatures:
    """Guards against sliding back to a feature-locked free tier."""

    def test_no_module_is_gated_by_a_limit(self) -> None:
        """No quota dimension may name a product or module.

        The tier model forbids a locked or crippled module outright. If a
        change here would make a CAPABILITY unavailable rather than a
        COUNT unavailable, it belongs in FEATURE_MIN_TIER instead.
        """
        from app.flags import PRODUCT_FLAGS

        assert set(quotas.DIMENSIONS).isdisjoint(PRODUCT_FLAGS)

    def test_every_tier_gets_unlimited_non_admin_members(self) -> None:
        """Members are explicitly unlimited at every tier.

        A dimension counting ordinary users would silently reintroduce the
        user cap the tier model deliberately removed, so there must not be
        one.
        """
        assert "members" not in quotas.DIMENSIONS
        assert "users" not in quotas.DIMENSIONS

    def test_the_three_side_tables_agree_with_the_dataclass(self) -> None:
        """Limits, licence keys and labels are all keyed by dimension.

        Three parallel dicts drift; asserted together so a new dimension
        cannot ship with no licence override key or a blank error message.
        """
        assert set(quotas.LICENSE_LIMIT_KEYS) == set(quotas.DIMENSIONS)
        assert set(quotas.DIMENSION_LABELS) == set(quotas.DIMENSIONS)
        for tier in licensing.TIER_ORDER:
            assert tier in quotas.DEFAULT_TIER_LIMITS


class TestDefaultTable:
    """The commercial table, transcribed once and asserted."""

    @pytest.mark.parametrize(
        "tier,dimension,expected",
        [
            ("community", "global_admins", 1),
            ("community", "tenant_admins", 0),
            ("community", "tenants", 1),
            ("community", "teams", 1),
            ("community", "objects", 1000),
            ("professional", "global_admins", 1),
            ("professional", "tenant_admins", 10),
            ("professional", "tenants", 1),
            ("professional", "teams", quotas.UNLIMITED),
            ("professional", "objects", quotas.UNLIMITED),
            ("enterprise", "global_admins", quotas.UNLIMITED),
            ("enterprise", "tenant_admins", quotas.UNLIMITED),
            ("enterprise", "tenants", quotas.UNLIMITED),
            ("enterprise", "teams", quotas.UNLIMITED),
            ("enterprise", "objects", quotas.UNLIMITED),
        ],
    )
    def test_table(self, tier: str, dimension: str, expected: int) -> None:
        """Table."""
        assert getattr(quotas.DEFAULT_TIER_LIMITS[tier], dimension) == expected

    def test_limits_never_narrow_as_the_tier_widens(self) -> None:
        """A higher tier must not buy less of anything."""
        for dimension in quotas.DIMENSIONS:
            previous = 0
            for tier in licensing.TIER_ORDER:
                value = getattr(quotas.DEFAULT_TIER_LIMITS[tier], dimension)
                if value == quotas.UNLIMITED:
                    previous = 10**9
                    continue
                assert value >= previous, f"{dimension} narrows at {tier}"
                previous = value


class TestLicenseConfigurableLimits:
    """The numbers are defaults; a licence may move them."""

    def test_payload_raises_a_limit(self) -> None:
        """Payload raises a limit."""
        limits = quotas.limits_for_tier("community", {"max_teams": 25})
        assert limits.teams == 25
        assert limits.tenants == 1, "an override must not disturb its neighbours"

    def test_payload_lowers_a_limit(self) -> None:
        """Down as well as up — a restricted contract is expressible."""
        limits = quotas.limits_for_tier("enterprise", {"max_tenants": 5})
        assert limits.tenants == 5
        assert limits.teams == quotas.UNLIMITED

    def test_payload_can_grant_unlimited(self) -> None:
        """Payload can grant unlimited."""
        limits = quotas.limits_for_tier("community", {"max_objects": quotas.UNLIMITED})
        assert limits.objects == quotas.UNLIMITED

    @pytest.mark.parametrize("bad", ["ten", None, True, -2, 1.5, [], {}])
    def test_a_malformed_override_falls_back_to_the_tier_default(self, bad: Any) -> None:
        """Neither 0 nor unlimited is a safe reading of a broken value.

        Zero locks the deployment out of its own product; unlimited hands
        away the paywall. Both are invisible to the operator, so a value
        that cannot be read is ignored in favour of the tier default.
        """
        limits = quotas.limits_for_tier("community", {"max_teams": bad})
        assert limits.teams == 1

    def test_an_unknown_tier_resolves_to_the_narrowest(self) -> None:
        """An unrecognised licence must not read as unlimited."""
        assert (
            quotas.limits_for_tier("platinum")
            == (quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY])
        )

    def test_no_payload_is_the_plain_default(self) -> None:
        """No payload is the plain default."""
        assert (
            quotas.limits_for_tier("professional", None)
            == (quotas.DEFAULT_TIER_LIMITS[licensing.TIER_PROFESSIONAL])
        )

    @pytest.mark.asyncio
    async def test_a_managed_domain_gets_the_enterprise_table(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same domain-only bypass as entitlement — billed separately.

        Resolved from the CONFIGURED domain. This test used to spoof a
        ``Host`` header, which is what made the whole limits table
        reachable by any caller willing to send one.
        """
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://portal.penguincloud.io")
        async with app.app_context():
            assert (
                await _REAL_RESOLVE_LIMITS()
                == (quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE])
            )

    @pytest.mark.asyncio
    async def test_an_ordinary_domain_does_not(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An ordinary domain does not."""
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://customer.example.com")
        async with app.app_context():
            assert (
                await _REAL_RESOLVE_LIMITS()
                == (quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY])
            )

    @pytest.mark.asyncio
    async def test_a_spoofed_host_header_does_not_buy_the_enterprise_table(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The limits table is not a header away from being unlimited."""
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://customer.example.com")
        async with app.test_request_context(
            "/api/v1/features", headers={"Host": "portal.penguincloud.io"}
        ):
            assert (
                await _REAL_RESOLVE_LIMITS()
                == (quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY])
            )


class TestTenantAdminsAreCountedDeploymentWide:
    """The table publishes one number, so it must mean one number."""

    @pytest.mark.asyncio
    async def test_admins_in_different_tenants_share_the_limit(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Counted per-tenant, "10 tenant admins" silently meant 10 per tenant.

        Not exploitable while tenants are themselves capped at 1 below
        Enterprise — but every limit is licence-configurable, so a payload
        raising ``max_tenants`` alone yielded 10xN delegated admins under a
        limit sold as 10. Two dimensions must not multiply.
        """
        async with app.app_context():
            db = get_db()
            first = await db.tenants.async_insert(
                name="A", slug=f"a-{uuid.uuid4().hex[:8]}", owner_id=1
            )
            second = await db.tenants.async_insert(
                name="B", slug=f"b-{uuid.uuid4().hex[:8]}", owner_id=1
            )
            await db.tenant_members.async_insert(tenant_id=first, user_id=1, role="admin")
            await db.tenant_members.async_insert(tenant_id=second, user_id=1, role="admin")
            # Owners are excluded, so only the two admins above count.
            await db.tenant_members.async_insert(tenant_id=second, user_id=2, role="owner")

            assert await quotas.count_tenant_admins() == 2


class TestRefusalShape:
    """A hard block that names the upgrade, not a dead end."""

    @pytest.mark.asyncio
    async def test_under_the_limit_is_allowed(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Under the limit is allowed."""
        _limits(monkeypatch, teams=1)
        assert await quotas.quota_refusal("teams", 0) is None

    @pytest.mark.asyncio
    async def test_at_the_limit_refuses_the_next_one(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """At the limit refuses the next one."""
        _limits(monkeypatch, teams=1)
        refusal = await quotas.quota_refusal("teams", 1)

        assert refusal is not None
        body, status = refusal
        assert status == 402, "a scale wall is not an authorization denial"
        assert body["error"] == "quota_exceeded"
        assert body["dimension"] == "teams"
        assert body["limit"] == 1
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL
        assert "professional" in body["message"]

    @pytest.mark.asyncio
    async def test_unlimited_never_refuses(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unlimited never refuses."""
        _limits(monkeypatch, teams=quotas.UNLIMITED)
        assert await quotas.quota_refusal("teams", 10_000) is None

    @pytest.mark.asyncio
    async def test_required_tier_is_present_even_when_null(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The key is always there, so a client never reads absence.

        Same rule as the features envelope: an absent key and a deliberate
        "no tier lifts this" are indistinguishable to a caller that has to
        infer one from the other.
        """
        _limits(monkeypatch, objects=1000)
        refusal = await quotas.quota_refusal("objects", 10_000)

        assert refusal is not None
        body, _ = refusal
        assert "required_tier" in body
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL

    @pytest.mark.asyncio
    async def test_an_override_below_the_tier_default_names_no_upgrade(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Upgrading to the tier you are already on is not an instruction.

        A licence may LOWER a limit below its tier default. minimum_tier_for
        reads the default table on purpose (it should say what the PRODUCT
        sells, not what this contract was tuned to), so it would name the
        current tier. The binding constraint is then the deployment's own
        contract, and the honest answer is that no upgrade lifts it.
        """
        _limits(monkeypatch, objects=5)
        refusal = await quotas.quota_refusal("objects", 5)

        assert refusal is not None
        body, status = refusal
        assert status == 402
        assert body["required_tier"] is None
        assert "contact sales" in body["message"]

    @pytest.mark.asyncio
    async def test_a_genuine_upgrade_is_still_named(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The suppression above must not swallow real upgrade paths."""
        _limits(monkeypatch, tenants=1)
        refusal = await quotas.quota_refusal("tenants", 1)

        assert refusal is not None
        body, _ = refusal
        assert body["required_tier"] == licensing.TIER_ENTERPRISE

    @pytest.mark.parametrize(
        "dimension,wanted,expected",
        [
            ("tenants", 2, "enterprise"),
            ("teams", 2, "professional"),
            ("tenant_admins", 1, "professional"),
            ("tenant_admins", 11, "enterprise"),
            ("global_admins", 2, "enterprise"),
            ("objects", 1001, "professional"),
            ("tenants", 1, "community"),
        ],
    )
    def test_minimum_tier_for(self, dimension: str, wanted: int, expected: str) -> None:
        """The upgrade named must actually admit what was refused."""
        assert quotas.minimum_tier_for(dimension, wanted) == expected


class TestEnforcementAtTheWritePaths:
    """Nth allowed, N+1 refused, and the write genuinely did not happen."""

    @pytest.mark.asyncio
    async def test_second_tenant_is_refused_below_enterprise(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Tenants are 1/1/unlimited: multi-tenant is an Enterprise structure.

        Limits are set RELATIVE to what the shared test database already
        holds. An absolute `tenants=1` would refuse for a reason unrelated
        to the boundary under test as soon as another test created a row.
        """
        async with app.app_context():
            _limits(monkeypatch, tenants=await quotas.count_tenants())
        before = await _count(client, admin_headers)

        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Second", "slug": "second-tenant", "kind": "customer"},
        )

        assert response.status_code == 402
        body = await response.get_json()
        assert body["error"] == "quota_exceeded"
        assert body["dimension"] == "tenants"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE
        # A hard block: the row must not exist.
        assert await _count(client, admin_headers) == before

    @pytest.mark.asyncio
    async def test_a_raised_limit_admits_the_second_tenant(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The positive case, so the refusal above means something.

        Both halves of the wall must give way: the number the licence
        carries AND the ``multi_tenant`` capability. Raising the number
        alone is deliberately not enough — see
        ``test_a_raised_limit_without_the_capability_still_refuses``.
        """
        async with app.app_context():
            _limits(monkeypatch, tenants=await quotas.count_tenants() + 1)
        monkeypatch.setattr(licensing, "is_feature_entitled_blocking", lambda feature: True)

        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Second", "slug": "second-allowed", "kind": "customer"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_a_raised_limit_without_the_capability_still_refuses(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A numeric override must not sell an Enterprise capability.

        Every limit is licence-configurable by design, so ``max_tenants: 5``
        on a Community licence would otherwise hand out multi-tenancy with
        nothing checking the entitlement it belongs to. The count is the
        scale wall; ``multi_tenant`` is the capability, and both apply.
        """
        async with app.app_context():
            _limits(monkeypatch, tenants=await quotas.count_tenants() + 1)

        response = await client.post(
            "/api/v1/tenants",
            headers=admin_headers,
            json={"name": "Second", "slug": "second-uncapable", "kind": "customer"},
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_not_entitled"
        assert body["feature"] == "multi_tenant"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE

    @pytest.mark.asyncio
    async def test_second_team_is_refused_on_free(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Second team is refused on free."""
        async with app.app_context():
            _limits(monkeypatch, teams=await quotas.count_teams() + 1)

        first = await client.post(
            "/api/v1/teams",
            headers=admin_headers,
            json={"name": "One", "slug": "team-one"},
        )
        second = await client.post(
            "/api/v1/teams",
            headers=admin_headers,
            json={"name": "Two", "slug": "team-two"},
        )

        assert first.status_code == 201
        assert second.status_code == 402
        body = await second.get_json()
        assert body["dimension"] == "teams"
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL

    @pytest.mark.asyncio
    async def test_free_admits_no_delegated_tenant_admin(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Delegated MSP admin is a licensed STRUCTURE: Free gets 0.

        Phase 2B built the delegation path; under the current tier model it
        is metered, and this asserts it is not silently allowing what the
        licence does not sell.
        """
        _limits(monkeypatch, tenant_admins=0)

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "admin"},
        )

        assert response.status_code == 402
        body = await response.get_json()
        assert body["dimension"] == "tenant_admins"
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL

    @pytest.mark.asyncio
    async def test_a_non_admin_member_is_never_metered(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Members are unlimited at every tier — including Free with 0 admins.

        The load-bearing half of "the paywall gates scale, not features": a
        free deployment must still be able to add people.
        """
        _limits(monkeypatch, tenant_admins=0)

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "member"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_promotion_is_metered_like_enrolment(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Add-as-member-then-promote must not be an unmetered route.

        Gating only the add path leaves the same structure reachable in two
        calls, which is the shape of every cap that has ever leaked.
        """
        _limits(monkeypatch, tenant_admins=0)

        added = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "member"},
        )
        assert added.status_code == 201

        promoted = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/{user_id}",
            headers=admin_headers,
            json={"role": "admin"},
        )

        assert promoted.status_code == 402
        assert (await promoted.get_json())["dimension"] == "tenant_admins"

    @pytest.mark.asyncio
    async def test_object_quota_refuses_a_connection_past_the_wall(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Objects = product connections, enforced at connection create.

        The wall is set to the CURRENT count so the next write crosses it.
        On a real Free deployment 1,000 is unlikely ever to bind (1 tenant,
        1 team, a handful of connections) — that is documented in
        quotas.count_objects and is why this test manufactures the boundary
        rather than trying to reach it.
        """
        async with app.app_context():
            _limits(monkeypatch, objects=await quotas.count_objects())

        response = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "gough",
                "display_name": "Over The Wall",
                "base_url": "https://gough.example.com",
                "auth_type": "bearer",
            },
        )

        assert response.status_code == 402
        body = await response.get_json()
        assert body["dimension"] == "objects"
        # None, not "community": the wall here is a licence override BELOW
        # the tier default, so no upgrade lifts it and saying "upgrade to
        # the tier you are already on" would be nonsense. See
        # quota_refusal's strictly-above check.
        assert body["required_tier"] is None
        assert "contact sales" in body["message"]

    @pytest.mark.asyncio
    async def test_a_connection_under_the_wall_is_created(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The positive case, so the refusal above means something."""
        async with app.app_context():
            _limits(monkeypatch, objects=await quotas.count_objects() + 1)

        response = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "gough",
                "display_name": "Under The Wall",
                "base_url": "https://gough2.example.com",
                "auth_type": "bearer",
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_the_object_wall_is_separate_from_the_per_tenant_quota(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two different ceilings, and neither substitutes for the other.

        `max_products` is an operator-set ceiling on ONE tenant and answers
        403; the object quota is what the LICENCE sells and answers 402. A
        client that saw only one status could not tell "this tenant is
        full" from "this plan is full".
        """
        async with app.app_context():
            _limits(monkeypatch, objects=await quotas.count_objects())

        response = await client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "tenant_id": tenant_id,
                "product_type": "gough",
                "display_name": "Distinguishable",
                "base_url": "https://gough3.example.com",
                "auth_type": "bearer",
            },
        )

        assert response.status_code == 402
        assert (await response.get_json())["error"] == "quota_exceeded"

    @pytest.mark.asyncio
    async def test_second_global_admin_is_refused_below_enterprise(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Global admins are 1/1/unlimited."""
        async with app.app_context():
            _limits(monkeypatch, global_admins=await quotas.count_global_admins())

        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "second-admin@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Second Admin",
                "role": "admin",
            },
        )

        assert response.status_code == 402
        body = await response.get_json()
        assert body["dimension"] == "global_admins"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE

    @pytest.mark.asyncio
    async def test_global_admin_promotion_is_metered_like_creation(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Create-as-viewer-then-promote must not be an unmetered route.

        Added after a revert check: deleting the promotion gate in
        users.py left every quota test green, so the cap was enforced on
        one of its two entrances only. Exactly the shape of every cap that
        has leaked.
        """
        created = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "promote-me@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Promote Me",
                "role": "viewer",
            },
        )
        assert created.status_code == 201
        new_user_id = (await created.get_json())["user"]["id"]

        async with app.app_context():
            _limits(monkeypatch, global_admins=await quotas.count_global_admins())

        promoted = await client.put(
            f"/api/v1/users/{new_user_id}",
            headers=admin_headers,
            json={"role": "admin"},
        )

        assert promoted.status_code == 402
        body = await promoted.get_json()
        assert body["dimension"] == "global_admins"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE

    @pytest.mark.asyncio
    async def test_a_non_admin_user_is_never_metered(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non admin user is never metered."""
        async with app.app_context():
            _limits(monkeypatch, global_admins=await quotas.count_global_admins())

        response = await client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "ordinary@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Ordinary",
                "role": "viewer",
            },
        )

        assert response.status_code == 201


async def _count(client: Any, headers: dict[str, str]) -> int:
    """Tenants visible to the caller, read back through the API."""
    response = await client.get("/api/v1/tenants", headers=headers)
    return len((await response.get_json())["tenants"])
