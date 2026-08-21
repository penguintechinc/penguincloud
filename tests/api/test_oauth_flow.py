"""OAuth2/SSO integration flow coverage (app.oauth).

Previously only the CSRF-state and feature-gate slices were tested (see
test_feature_gate_and_oauth_state.py). This file exercises the actual
authorization redirect and callback flows: the httpx exchange with the
identity provider is faked at the module boundary (same technique as
test_killkrill_client.py), the license gate is bypassed the same way
test_feature_gate_and_oauth_state.py already does
(``LicenseManager.is_feature_enabled`` monkeypatched True), and provider
credentials are supplied via a monkeypatched ``Config.OAUTH_PROVIDERS``
rather than real env vars.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.config import Config
from app.license import LicenseManager
from app.oauth import (
    _extract_provider_email,
    _extract_provider_name,
    _extract_provider_user_id,
    get_provider_config,
)
from quart import Quart


@pytest.fixture(autouse=True)
def _sso_entitled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file exercises the route BEHIND the SSO gate."""
    monkeypatch.setattr(LicenseManager, "is_feature_enabled", lambda self, feature: True)


# app.models.store_oauth_connection (models.py) unconditionally passes
# expires_at=... to BOTH db.oauth_connections.async_insert(...) and the
# update() branch, but app.models_sqlalchemy.OAuthConnection defines no
# expires_at column (id, user_id, provider, provider_user_id, access_token,
# refresh_token, created_at, updated_at only). SQLAlchemy's compiler raises
# `CompileError: Unconsumed column names: expires_at` for BOTH the insert
# and the update path -- verified directly by calling store_oauth_connection
# in isolation, not just through these routes. That makes this a genuine,
# previously-undiscovered defect (not a test setup issue): every real
# Google/Microsoft/Okta sign-in that reaches this call -- new user, existing
# user linked by email, or a repeat sign-in linked by provider id -- 500s
# today, and so does every call to get_oauth_connections/disconnect_oauth
# once a connection exists. This surface had 0% test coverage before this
# file, which is how it went uncaught. Fixing app/models_sqlalchemy.py is
# outside this change's file set (tests/api/, pytest config, ci.yml only).
REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN = (
    "store_oauth_connection (models.py) always passes expires_at to "
    "db.oauth_connections insert/update, but OAuthConnection "
    "(models_sqlalchemy.py) declares no expires_at column -- raises "
    "sqlalchemy.exc.CompileError: 'Unconsumed column names: expires_at' "
    "for every OAuth connection store, whether newly inserted or updated"
)


