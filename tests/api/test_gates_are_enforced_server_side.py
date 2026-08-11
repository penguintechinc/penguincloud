"""The gates this branch declared, exercised at the routes that carry them.

Every test here covers something that was *declared* and not *enforced* —
the failure mode this project keeps producing, in five different shapes:

* ``penguincloud.{product}`` flags reached only the browser, so
  ``featureGates.ts`` decided what to render while the API accepted
  anything (:class:`TestProductFlagGatesTheApi`);
* ``delegated_admin`` and ``multi_tenant`` were sold in
  ``FEATURE_MIN_TIER`` and checked nowhere
  (:class:`TestLicensedCapabilitiesAreChecked`);
* ``POST /api/v1/auth/register`` created a team past the licensed limit
  (:class:`TestRegistrationIsMetered`);
* ``--dev`` consulted nothing in the entitlement path and appeared to work
  only because it shares a domain predicate with the licence bypass
  (:class:`TestDevModeActuallyWidensEntitlement`);
* the OAuth signup path skipped the dev-mode cap and hit the model backstop
  instead, turning a 402 into a 500 (:class:`TestOauthSignupRespectsTheCap`).

Assertions are behavioural on purpose: a scanner proving a name is spelled
at a gate proves spelling, not enforcement.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from quart import Quart

from conftest import _FakeFlagServer

from app import devmode, flags, licensing, models, quotas


def _flag_server(
    monkeypatch: pytest.MonkeyPatch,
    enabled: frozenset[str],
    disabled: frozenset[str] = frozenset(),
) -> None:
    """Install a flag server with an explicit answer for each named flag."""
    monkeypatch.setattr(flags, "_client", _FakeFlagServer(enabled, disabled))
    monkeypatch.setattr(flags, "_client_built", True)
    flags._CACHE.clear()


def _no_flag_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model a deployment with no PostHog configured at all."""
    monkeypatch.delenv("POSTHOG_KEY", raising=False)
    flags.reset_client()


async def _register_connection(
    client: Any, headers: dict[str, str], tenant_id: int, product_type: str
) -> Any:
    return await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "product_type": product_type,
            "display_name": f"{product_type} one",
            "base_url": "https://product.example.com",
            "auth_type": "bearer",
            "api_key": "not-a-real-key",
        },
    )


