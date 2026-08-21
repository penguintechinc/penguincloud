"""Authentication endpoint and auth_required middleware tests.

conftest.py cites this module as the place auth_required's verification is
covered ("tests/api/test_auth.py covers that path") — it did not exist.
This makes that citation true.

Covers both directions of the middleware: a genuine access token is
accepted, and every way a token can be wrong is refused with 401 —
including the token-type confusion that penguin-aaa's issue_token_set
makes possible, since it mints access and id tokens from one base payload
with the same issuer, audience and signing key.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt
import pytest
from quart import Quart

PROTECTED_ROUTE = "/api/v1/auth/me"
PASSWORD = "authtestpass123"


async def _register(client: Any, **overrides: Any) -> tuple[str, Any]:
    """Register a unique user; return (email, response)."""
    email = overrides.pop("email", f"authtest-{uuid.uuid4().hex[:8]}@example.com")
    payload = {"email": email, "password": PASSWORD, "full_name": "Auth Test"}
    payload.update(overrides)
    return email, await client.post("/api/v1/auth/register", json=payload)


def _signing_material(app: Quart) -> tuple[Any, str, dict[str, Any]]:
    """Return (signing_key, kid, config) for minting test tokens.

    Tokens are signed with the app's real key so these tests exercise the
    claim checks rather than stopping at signature verification — a token
    rejected for a bad signature would prove nothing about issuer,
    audience, expiry or token-type handling.

    Reaches into OIDCProvider._keystore because penguin-aaa exposes only
    the public JWKS (oidc.jwks()); there is no public accessor for the
    private signing key, by design. Test-only.
    """
    oidc = app.extensions["oidc_provider"]
    signing_key, kid = oidc._keystore.get_signing_key()
    return signing_key, kid, app.config


def _mint(app: Quart, **claim_overrides: Any) -> str:
    """Mint a token signed by the app's keystore, with claims overridden."""
    signing_key, kid, config = _signing_material(app)
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": "1",
        "iss": config["JWT_ISSUER"],
        "aud": list(config["JWT_AUDIENCES"]),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "scope": ["read", "write"],
        "roles": ["viewer"],
        "tenant": "unscoped",
        "teams": [],
        "token_use": "access",
    }
    claims.update(claim_overrides)
    return pyjwt.encode(
        claims, signing_key, algorithm=config["JWT_ALGORITHM"], headers={"kid": kid}
    )


class TestRegisterAndLogin:
    """Happy paths for the two unauthenticated endpoints."""

    @pytest.mark.asyncio
    async def test_register_creates_user_and_personal_team(self, client: Any) -> None:
        """Registration returns the new user plus its personal team."""
        email, response = await _register(client)
        assert response.status_code == 201

        body = await response.get_json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "viewer"
        assert body["personal_team"]["id"]
        # A registration response must never echo credential material.
        assert "password" not in repr(body)
        assert "password_hash" not in repr(body)

    @pytest.mark.asyncio
    async def test_register_rejects_duplicate_email(self, client: Any) -> None:
        """A second registration for the same address is a 409."""
        email, first = await _register(client)
        assert first.status_code == 201

        _, second = await _register(client, email=email)
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_register_rejects_short_password(self, client: Any) -> None:
        """Passwords under 8 characters are refused."""
        _, response = await _register(client, password="short")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_login_returns_token_and_profile(self, client: Any) -> None:
        """Login returns a usable token set and the caller's profile."""
        email, _ = await _register(client)

        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200

        body = await response.get_json()
        assert body["token_type"] == "Bearer"
        assert body["access_token"]
        assert body["user"]["email"] == email
        assert "password_hash" not in repr(body)

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self, client: Any) -> None:
        """A bad password is a 401 with no user enumeration hint."""
        email, _ = await _register(client)

        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrongpassword"}
        )
        assert response.status_code == 401

        unknown = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        assert unknown.status_code == 401
        # Same body either way — a wrong password and an unknown account
        # must be indistinguishable.
        assert (await response.get_json()) == (await unknown.get_json())


class TestAuthRequiredAccepts:
    """The accept path."""

    @pytest.mark.asyncio
    async def test_valid_access_token_is_accepted(
        self, client: Any, auth_headers: dict[str, str]
    ) -> None:
        """A token minted by login authenticates a protected route."""
        response = await client.get(PROTECTED_ROUTE, headers=auth_headers)
        assert response.status_code == 200
        assert (await response.get_json())["email"]