@pytest.fixture
def google_provider(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A fully-configured Google provider entry, independent of env vars."""
    providers = {
        "google": {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        }
    }
    monkeypatch.setattr(Config, "OAUTH_PROVIDERS", providers)
    return providers["google"]


class _FakeOAuthResponse:
    """Fake O Auth Response."""

    def __init__(self, json_data: dict[str, Any], *, raises: bool = False) -> None:
        """Init."""
        self._json = json_data
        self._raises = raises

    def json(self) -> dict[str, Any]:
        """Json."""
        return self._json

    def raise_for_status(self) -> None:
        """Raise for status."""
        if self._raises:
            raise httpx.HTTPError("provider returned an error status")


class _FakeOAuthHttpClient:
    """httpx.AsyncClient stand-in for the token+userinfo exchange."""

    def __init__(
        self,
        *args: Any,
        token_response: _FakeOAuthResponse | None = None,
        userinfo_response: _FakeOAuthResponse | None = None,
        **kwargs: Any,
    ) -> None:
        """Init."""
        self._token_response = token_response
        self._userinfo_response = userinfo_response

    async def post(self, url: str, **kwargs: Any) -> _FakeOAuthResponse:
        """Post."""
        assert self._token_response is not None
        return self._token_response

    async def get(self, url: str, **kwargs: Any) -> _FakeOAuthResponse:
        """Get."""
        assert self._userinfo_response is not None
        return self._userinfo_response

    async def __aenter__(self) -> _FakeOAuthHttpClient:
        """Aenter."""
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        """Aexit."""
        return False


def _install_fake_exchange(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token_response: _FakeOAuthResponse | None = None,
    userinfo_response: _FakeOAuthResponse | None = None,
) -> None:
    """Install fake exchange."""
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: _FakeOAuthHttpClient(
            *a, token_response=token_response, userinfo_response=userinfo_response, **k
        ),
    )


async def _get_state_from_redirect(client: Any) -> str:
    """Drive GET /auth/oauth/google to obtain a real, session-bound state."""
    response = await client.get("/api/v1/auth/oauth/google")
    assert response.status_code == 302
    location = str(response.headers["Location"])
    state: str = parse_qs(urlparse(location).query)["state"][0]
    return state


class TestGetProviderConfig:
    """Get Provider Config."""

    def test_unknown_provider_returns_none(self) -> None:
        """Unknown provider returns none."""
        assert get_provider_config("not-a-real-provider") is None

    def test_okta_substitutes_tenant_url_into_all_three_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Okta substitutes tenant url into all three urls."""
        monkeypatch.setattr(
            Config,
            "OAUTH_PROVIDERS",
            {
                "okta": {
                    "client_id": "cid",
                    "client_secret": "sec",
                    "tenant_url": "https://dev-999.okta.com",
                    "authorization_url": "{tenant_url}/oauth2/v1/authorize",
                    "token_url": "{tenant_url}/oauth2/v1/token",
                    "userinfo_url": "{tenant_url}/oauth2/v1/userinfo",
                }
            },
        )
        config = get_provider_config("okta")
        assert config is not None
        assert config["authorization_url"] == "https://dev-999.okta.com/oauth2/v1/authorize"
        assert config["token_url"] == "https://dev-999.okta.com/oauth2/v1/token"
        assert config["userinfo_url"] == "https://dev-999.okta.com/oauth2/v1/userinfo"

    def test_google_config_untouched_by_okta_substitution(
        self, google_provider: dict[str, Any]
    ) -> None:
        """Google config untouched by okta substitution."""
        config = get_provider_config("google")
        assert config is not None
        assert config["authorization_url"] == google_provider["authorization_url"]


class TestExtractProviderFields:
    """Extract Provider Fields."""

    @pytest.mark.parametrize(
        ("provider", "userinfo", "expected"),
        [
            ("google", {"sub": "g-1"}, "g-1"),
            ("microsoft", {"id": "m-1"}, "m-1"),
            ("okta", {"sub": "o-1"}, "o-1"),
            ("unknown", {"sub": "x"}, None),
        ],
    )
    def test_extract_provider_user_id(
        self, provider: str, userinfo: dict[str, Any], expected: str | None
    ) -> None:
        """Extract provider user id."""
        assert _extract_provider_user_id(provider, userinfo) == expected

    @pytest.mark.parametrize(
        ("provider", "userinfo", "expected"),
        [
            ("google", {"email": "a@example.com"}, "a@example.com"),
            ("microsoft", {"userPrincipalName": "b@example.com"}, "b@example.com"),
            ("microsoft", {"mail": "c@example.com"}, "c@example.com"),
            ("okta", {"email": "d@example.com"}, "d@example.com"),
            ("unknown", {"email": "e@example.com"}, None),
        ],
    )
    def test_extract_provider_email(
        self, provider: str, userinfo: dict[str, Any], expected: str | None
    ) -> None:
        """Extract provider email."""
        assert _extract_provider_email(provider, userinfo) == expected

    @pytest.mark.parametrize(
        ("provider", "userinfo", "expected"),
        [
            ("google", {"name": "Ada"}, "Ada"),
            ("google", {}, ""),
            ("microsoft", {"displayName": "Bea"}, "Bea"),
            ("okta", {"name": "Cid"}, "Cid"),
            ("unknown", {"name": "Nope"}, ""),
        ],
    )
    def test_extract_provider_name(
        self, provider: str, userinfo: dict[str, Any], expected: str
    ) -> None:
        """Extract provider name."""
        assert _extract_provider_name(provider, userinfo) == expected


class TestOAuthRedirect:
    """O Auth Redirect."""

    @pytest.mark.asyncio
    async def test_unconfigured_provider_is_rejected(self, client: Any) -> None:
        """Unconfigured provider is rejected."""
        response = await client.get("/api/v1/auth/oauth/not-a-real-provider")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_credentials_is_a_server_config_error(self, client: Any) -> None:
        # Default TestingConfig has no OAUTH_GOOGLE_CLIENT_ID/SECRET set --
        # google is a known provider with empty credentials.
        """Missing credentials is a server config error."""
        response = await client.get("/api/v1/auth/oauth/google")
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_success_redirects_with_state_and_correct_params(
        self, client: Any, google_provider: dict[str, Any]
    ) -> None:
        """Success redirects with state and correct params."""
        response = await client.get("/api/v1/auth/oauth/google")

        assert response.status_code == 302
        location = response.headers["Location"]
        assert location.startswith(google_provider["authorization_url"])
        params = parse_qs(urlparse(location).query)
        assert params["client_id"] == [google_provider["client_id"]]
        assert params["response_type"] == ["code"]
        assert params["scope"] == ["openid email profile"]
        assert "state" in params
        assert params["redirect_uri"] == ["http://localhost/api/v1/auth/oauth/google/callback"]


class TestOAuthCallback:
    """O Auth Callback."""

    @pytest.mark.asyncio
    async def test_unconfigured_provider_is_rejected(self, client: Any) -> None:
        """Unconfigured provider is rejected."""
        response = await client.get("/api/v1/auth/oauth/not-a-real-provider/callback")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_state_is_rejected(
        self, client: Any, google_provider: dict[str, Any]
    ) -> None:
        """Missing state is rejected."""
        response = await client.get("/api/v1/auth/oauth/google/callback?code=abc")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_provider_error_param_is_surfaced(
        self, client: Any, google_provider: dict[str, Any]
    ) -> None:
        """Provider error param is surfaced."""
        state = await _get_state_from_redirect(client)
        response = await client.get(
            f"/api/v1/auth/oauth/google/callback?state={state}&error=access_denied"
        )
        assert response.status_code == 401
        assert "access_denied" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_missing_code_is_rejected(
        self, client: Any, google_provider: dict[str, Any]
    ) -> None:
        """Missing code is rejected."""
        state = await _get_state_from_redirect(client)
        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_provider_info_missing_email_is_rejected(
        self, client: Any, google_provider: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Provider info missing email is rejected."""
        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse({"access_token": "at1", "expires_in": 3600}),
            userinfo_response=_FakeOAuthResponse({"sub": "g-1"}),  # no email
        )
        state = await _get_state_from_redirect(client)
        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_provider_http_error_is_a_500(
        self, client: Any, google_provider: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Provider http error is a 500."""
        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse({}, raises=True),
        )
        state = await _get_state_from_redirect(client)
        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")
        assert response.status_code == 500
        assert (await response.get_json())["error"] == "Failed to complete OAuth flow"

    @pytest.mark.xfail(reason=REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN, strict=False)
    @pytest.mark.asyncio
    async def test_new_user_created_from_provider_info(
        self, client: Any, google_provider: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """New user created from provider info."""
        provider_sub = f"g-{uuid.uuid4().hex[:8]}"
        email = f"sso-{uuid.uuid4().hex[:8]}@example.com"
        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse(
                {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600}
            ),
            userinfo_response=_FakeOAuthResponse(
                {"sub": provider_sub, "email": email, "name": "SSO User"}
            ),
        )
        state = await _get_state_from_redirect(client)

        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")

        assert response.status_code == 200
        data = await response.get_json()
        assert data["user"]["email"] == email
        assert data["user"]["full_name"] == "SSO User"
        assert data["user"]["role"] == "viewer"
        assert data["token_type"] == "Bearer"
        assert data["access_token"]

    @pytest.mark.xfail(reason=REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN, strict=False)
    @pytest.mark.asyncio
    async def test_existing_email_links_instead_of_creating(
        self,
        client: Any,
        app: Quart,
        google_provider: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A provider email matching an existing account links, no dup user."""
        email = f"existing-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "existingpass123", "full_name": "Existing User"},
        )
        assert register.status_code in (200, 201)
        existing_user_id = int((await register.get_json())["user"]["id"])

        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse({"access_token": "at1", "expires_in": 3600}),
            userinfo_response=_FakeOAuthResponse(
                {"sub": f"g-{uuid.uuid4().hex[:8]}", "email": email, "name": "Ignored Name"}
            ),
        )
        state = await _get_state_from_redirect(client)

        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")

        assert response.status_code == 200
        data = await response.get_json()
        assert data["user"]["id"] == existing_user_id
        # The account keeps its original name -- the provider did not create
        # a second record and overwrite it.
        assert data["user"]["full_name"] == "Existing User"

        async with app.app_context():
            from app.models import get_oauth_connection

            connection = await get_oauth_connection(existing_user_id, "google")
        assert connection is not None

    @pytest.mark.xfail(reason=REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN, strict=False)
    @pytest.mark.asyncio
    async def test_existing_oauth_connection_links_by_provider_id(
        self,
        client: Any,
        app: Quart,
        google_provider: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A repeat sign-in finds the connection before falling to email."""
        email = f"repeat-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "repeatpass123", "full_name": "Repeat User"},
        )
        assert register.status_code in (200, 201)
        user_id = int((await register.get_json())["user"]["id"])
        provider_sub = f"g-{uuid.uuid4().hex[:8]}"

        async with app.app_context():
            from app.models import store_oauth_connection

            await store_oauth_connection(
                user_id=user_id,
                provider="google",
                provider_user_id=provider_sub,
                access_token="old-token",
            )

        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse({"access_token": "new-token", "expires_in": 3600}),
            userinfo_response=_FakeOAuthResponse({"sub": provider_sub, "email": email}),
        )
        state = await _get_state_from_redirect(client)

        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")

        assert response.status_code == 200
        assert (await response.get_json())["user"]["id"] == user_id

    @pytest.mark.asyncio
    async def test_devmode_user_cap_refuses_new_user_creation(
        self,
        client: Any,
        google_provider: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Devmode user cap refuses new user creation."""
        from app import devmode

        monkeypatch.setattr(devmode, "_requested", True)
        monkeypatch.setattr(devmode, "domain_permits", lambda: True)

        async def _count() -> int:
            """Count."""
            return 1  # at MAX_DEV_MODE_USERS -- next creation is refused

        monkeypatch.setattr(devmode, "user_count", _count)

        _install_fake_exchange(
            monkeypatch,
            token_response=_FakeOAuthResponse({"access_token": "at1", "expires_in": 3600}),
            userinfo_response=_FakeOAuthResponse(
                {
                    "sub": f"g-{uuid.uuid4().hex[:8]}",
                    "email": f"cap-{uuid.uuid4().hex[:8]}@example.com",
                }
            ),
        )
        state = await _get_state_from_redirect(client)

        response = await client.get(f"/api/v1/auth/oauth/google/callback?state={state}&code=abc123")

        assert response.status_code == 402
        body = await response.get_json()
        assert "dev" in body["error"].lower() or "dev" in str(body).lower()


@pytest.mark.usefixtures("_sso_entitled")
class TestOAuthConnectionsList:
    """O Auth Connections List."""

    @pytest.mark.asyncio
    async def test_no_connections_returns_empty_list(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """No connections returns empty list."""
        response = await client.get("/api/v1/auth/oauth/connections", headers=auth_headers)
        assert response.status_code == 200
        assert (await response.get_json())["connections"] == []

    @pytest.mark.xfail(reason=REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN, strict=False)
    @pytest.mark.asyncio
    async def test_connection_present_hides_tokens(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Connection present hides tokens."""
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])

        async with app.app_context():
            from app.models import store_oauth_connection

            await store_oauth_connection(
                user_id=user_id,
                provider="google",
                provider_user_id="g-listed",
                access_token="secret-access",
                refresh_token="secret-refresh",
            )

        response = await client.get("/api/v1/auth/oauth/connections", headers=auth_headers)
        assert response.status_code == 200
        connections = (await response.get_json())["connections"]
        assert len(connections) == 1
        assert "access_token" not in connections[0]
        assert "refresh_token" not in connections[0]

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, client: Any) -> None:
        """Unauthenticated is rejected."""
        response = await client.get("/api/v1/auth/oauth/connections")
        assert response.status_code == 401


