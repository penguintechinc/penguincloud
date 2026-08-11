"""API key + audit log endpoint tests (/api/v1/users/...).

Regression coverage for three endpoints that wrapped an *async* model
function in asyncio.to_thread. to_thread runs the call in a worker thread,
which for a coroutine function merely *builds* a coroutine object and hands
it back un-awaited: the DB work never runs, and the caller sees a truthy
object instead of a result.

The revocation case was the security-relevant one — `success` was always a
truthy coroutine, so DELETE reported 200 without revoking anything and the
ownership predicate (user_id == caller) in the UPDATE's WHERE clause could
never fail.

Distinct from tests/api/test_api_keys.py, which targets an unimplemented
top-level /api/v1/api-keys surface and is skipped pending Phase 1B.
"""

from typing import Any

import pytest


async def _create_key(
    client: Any, headers: dict[str, str], name: str = "Test Key"
) -> dict[str, Any]:
    """Create an API key via the users blueprint and return the response body."""
    response = await client.post("/api/v1/users/api-keys", headers=headers, json={"name": name})
    assert response.status_code == 201, f"Failed to create API key: {await response.get_json()}"
    body: dict[str, Any] = await response.get_json()
    return body


@pytest.mark.asyncio
async def test_list_api_keys_returns_real_list(client: Any, auth_headers: dict[str, str]) -> None:
    """GET /users/api-keys returns actual rows, not an un-awaited coroutine."""
    await _create_key(client, auth_headers, name="Listable Key")

    response = await client.get("/api/v1/users/api-keys", headers=auth_headers)
    assert response.status_code == 200

    body = await response.get_json()
    assert isinstance(body["api_keys"], list)
    assert len(body["api_keys"]) >= 1

    entry = body["api_keys"][0]
    assert entry["name"] == "Listable Key"
    # key_prefix is the schema column; create_api_key previously inserted
    # `prefix`, which the DAL rejects as an unconsumed column name.
    assert entry["prefix"].startswith("pk_")
    # The full key is shown once at creation and never listed again.
    assert "key" not in entry
    assert "key_hash" not in entry


@pytest.mark.asyncio
async def test_created_key_is_listed_once_only(client: Any, auth_headers: dict[str, str]) -> None:
    """The full key value is returned at creation and never re-listed."""
    created = await _create_key(client, auth_headers, name="Once Only")
    assert created["key"].startswith("pk_")

    response = await client.get("/api/v1/users/api-keys", headers=auth_headers)
    body = await response.get_json()
    assert created["key"] not in repr(body)


@pytest.mark.asyncio
async def test_revoked_key_is_actually_revoked(
    app: Any, client: Any, auth_headers: dict[str, str]
) -> None:
    """DELETE genuinely revokes: the key stops validating afterwards.

    Asserts against validate_api_key rather than the 200 response, because
    the 200 was exactly what the bug produced while revoking nothing.
    """
    created = await _create_key(client, auth_headers, name="Revoke Me")
    raw_key = created["key"]

    async with app.app_context():
        from app.auth_features import validate_api_key

        assert await validate_api_key(raw_key) is not None, "key should start valid"

    response = await client.delete(f"/api/v1/users/api-keys/{created['id']}", headers=auth_headers)
    assert response.status_code == 200

    async with app.app_context():
        from app.auth_features import validate_api_key

        assert await validate_api_key(raw_key) is None, "revoked key still validates"


@pytest.mark.asyncio
async def test_revoking_another_users_key_returns_404(
    app: Any, client: Any, auth_headers: dict[str, str]
) -> None:
    """A caller cannot revoke a key they do not own.

    The ownership check lives in the UPDATE's WHERE clause, so an
    un-awaited coroutine made it unreachable — every revocation "succeeded"
    regardless of owner.
    """
    victim = await _create_key(client, auth_headers, name="Victim Key")
    victim_key = victim["key"]

    # A second, unrelated user.
    import uuid

    attacker_email = f"attacker-{uuid.uuid4().hex[:8]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": attacker_email,
            "password": "attackerpass123",
            "full_name": "Attacker",
        },
    )
    assert register.status_code in (200, 201)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": attacker_email, "password": "attackerpass123"},
    )
    assert login.status_code == 200
    attacker_headers = {"Authorization": f"Bearer {(await login.get_json())['access_token']}"}

    response = await client.delete(
        f"/api/v1/users/api-keys/{victim['id']}", headers=attacker_headers
    )
    assert response.status_code == 404

    # And the victim's key still works.
    async with app.app_context():
        from app.auth_features import validate_api_key

        assert await validate_api_key(victim_key) is not None


@pytest.mark.asyncio
async def test_revoking_unknown_key_returns_404(client: Any, auth_headers: dict[str, str]) -> None:
    """Revoking an id that does not exist is a 404, not a false success."""
    response = await client.delete("/api/v1/users/api-keys/99999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.usefixtures("enterprise_license")
async def test_audit_logs_endpoint_returns_real_list(
    client: Any, admin_headers: dict[str, str], tenant_id: int
) -> None:
    """GET /users/audit-logs returns actual rows, not an un-awaited coroutine.

    Now tenant-scoped and Enterprise-licensed, so the request names a
    tenant and the test states the licence. Both are asserted in their own
    right by tests/api/test_audit_isolation.py.
    """
    response = await client.get(
        f"/api/v1/users/audit-logs?tenant_id={tenant_id}", headers=admin_headers
    )
    assert response.status_code == 200

    body = await response.get_json()
    assert isinstance(body["logs"], list)
    for entry in body["logs"]:
        # Serialised shape, not raw rows — action_type is exposed as `action`.
        assert set(entry) == {
            "id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "created_at",
        }


@pytest.mark.asyncio
async def test_audit_logs_endpoint_requires_admin(
    client: Any, auth_headers: dict[str, str]
) -> None:
    """A non-admin caller is refused the audit log."""
    response = await client.get("/api/v1/users/audit-logs", headers=auth_headers)
    assert response.status_code == 403
