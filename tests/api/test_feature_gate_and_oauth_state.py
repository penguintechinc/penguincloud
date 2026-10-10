"""Feature gating (I4) and OAuth CSRF state handling (I5).

I4 — middleware.require_feature and the former oauth.require_feature stub
both fell through to the wrapped view on every path, so decorating a route
with them documented an intent without enforcing anything.

I5 — oauth.validate_state_token read the session via `session.get_json()`,
a method Quart's session object does not have. The hasattr guard fell
through to an empty dict, so the function returned False unconditionally
and every OAuth callback 401'd; and the state was never consumed, so a
captured callback URL stayed replayable.
"""

import secrets
from typing import Any

import pytest
from quart import Quart


class TestFeatureGateFailsClosed:
    """I4: a gate that cannot resolve an entitlement must deny."""

    @pytest.mark.asyncio
    async def test_gated_route_is_denied(
        self, app: Quart, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A route behind require_feature 403s while the lookup is unbuilt."""
        from app.middleware import auth_required, require_feature, tenant_required

        @app.route("/api/v1/_test/gated")
        @tenant_required
        @require_feature("some_unbuilt_feature")
        @auth_required
        async def _gated() -> tuple[dict[str, str], int]:
            return {"reached": "yes"}, 200

        response = await client.get("/api/v1/_test/gated?tenant_id=1", headers=auth_headers)
        assert response.status_code in (400, 403)
        if response.status_code == 403:
            body = await response.get_json()
            assert body["error"] == "feature_not_entitled"
            assert "some_unbuilt_feature" in body["message"]
        # Either way the view body must never have run.
        assert "reached" not in repr(await response.get_json())

    @pytest.mark.asyncio
    async def test_gate_denies_before_running_the_view(
        self, app: Quart, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """The wrapped view is not executed when the gate denies."""
        executed: list[bool] = []

        from app.middleware import auth_required, require_feature

        @app.route("/api/v1/_test/gated-sideeffect")
        @require_feature("another_unbuilt_feature")
        @auth_required
        async def _gated_side_effect() -> tuple[dict[str, str], int]:
            executed.append(True)
            return {"ok": "yes"}, 200

        await client.get("/api/v1/_test/gated-sideeffect", headers=auth_headers)
        assert executed == [], "gated view ran despite the gate"


class TestOAuthFeatureGate:
    """SSO is a licensed feature, so its routes go through the real gate."""

    def test_oauth_uses_the_real_license_gate(self) -> None:
        """oauth.require_feature IS license.require_feature, not a local stub.

        The stub it replaced returned the view in both branches of its own
        `if`, so the decorator could never deny.
        """
        from app import license as license_module
        from app import oauth

        assert oauth.require_feature is license_module.require_feature

    @pytest.mark.asyncio
    async def test_oauth_route_denied_when_not_entitled(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With entitlement checking active and SSO absent, the route 403s."""
        from app.license import LicenseManager

        monkeypatch.setattr(LicenseManager, "is_feature_enabled", lambda self, feature: False)

        response = await client.get("/api/v1/auth/oauth/google")
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "feature_not_entitled"


class TestOAuthStateToken:
    """I5: state must validate correctly, and exactly once."""

    @pytest.mark.asyncio
    async def test_valid_state_passes(self, app: Quart) -> None:
        """A state matching the session value validates."""
        from app.oauth import validate_state_token
        from quart import session

        async with app.test_request_context("/callback"):
            state = secrets.token_urlsafe(32)
            session["oauth_state"] = state
            assert validate_state_token(state) is True

    @pytest.mark.asyncio
    async def test_replay_is_rejected(self, app: Quart) -> None:
        """The same state cannot be validated twice — it is consumed."""
        from app.oauth import validate_state_token
        from quart import session

        async with app.test_request_context("/callback"):
            state = secrets.token_urlsafe(32)
            session["oauth_state"] = state

            assert validate_state_token(state) is True
            assert validate_state_token(state) is False, "state was replayable"
            assert "oauth_state" not in session

    @pytest.mark.asyncio
    async def test_mismatched_state_rejected(self, app: Quart) -> None:
        """A state that does not match the stored value is refused."""
        from app.oauth import validate_state_token
        from quart import session

        async with app.test_request_context("/callback"):
            session["oauth_state"] = secrets.token_urlsafe(32)
            assert validate_state_token(secrets.token_urlsafe(32)) is False

    @pytest.mark.asyncio
    async def test_absent_session_state_rejected(self, app: Quart) -> None:
        """With nothing in the session there is nothing to match."""
        from app.oauth import validate_state_token

        async with app.test_request_context("/callback"):
            assert validate_state_token("anything") is False

    @pytest.mark.asyncio
    async def test_empty_presented_state_rejected(self, app: Quart) -> None:
        """An empty presented state never matches, even if one is stored."""
        from app.oauth import validate_state_token
        from quart import session

        async with app.test_request_context("/callback"):
            session["oauth_state"] = secrets.token_urlsafe(32)
            assert validate_state_token("") is False

    @pytest.mark.asyncio
    async def test_callback_rejects_missing_state(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The callback route refuses a request carrying no state."""
        from app.license import LicenseManager

        monkeypatch.setattr(LicenseManager, "is_feature_enabled", lambda self, feature: True)

        response = await client.get("/api/v1/auth/oauth/google/callback?code=abc")
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "Invalid state parameter"