class TestAuthRequiredRejects:
    """Every way a presented token can be wrong."""

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, client: Any) -> None:
        """No Authorization header at all."""
        assert (await client.get(PROTECTED_ROUTE)).status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_rejected(self, client: Any) -> None:
        """A non-Bearer scheme is not accepted."""
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_rejected(self, client: Any) -> None:
        """A token that is not a JWT at all."""
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bad_signature_rejected(self, app: Quart, client: Any) -> None:
        """Correct claims, wrong signing key."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        _, kid, config = _signing_material(app)
        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        forged = pyjwt.encode(
            {
                "sub": "1",
                "iss": config["JWT_ISSUER"],
                "aud": list(config["JWT_AUDIENCES"]),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "scope": ["read"],
                "roles": ["admin"],
                "tenant": "unscoped",
                "teams": [],
                "token_use": "access",
            },
            attacker_key,
            algorithm="RS256",
            headers={"kid": kid},
        )

        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_issuer_rejected(self, app: Quart, client: Any) -> None:
        """Correctly signed but issued by someone else."""
        token = _mint(app, iss="https://evil.example.com")
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self, app: Quart, client: Any) -> None:
        """Correctly signed but minted for a different audience."""
        token = _mint(app, aud=["some-other-service"])
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, app: Quart, client: Any) -> None:
        """A token past its exp is refused."""
        past = datetime.now(UTC) - timedelta(hours=2)
        token = _mint(
            app,
            iat=int(past.timestamp()),
            exp=int((past + timedelta(hours=1)).timestamp()),
        )
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_kid_rejected(self, app: Quart, client: Any) -> None:
        """A kid that is not in the JWKS cannot be resolved to a key."""
        _, _, config = _signing_material(app)
        from cryptography.hazmat.primitives.asymmetric import rsa

        now = datetime.now(UTC)
        token = pyjwt.encode(
            {
                "sub": "1",
                "iss": config["JWT_ISSUER"],
                "aud": list(config["JWT_AUDIENCES"]),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "tenant": "unscoped",
                "token_use": "access",
            },
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            algorithm="RS256",
            headers={"kid": "no-such-key-id"},
        )
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_tenant_claim_rejected(self, app: Quart, client: Any) -> None:
        """security.md requires a tenant claim on every token."""
        token = _mint(app, tenant="")
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_sub_claim_rejected(self, app: Quart, client: Any) -> None:
        """A token with no subject identifies nobody."""
        token = _mint(app, sub="")
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestTokenTypeConfusion:
    """I3: only an access token may authenticate a protected route.

    issue_token_set mints access and id tokens from one base payload with
    the same iss, aud and signing key. `token_use` is the only thing
    telling them apart, so without an explicit check an id token — which
    clients treat as freely shareable profile data — authenticates
    everywhere an access token does.
    """

    @pytest.mark.asyncio
    async def test_id_token_rejected_on_protected_route(self, app: Quart, client: Any) -> None:
        """The real id token from issue_token_set is refused."""
        async with app.app_context():
            from app.auth import create_token_set_async
            from app.models import create_user

            user = await create_user(
                email=f"idtoken-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="x",
                full_name="Id Token User",
                role="viewer",
            )
            assert user is not None
            token_set = await create_token_set_async(user["id"], tenant_id="", role="viewer")

        # Sanity: the access token from the same set IS accepted, so the
        # rejection below is about token type and nothing else.
        ok = await client.get(
            PROTECTED_ROUTE,
            headers={"Authorization": f"Bearer {token_set['access_token']}"},
        )
        assert ok.status_code == 200

        response = await client.get(
            PROTECTED_ROUTE,
            headers={"Authorization": f"Bearer {token_set['id_token']}"},
        )
        assert response.status_code == 401
        assert "token type" in (await response.get_json())["error"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_rejected_on_protected_route(self, client: Any) -> None:
        """An opaque refresh token is not a bearer credential."""
        email, _ = await _register(client)
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        refresh_token = (await login.get_json())["refresh_token"]

        response = await client.get(
            PROTECTED_ROUTE, headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_without_token_use_rejected(self, app: Quart, client: Any) -> None:
        """A token omitting token_use fails closed rather than defaulting."""
        signing_key, kid, config = _signing_material(app)
        now = datetime.now(UTC)
        token = pyjwt.encode(
            {
                "sub": "1",
                "iss": config["JWT_ISSUER"],
                "aud": list(config["JWT_AUDIENCES"]),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "tenant": "unscoped",
            },
            signing_key,
            algorithm=config["JWT_ALGORITHM"],
            headers={"kid": kid},
        )
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestErrorDisclosure:
    """Verification failures must not describe themselves to the caller."""

    @pytest.mark.asyncio
    async def test_rejection_does_not_leak_exception_detail(self, app: Quart, client: Any) -> None:
        """The 401 body is generic — no PyJWT exception text echoed out."""
        token = _mint(app, aud=["some-other-service"])
        response = await client.get(PROTECTED_ROUTE, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

        error = (await response.get_json())["error"]
        assert error == "Invalid token"
        for leak in ("audience", "Audience", "signature", "PyJWT", "iss", "verify"):
            assert leak not in error