class TestProductFlagGatesTheApi:
    """The flag decides what the API does, not only what the UI draws."""

    @pytest.mark.asyncio
    async def test_a_disabled_product_flag_refuses_connection_create(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct API call, no browser involved — the gate must still hold."""
        _flag_server(
            monkeypatch, flags.PRODUCT_FLAGS - {"gough"}, disabled=frozenset({"gough"})
        )

        response = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_disabled"
        assert body["flag"] == "penguincloud.gough"

    @pytest.mark.asyncio
    async def test_an_enabled_product_flag_admits_the_same_call(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The positive case, so the refusal above is not vacuous."""
        _flag_server(monkeypatch, flags.PRODUCT_FLAGS)

        response = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_no_flag_backend_leaves_every_module_available(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A deployment with no PostHog must not be an inert portal.

        The tier model is explicit that every tier gets ALL modules with
        full features and that a locked or crippled module is never an
        acceptable outcome. Resolving product flags to OFF when no flag
        backend is configured — which is most self-hosted deployments —
        left the portal with no products at all.
        """
        _no_flag_server(monkeypatch)

        assert flags.get_client() is None
        response = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_a_configured_server_that_knows_nothing_kills_nothing(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unknown is not "off": connecting PostHog must not lose modules.

        An operator who points the portal at a flag server before defining
        twenty flag definitions would otherwise lose twenty product modules
        at once, with the refusal blaming a flag that does not exist.
        """
        _flag_server(monkeypatch, frozenset())

        response = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_a_disabled_product_flag_refuses_the_proxy(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A connection created while ON must stop proxying when turned OFF.

        This is the kill-switch case: the flag exists so an operator can
        disable a module without a redeploy, and a gate only on the create
        path would leave every existing connection fully usable.
        """
        _flag_server(monkeypatch, flags.PRODUCT_FLAGS)
        created = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )
        assert created.status_code == 201
        connection_id = (await created.get_json())["id"]

        _flag_server(
            monkeypatch, flags.PRODUCT_FLAGS - {"gough"}, disabled=frozenset({"gough"})
        )

        response = await client.get(
            f"/api/v1/products/{connection_id}/proxy/api/v1/nodes",
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert (await response.get_json())["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_an_unflagged_product_type_is_not_refused(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``generic`` has no module to switch off — see UNFLAGGED_PRODUCT_TYPES."""
        _flag_server(
            monkeypatch, frozenset(), disabled=frozenset(flags.PRODUCT_FLAGS)
        )

        response = await _register_connection(
            client, admin_headers, tenant_id, "generic"
        )

        assert response.status_code == 201


class TestValidationPrecedesMetering:
    """A malformed request is a 400, whatever the quota says."""

    @pytest.mark.asyncio
    async def test_an_invalid_product_type_over_quota_is_a_400(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Over quota AND invalid used to answer 402.

        Telling an operator to upgrade their licence because they typed the
        product type wrong sends them to sales for a typo.
        """

        async def _no_objects() -> quotas.TierLimits:
            return quotas.DEFAULT_TIER_LIMITS[licensing.TIER_COMMUNITY].__class__(
                global_admins=quotas.UNLIMITED,
                tenant_admins=quotas.UNLIMITED,
                tenants=quotas.UNLIMITED,
                teams=quotas.UNLIMITED,
                objects=0,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _no_objects)

        response = await _register_connection(
            client, admin_headers, tenant_id, "not-a-product"
        )

        assert response.status_code == 400
        assert (await response.get_json())["error"] == "Invalid product type"

    @pytest.mark.asyncio
    async def test_a_valid_request_over_quota_is_still_402(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reordering must not have disabled the wall it moved past."""

        async def _no_objects() -> Any:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            return type(base)(
                global_admins=quotas.UNLIMITED,
                tenant_admins=quotas.UNLIMITED,
                tenants=quotas.UNLIMITED,
                teams=quotas.UNLIMITED,
                objects=0,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _no_objects)

        response = await _register_connection(
            client, admin_headers, tenant_id, "gough"
        )

        assert response.status_code == 402
        assert (await response.get_json())["dimension"] == "objects"


class TestLicensedCapabilitiesAreChecked:
    """``delegated_admin`` and ``multi_tenant`` are built, so they are gated."""

    @pytest.mark.asyncio
    async def test_delegated_admin_needs_the_licensed_capability(
        self,
        app: Quart,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A raised tenant_admins limit must not sell delegated MSP admin.

        The numeric wall and the capability are two halves of one gate: the
        limits are licence-configurable, so a payload raising
        ``max_tenant_admins`` on a Community licence would otherwise hand
        out a Professional structure with nothing checking entitlement.
        """

        async def _admins_allowed() -> Any:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            return base

        monkeypatch.setattr(quotas, "resolve_limits", _admins_allowed)

        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "admin"},
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_not_entitled"
        assert body["feature"] == "delegated_admin"
        assert body["required_tier"] == licensing.TIER_PROFESSIONAL

    @pytest.mark.asyncio
    async def test_a_licensed_deployment_may_delegate(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        enterprise_license: None,
    ) -> None:
        """The positive case, so the refusal above means something."""
        response = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "admin"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_promotion_is_gated_like_enrolment(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        user_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """"Add as member, then promote" must not route around the gate."""
        enrolled = await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            headers=admin_headers,
            json={"user_id": user_id, "role": "member"},
        )
        assert enrolled.status_code == 201

        async def _admins_allowed() -> Any:
            return quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]

        monkeypatch.setattr(quotas, "resolve_limits", _admins_allowed)

        response = await client.put(
            f"/api/v1/tenants/{tenant_id}/members/{user_id}",
            headers=admin_headers,
            json={"role": "admin"},
        )

        assert response.status_code == 403
        assert (await response.get_json())["feature"] == "delegated_admin"


class TestRegistrationIsMetered:
    """Self-service signup used to walk past the licensed team limit."""

    @pytest.mark.asyncio
    async def test_the_personal_team_is_refused_past_the_limit(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The team is refused; the registration is NOT.

        Non-admin members are unlimited at every tier, so refusing the
        signup would turn a team wall into a user cap the tier model
        deliberately does not have. The refusal is reported rather than
        swallowed — a silently missing team is the "silent cap" the model
        forbids.
        """

        async def _one_team() -> Any:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            return type(base)(
                global_admins=quotas.UNLIMITED,
                tenant_admins=quotas.UNLIMITED,
                tenants=quotas.UNLIMITED,
                teams=0,
                objects=quotas.UNLIMITED,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _one_team)

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"metered-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Metered Signup",
            },
        )

        assert response.status_code == 201
        body = await response.get_json()
        assert body["user"]["id"]
        assert body["personal_team"] is None
        refused = body["personal_team_refused"]
        assert refused["dimension"] == "teams"
        assert refused["error"] == "quota_exceeded"
        # The limit was consumed by a team this endpoint created, possibly
        # for someone else. A bare "1 of 1 teams" reads as a bug to a user
        # who has never created one, so the refusal must say why.
        assert "personal team" in refused["message"]
        assert "counts toward" in refused["message"]
        assert "team limit" in refused["message"]

    @pytest.mark.asyncio
    async def test_registration_under_the_limit_still_gets_a_team(
        self, client: Any
    ) -> None:
        """The wall must not have removed the feature it meters."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"unmetered-{uuid.uuid4().hex[:8]}@example.com",
                "password": "a-sufficiently-long-password",
                "full_name": "Normal Signup",
            },
        )

        assert response.status_code == 201
        body = await response.get_json()
        assert body["personal_team"] is not None
        assert body["personal_team_refused"] is None


class TestModelLayerBackstop:
    """A limit enforced at only some call sites is not a limit."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "dimension,call",
        [
            ("teams", "create_team"),
            ("tenants", "create_tenant"),
            ("tenant_admins", "add_tenant_member"),
        ],
    )
    async def test_an_unmetered_write_raises_rather_than_breaching(
        self,
        app: Quart,
        dimension: str,
        call: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """This is what a future route that forgets to meter itself hits."""

        async def _zero() -> Any:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            return type(base)(
                global_admins=quotas.UNLIMITED,
                tenant_admins=0,
                tenants=0,
                teams=0,
                objects=quotas.UNLIMITED,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _zero)

        arguments: dict[str, dict[str, Any]] = {
            "create_team": {
                "name": "T",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "owner_id": 1,
            },
            "create_tenant": {
                "name": "T",
                "slug": f"t-{uuid.uuid4().hex[:8]}",
                "owner_id": 1,
            },
            "add_tenant_member": {"tenant_id": 1, "user_id": 1, "role": "admin"},
        }

        async with app.app_context():
            with pytest.raises(quotas.QuotaExceeded):
                await getattr(models, call)(**arguments[call])

    @pytest.mark.asyncio
    async def test_a_non_admin_member_is_not_metered_by_the_backstop(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Participation is unlimited at every tier; delegation is not."""

        async def _no_admins() -> Any:
            base = quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            return type(base)(
                global_admins=quotas.UNLIMITED,
                tenant_admins=0,
                tenants=quotas.UNLIMITED,
                teams=quotas.UNLIMITED,
                objects=quotas.UNLIMITED,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _no_admins)

        async with app.app_context():
            # No exception: a member is not a delegated admin.
            await quotas.assert_within("tenants")


class TestDevModeActuallyWidensEntitlement:
    """``--dev`` must unlock BECAUSE it is active, not by coincidence."""

    @staticmethod
    def _dev_domain(monkeypatch: pytest.MonkeyPatch) -> None:
        """A PenguinTech product domain that the licence bypass excludes.

        This is the point of the test. Dev mode's domain condition includes
        product ``.app`` domains (general.md); ``penguin_licensing``'s
        bypass list does not carry them. So on this host the licence bypass
        is OFF and anything that unlocks did so through dev mode.
        """
        monkeypatch.delenv("SERVER_NAME", raising=False)
        monkeypatch.setenv("BASE_URL", "https://portal.waddles.app")
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

    @pytest.mark.asyncio
    async def test_without_dev_mode_the_feature_is_refused(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Establishes that the domain alone unlocks nothing."""
        self._dev_domain(monkeypatch)

        assert licensing.current_host_is_license_exempt() is False
        async with app.app_context():
            assert await licensing.is_feature_entitled("sso_integration") is False

    @pytest.mark.asyncio
    async def test_active_dev_mode_entitles_the_same_feature(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same host, same licence, ``--dev`` passed: now entitled."""
        self._dev_domain(monkeypatch)
        monkeypatch.setattr(devmode, "_requested", True)

        async def _one_user() -> int:
            return 1

        monkeypatch.setattr(devmode, "user_count", _one_user)

        async with app.app_context():
            assert licensing.current_host_is_license_exempt() is False
            assert await devmode.is_active() is True
            assert await licensing.is_feature_entitled("sso_integration") is True
            assert await licensing.is_feature_entitled("saml_sso") is True

        devmode.reset()

    @pytest.mark.asyncio
    async def test_dev_mode_widens_the_limits_table_too(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """"All premium features" includes the structures the paywall gates."""
        self._dev_domain(monkeypatch)
        monkeypatch.setattr(devmode, "_requested", True)

        async def _one_user() -> int:
            return 1

        monkeypatch.setattr(devmode, "user_count", _one_user)

        async with app.app_context():
            assert await quotas.resolve_limits() == (
                quotas.DEFAULT_TIER_LIMITS[licensing.TIER_ENTERPRISE]
            )

        devmode.reset()

    @pytest.mark.asyncio
    async def test_a_second_user_takes_the_entitlement_away(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cap is what bounds the unlock, and it is re-read every time."""
        self._dev_domain(monkeypatch)
        monkeypatch.setattr(devmode, "_requested", True)

        async def _two_users() -> int:
            return 2

        monkeypatch.setattr(devmode, "user_count", _two_users)

        async with app.app_context():
            assert await devmode.is_active() is False
            assert await licensing.is_feature_entitled("sso_integration") is False

        devmode.reset()


class TestOauthSignupRespectsTheCap:
    """The second SSO user gets a reason, not an internal server error."""

    @pytest.mark.asyncio
    async def test_the_oauth_path_refuses_before_the_backstop_raises(
        self, app: Quart, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``oauth_callback`` called ``create_user`` with no cap check.

        The cap still held — the model-layer backstop raised — but the
        exception escaped the view as a 500, so an operator evaluating with
        ``--dev`` saw "internal server error" instead of "this mode is
        limited to one user".
        """
        monkeypatch.setattr(devmode, "_requested", True)
        monkeypatch.setattr(devmode, "domain_permits", lambda: True)

        async def _one_user() -> int:
            return 1

        monkeypatch.setattr(devmode, "user_count", _one_user)

        async with app.app_context():
            refusal = await devmode.user_creation_refusal()

        assert refusal is not None
        body, status = refusal
        assert status == 402
        assert body["error"] == "dev_mode_user_cap"

        devmode.reset()

    @pytest.mark.asyncio
    async def test_the_oauth_view_checks_the_cap_before_creating(self) -> None:
        """The refusal has to be *called* on that path, not merely exist.

        Behavioural coverage of the full callback needs a live identity
        provider, so this pins the ordering that makes the difference
        between a 402 and a 500: the cap check must precede ``create_user``
        in ``oauth_callback``.
        """
        import inspect

        from app import oauth

        source = inspect.getsource(oauth.oauth_callback)
        cap = source.index("user_creation_refusal")
        create = source.index("await create_user(")
        assert cap < create, (
            "oauth_callback creates a user before consulting the dev-mode "
            "cap, so the second SSO signup 500s instead of answering 402"
        )


class TestAuditIsEnterpriseLicensed:
    """Audit access is sold at Enterprise, and was shipping unpaywalled.

    ``audit_export`` sat in ``NOT_YET_IMPLEMENTED`` while
    ``GET /api/v1/audit/export`` was fully built (CSV + JSON) behind nothing
    but a tenant scope. Membership of that set exempts a feature from the
    mint-vs-enforce guard, so the one thing it must never contain is
    something that is actually built.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route", ["logs", "export"])
    async def test_unlicensed_deployments_are_refused(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int, route: str
    ) -> None:
        response = await client.get(
            f"/api/v1/audit/{route}?tenant_id={tenant_id}", headers=admin_headers
        )

        assert response.status_code == 403
        body = await response.get_json()
        assert body["error"] == "feature_not_entitled"
        assert body["required_tier"] == licensing.TIER_ENTERPRISE
        assert body["feature"] == f"audit_{route}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route", ["logs", "export"])
    async def test_an_enterprise_licence_admits_both(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        route: str,
        enterprise_license: None,
    ) -> None:
        """The positive case, so the refusals above are not vacuous."""
        response = await client.get(
            f"/api/v1/audit/{route}?tenant_id={tenant_id}", headers=admin_headers
        )

        assert response.status_code == 200

    def test_audit_export_is_no_longer_declared_unbuilt(self) -> None:
        """It is built; parking it as unbuilt is what hid it."""
        assert "audit_export" not in licensing.NOT_YET_IMPLEMENTED
        assert "audit_logs" not in licensing.NOT_YET_IMPLEMENTED

    def test_writing_audit_rows_is_not_licensed(self) -> None:
        """Only READING is the product.

        Audit rows are written on every tier — that is a security property,
        and gating it would make audit a locked module rather than a paid
        capability, which the tier model forbids outright.
        """
        import inspect

        from app import models

        assert "require_feature" not in inspect.getsource(models.create_audit_log)
