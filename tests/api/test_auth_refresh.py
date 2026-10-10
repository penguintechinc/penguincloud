"""HTTP-layer tests for refresh token rotation, logout and session listing.

POST /api/v1/auth/refresh was a 501 stub after the Quart migration, which
left the whole refresh-token surface dead: login never stored a token, so
`tokens_revoked` on logout was always 0 and /auth/sessions was always [].

These are the HTTP-layer siblings of the three model-layer regression tests
in test_auth_extended.py (expired / revoked / valid) — that file proves
is_refresh_token_valid enforces the rules, this one proves the endpoint
actually consults it.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

PASSWORD = "refreshpass123"


async def _register_and_login(client: Any) -> tuple[int, dict[str, Any]]:
    """Register a fresh user and log in; return (user_id, login body)."""
    email = f"refresh-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Refresh User"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    user_id = int((await register.get_json())["user"]["id"])

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, await login.get_json()
    body: dict[str, Any] = await login.get_json()
    return user_id, body


@pytest.mark.asyncio
async def test_login_returns_a_refresh_token(client: Any) -> None:
    """Login issues a refresh token alongside the access token."""
    _, login = await _register_and_login(client)
    assert login["refresh_token"]
    assert login["access_token"] != login["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rotates_and_returns_a_new_pair(client: Any) -> None:
    """A valid refresh token is exchanged for a brand new pair."""
    _, login = await _register_and_login(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert response.status_code == 200, await response.get_json()

    body = await response.get_json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    # Rotation, not reissue of the same value.
    assert body["refresh_token"] != login["refresh_token"]


@pytest.mark.asyncio
async def test_refreshed_access_token_is_usable(client: Any) -> None:
    """The access token handed back by refresh authenticates a real route."""
    _, login = await _register_and_login(client)

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    new_access = (await refreshed.get_json())["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_reuse_after_rotation_is_rejected(client: Any) -> None:
    """Replaying a rotated refresh token fails — rotation is single-use."""
    _, login = await _register_and_login(client)
    original = login["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401
    assert "Invalid or expired" in (await replay.get_json())["error"]


@pytest.mark.asyncio
async def test_rotated_successor_still_works(client: Any) -> None:
    """Rotation chains: each new token refreshes once in turn."""
    _, login = await _register_and_login(client)

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    second_token = (await first.get_json())["refresh_token"]

    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": second_token})
    assert second.status_code == 200
    assert (await second.get_json())["refresh_token"] not in (
        login["refresh_token"],
        second_token,
    )


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(app: Any, client: Any) -> None:
    """A stored token past its expires_at cannot be exchanged."""
    user_id, _ = await _register_and_login(client)

    expired_token = f"expired-{uuid.uuid4().hex}"
    async with app.app_context():
        from app.models import store_refresh_token

        await store_refresh_token(
            user_id=user_id,
            token_hash=hashlib.sha256(expired_token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": expired_token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unknown_refresh_token_is_rejected(client: Any) -> None:
    """A token that was never issued is rejected."""
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "never-issued-token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_requires_a_token(client: Any) -> None:
    """Missing body or missing token is a 400, not a 500."""
    assert (await client.post("/api/v1/auth/refresh", json={})).status_code == 400
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
    ).status_code == 400


@pytest.mark.asyncio
async def test_refresh_rejection_does_not_disclose_token_state(client: Any) -> None:
    """Unknown, revoked and expired tokens are indistinguishable to a caller."""
    _, login = await _register_and_login(client)
    await client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})

    replayed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    unknown = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "never-issued-token"}
    )

    assert replayed.status_code == unknown.status_code == 401
    assert (await replayed.get_json()) == (await unknown.get_json())


@pytest.mark.asyncio
async def test_sessions_lists_the_stored_refresh_token(client: Any) -> None:
    """/auth/sessions reports the session created at login, not []."""
    _, login = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert response.status_code == 200

    sessions = (await response.get_json())["sessions"]
    assert len(sessions) >= 1
    entry = sessions[0]
    assert set(entry) == {
        "id",
        "device_info",
        "ip_address",
        "created_at",
        "expires_at",
    }
    # A session listing must never expose anything replayable.
    assert login["refresh_token"] not in repr(sessions)


@pytest.mark.asyncio
async def test_logout_revokes_the_refresh_token(client: Any) -> None:
    """Logout reports a real revocation count and kills the refresh token."""
    _, login = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    logout = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert (await logout.get_json())["tokens_revoked"] >= 1

    after = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_the_session_list(client: Any) -> None:
    """After logout the user has no active sessions left."""
    _, login = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    await client.post("/api/v1/auth/logout", headers=headers)

    response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert response.status_code == 200
    assert (await response.get_json())["sessions"] == []


@pytest.mark.asyncio
async def test_revoked_session_cannot_refresh(client: Any) -> None:
    """Revoking a session via /auth/sessions/<id> kills its refresh token."""
    _, login = await _register_and_login(client)
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    listed = await client.get("/api/v1/auth/sessions", headers=headers)
    session_id = (await listed.get_json())["sessions"][0]["id"]

    revoke = await client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert revoke.status_code == 200

    after = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_is_not_stored_in_plaintext(app: Any, client: Any) -> None:
    """Only the digest is persisted — a DB read cannot recover a usable token."""
    user_id, login = await _register_and_login(client)
    raw = login["refresh_token"]

    async with app.app_context():
        from app.models import get_db, get_refresh_token_by_hash

        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        record = await get_refresh_token_by_hash(expected_hash)
        assert record is not None, "login did not store the refresh token"
        assert int(record["user_id"]) == user_id

        db = get_db()
        rows = await db(db.refresh_tokens.user_id == user_id).select()
        assert raw not in repr([dict(r) for r in rows])
