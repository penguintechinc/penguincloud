"""Tests for `pcli.auth.tokens`."""

from __future__ import annotations

import base64
import json
import time

from pcli.auth.tokens import TenantContext, TokenSet, decode_jwt_claims


def test_token_set_round_trips_through_json() -> None:
    """Token set round trips through json."""
    tenant = TenantContext(id=7, slug="acme", name="Acme")
    original = TokenSet(
        access_token="access-123",  # noqa: S106
        refresh_token="refresh-456",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=1_700_000_000.0,
        tenant=tenant,
        scope=("products:read", "products:manage"),
    )
    restored = TokenSet.from_json(original.to_json())
    assert restored == original


def test_token_set_without_tenant_round_trips() -> None:
    """Token set without tenant round trips."""
    original = TokenSet(
        access_token="access-123",  # noqa: S106
        refresh_token="",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=1_700_000_000.0,
    )
    restored = TokenSet.from_json(original.to_json())
    assert restored.tenant is None
    assert restored.scope == ()


def test_is_expired_true_past_expiry() -> None:
    """Is expired true past expiry."""
    token = TokenSet(
        access_token="a",  # noqa: S106
        refresh_token="r",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=time.time() - 10,
    )
    assert token.is_expired is True


def test_is_expired_true_within_skew_window() -> None:
    """A token expiring in 5s (less than the 30s skew) counts as expired already."""
    token = TokenSet(
        access_token="a",  # noqa: S106
        refresh_token="r",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=time.time() + 5,
    )
    assert token.is_expired is True


def test_is_expired_false_comfortably_in_future() -> None:
    """Is expired false comfortably in future."""
    token = TokenSet(
        access_token="a",  # noqa: S106
        refresh_token="r",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=time.time() + 3600,
    )
    assert token.is_expired is False


def test_authorization_header() -> None:
    """Authorization header."""
    token = TokenSet(
        access_token="tok",  # noqa: S106
        refresh_token="",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=0,
    )
    assert token.authorization_header == "Bearer tok"


def test_with_tenant_returns_new_scoped_copy() -> None:
    """With tenant returns new scoped copy."""
    original = TokenSet(
        access_token="a",  # noqa: S106
        refresh_token="r",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=123.0,
    )
    tenant = TenantContext(id=1, slug="s", name="S")
    scoped = original.with_tenant(tenant)
    assert scoped.tenant == tenant
    assert original.tenant is None  # original untouched
    assert scoped.access_token == original.access_token


def test_from_login_response_computes_absolute_expiry() -> None:
    """From login response computes absolute expiry."""
    body = {
        "access_token": "at",
        "refresh_token": "rt",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    token = TokenSet.from_login_response(body, issued_at=1_000_000.0)
    assert token.expires_at == 1_003_600.0
    assert token.tenant is None


def test_from_login_response_attaches_tenant() -> None:
    """From login response attaches tenant."""
    body = {"access_token": "at", "refresh_token": "rt", "token_type": "Bearer", "expires_in": 60}
    tenant = TenantContext(id=9, slug="x", name="X")
    token = TokenSet.from_login_response(body, tenant=tenant)
    assert token.tenant == tenant


def _jwt_with_payload(payload: dict[str, object]) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.signature"


def test_decode_jwt_claims_reads_payload() -> None:
    """Decode jwt claims reads payload."""
    token = _jwt_with_payload({"tenant": 5, "scope": ["a:read"]})
    claims = decode_jwt_claims(token)
    assert claims == {"tenant": 5, "scope": ["a:read"]}


def test_decode_jwt_claims_degrades_to_empty_on_malformed_token() -> None:
    """Decode jwt claims degrades to empty on malformed token."""
    assert decode_jwt_claims("not-a-jwt") == {}
    assert decode_jwt_claims("") == {}
    assert decode_jwt_claims("a.b") == {}


def test_decode_jwt_claims_degrades_to_empty_on_non_json_payload() -> None:
    """Decode jwt claims degrades to empty on non json payload."""
    bogus_payload = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
    assert decode_jwt_claims(f"header.{bogus_payload}.sig") == {}


def test_decode_jwt_claims_never_used_for_authorization_by_construction() -> None:
    """A tampered/garbage claim set decodes without error -- it's display-only.

    Guards the module docstring's promise: nothing downstream can be
    tricked into treating this as a verified claim, because the function
    performs no signature check at all (there is nothing to bypass).
    """
    forged = _jwt_with_payload({"scope": ["admin:*"], "tenant": 999999})
    claims = decode_jwt_claims(forged)
    assert claims["tenant"] == 999999  # decoded verbatim, unverified -- by design
