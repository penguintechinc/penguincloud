"""``GET /api/v1/features``: the contract the webui decodes.

The endpoint replaces a build-time seam (``featureGates.ts``'s hardcoded
map plus a ``VITE_ENABLE_PRODUCTS`` env override), so its response shape is
now the only thing standing between the portal's idea of what is enabled
and the browser's.

Two properties are load-bearing and asserted rather than assumed:

* **Every declared flag has a key, always.** A sparse "only the on ones"
  map forces the client to read an absent key as false, which makes "off"
  and "the response was not the shape I expected" indistinguishable — the
  absent-key-renders-as-none defect this repo has already shipped once.
* **It is authenticated.** The response enumerates every integrated product
  and every licensed capability; that map does not go to anonymous callers,
  for the same reason the full OpenAPI document does not.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import _FakeFlagServer

from app import devmode, flags, licensing


class TestAuthentication:
    """The commercial surface map is not published anonymously."""

    @pytest.mark.asyncio
    async def test_anonymous_is_rejected(self, client: Any) -> None:
        response = await client.get("/api/v1/features")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_any_authenticated_caller_may_read_it(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Not further scope-gated: a viewer must know what to render."""
        response = await client.get("/api/v1/features", headers=auth_headers)
        assert response.status_code == 200


class TestResponseShape:
    """The DTO, field by field."""

    @pytest.mark.asyncio
    async def test_every_declared_key_is_present(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert set(body) == {
            "flags",
            "tier",
            "tiers",
            "licensed_features",
            "dev_mode",
            "dev_mode_max_users",
            "limits",
        }

    @pytest.mark.asyncio
    async def test_flags_covers_every_declared_flag(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Complete, not sparse — the client must never infer from absence."""
        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert set(body["flags"]) == set(flags.KNOWN_FLAGS)
        assert all(isinstance(value, bool) for value in body["flags"].values())

    @pytest.mark.asyncio
    async def test_flags_default_off_with_no_flag_server(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unconfigured PostHog: everything off, nothing raised."""
        monkeypatch.delenv("POSTHOG_KEY", raising=False)
        flags.reset_client()

        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert response.status_code == 200
        assert not any(body["flags"].values())

    @pytest.mark.asyncio
    async def test_tier_and_ordering_are_published(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The UI must not keep a second copy of the tier ordering."""
        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert body["tiers"] == list(licensing.TIER_ORDER)
        assert body["tier"] in body["tiers"]

    @pytest.mark.asyncio
    async def test_licensed_features_map_matches_the_server_side_map(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Published so the UI can name the upgrade, not re-derive it."""
        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert body["licensed_features"] == dict(licensing.FEATURE_MIN_TIER)
        for tier in body["licensed_features"].values():
            assert tier in body["tiers"]

    @pytest.mark.asyncio
    async def test_dev_mode_is_false_by_default(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert body["dev_mode"] is False
        assert body["dev_mode_max_users"] == devmode.MAX_DEV_MODE_USERS


class TestLimitsArePublished:
    """The UI shows "1 of 1 tenants" BEFORE the operator hits a 402."""

    @pytest.mark.asyncio
    async def test_every_dimension_is_present(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        from app import quotas

        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert set(body["limits"]) == set(quotas.DIMENSIONS)
        assert all(isinstance(value, int) for value in body["limits"].values())

    @pytest.mark.asyncio
    async def test_limits_come_from_the_resolver_not_a_constant(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A licence may raise or lower any of them per deployment.

        Publishing a hardcoded table would be wrong for exactly the
        customers who negotiated a different number.
        """
        from app import quotas

        async def _custom() -> quotas.TierLimits:
            return quotas.TierLimits(
                global_admins=3,
                tenant_admins=7,
                tenants=2,
                teams=quotas.UNLIMITED,
                objects=5000,
            )

        monkeypatch.setattr(quotas, "resolve_limits", _custom)

        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert body["limits"]["tenant_admins"] == 7
        assert body["limits"]["objects"] == 5000
        assert body["limits"]["teams"] == quotas.UNLIMITED


class TestDevModeSignal:
    """The signal the persistent UI banner renders on."""

    @pytest.mark.asyncio
    async def test_signal_is_true_when_dev_mode_is_active(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _active() -> bool:
            return True

        monkeypatch.setattr(devmode, "is_active", _active)

        response = await client.get("/api/v1/features", headers=auth_headers)
        assert (await response.get_json())["dev_mode"] is True

    @pytest.mark.asyncio
    async def test_signal_is_recomputed_per_request(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No latch anywhere on the path, including in the response.

        A banner that stays up after dev mode deactivates is merely wrong;
        one that stays DOWN after it activates hides an unlicensed
        deployment from the operator looking at it.
        """
        # A mutable answer rather than a queue: dev mode is now consulted
        # more than once per request (the entitlement path asks it too), and
        # a queue would fail on the call count instead of on the latch this
        # test is about.
        state = {"active": True}

        async def _toggling() -> bool:
            return state["active"]

        monkeypatch.setattr(devmode, "is_active", _toggling)

        first = await client.get("/api/v1/features", headers=auth_headers)
        state["active"] = False
        second = await client.get("/api/v1/features", headers=auth_headers)

        assert (await first.get_json())["dev_mode"] is True
        assert (await second.get_json())["dev_mode"] is False


class TestFlagAndLicenceAreBothReported:
    """The UI needs both halves, because a feature needs both to ship."""

    @pytest.mark.asyncio
    async def test_a_flagged_but_unlicensed_feature_is_visible_as_such(
        self, client: Any, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag ON + community tier must be distinguishable from flag OFF.

        Reporting only a single "available" boolean would collapse "not
        rolled out yet" and "needs an upgrade" into one state, and the UI
        could only ever render one of the two messages.
        """
        # Turn every flag on at the SERVER, not by replacing the evaluator:
        # evaluate_all takes the bulk path, and patching the single-flag
        # function would leave this test asserting against code the endpoint
        # no longer calls.
        monkeypatch.setattr(flags, "_client", _FakeFlagServer(flags.KNOWN_FLAGS))
        monkeypatch.setattr(flags, "_client_built", True)
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        response = await client.get("/api/v1/features", headers=auth_headers)
        body = await response.get_json()

        assert body["flags"]["sso_integration"] is True
        assert body["tier"] == licensing.TIER_COMMUNITY
        assert body["licensed_features"]["sso_integration"] == (
            licensing.TIER_PROFESSIONAL
        )