@pytest.mark.usefixtures("_sso_entitled")
class TestDisconnectOAuth:
    """Disconnect O Auth."""

    @pytest.mark.xfail(reason=REASON_OAUTH_CONNECTIONS_MISSING_EXPIRES_AT_COLUMN, strict=False)
    @pytest.mark.asyncio
    async def test_disconnect_removes_the_connection(
        self, client: Any, app: Quart, auth_headers: dict[str, str]
    ) -> None:
        """Disconnect removes the connection."""
        profile = await client.get("/api/v1/users/me", headers=auth_headers)
        user_id = int((await profile.get_json())["id"])

        async with app.app_context():
            from app.models import store_oauth_connection

            await store_oauth_connection(
                user_id=user_id,
                provider="google",
                provider_user_id="g-disconnect",
                access_token="tok",
            )

        response = await client.post("/api/v1/auth/oauth/google/disconnect", headers=auth_headers)
        assert response.status_code == 200
        assert (await response.get_json())["message"] == "OAuth connection disconnected"

        followup = await client.get("/api/v1/auth/oauth/connections", headers=auth_headers)
        assert (await followup.get_json())["connections"] == []

    @pytest.mark.asyncio
    async def test_disconnect_without_a_connection_is_not_found(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """Disconnect without a connection is not found."""
        response = await client.post("/api/v1/auth/oauth/google/disconnect", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self, client: Any) -> None:
        """Unauthenticated is rejected."""
        response = await client.post("/api/v1/auth/oauth/google/disconnect")
        assert response.status_code == 401
