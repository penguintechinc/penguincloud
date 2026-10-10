"""``POST /api/v1/users/<user_id>/rate-limit-reset`` — the operator escape hatch.

``app/ratelimit.py`` exposed :func:`rate_limit_reset` as a Python primitive
with no HTTP route: an operator facing a locked-out user had to wait out the
TTL (up to 1h) or open a Python shell against production. This route is the
route, gated the way every other tenant-acting admin route in this file is
gated (``members:manage`` in the TARGET's tenant, resolved through
``require_tenant_scope`` so a delegated MSP admin's authority is honoured),
and closes the same cross-tenant leak class ``test_audit_isolation.py``
exists for: naming a tenant the caller genuinely administers is not enough
— the caller also has to be right that the target user is a MEMBER of that
tenant, not merely of a tenant they mistakenly assume.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt
import pytest
from app import ratelimit
from penguin_dal.quart_ext import get_db
from quart import Quart

MonkeyPatch = pytest.MonkeyPatch

pytestmark = pytest.mark.usefixtures("enterprise_license")


async def _register_and_login(client: Any, email: str) -> dict[str, str]:
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password"},
    )
    assert register.status_code in (200, 201), await register.get_json()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "a-long-enough-password"},
    )
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_id_from_headers(headers: dict[str, str]) -> int:
    token = headers["Authorization"].split(" ", 1)[1]
    payload = jwt.decode(token, options={"verify_signature": False})
    return int(payload["sub"])


async def _create_tenant(client: Any, headers: dict[str, str], name: str) -> int:
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": name, "slug": f"{name}-{uuid.uuid4().hex[:8]}", "plan": "free"},
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


async def _add_member(
    client: Any, admin_headers: dict[str, str], tenant_id: int, user_id: int
) -> None:
    response = await client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=admin_headers,
        json={"user_id": user_id, "role": "member"},
    )
    assert response.status_code == 201, await response.get_json()


def _reset_url(user_id: int) -> str:
    return f"/api/v1/users/{user_id}/rate-limit-reset"


class TestScopeGate:
    """Authenticated is not the same as authorized."""

    @pytest.mark.asyncio
    async def test_a_caller_with_no_authority_over_the_tenant_is_refused(self, client: Any) -> None:
        """Merely being authenticated is not merely being authorized."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "gate-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        stranger = await _register_and_login(client, f"stranger-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            _reset_url(member_id),
            headers=stranger,
            json={"tenant_id": tenant_id, "bucket": "login"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_the_target_members_own_role_confers_no_authority(self, client: Any) -> None:
        """Direct membership is not admin authority — a plain member cannot self-clear."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "self-clear-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        response = await client.post(
            _reset_url(member_id),
            headers=member,
            json={"tenant_id": tenant_id, "bucket": "login"},
        )

        assert response.status_code == 403


class TestCrossTenantIsolation:
    """The audit_isolation.py defect shape, on an admin ACTION route."""

    @pytest.mark.asyncio
    async def test_naming_a_tenant_the_caller_administers_is_not_enough(self, client: Any) -> None:
        """The caller must ALSO be right that the target is a member of it.

        Without the membership check, an admin of tenant A could name A
        (a tenant they genuinely administer) to reach a user who exists
        only in unrelated tenant B — the exact shape of the
        ``db(db.audit_logs.id > 0)`` leak this repo has already shipped
        once.
        """
        admin_a = await _register_and_login(client, f"admin-a-{uuid.uuid4().hex[:8]}@example.com")
        tenant_a = await _create_tenant(client, admin_a, "tenant-a")

        admin_b = await _register_and_login(client, f"admin-b-{uuid.uuid4().hex[:8]}@example.com")
        tenant_b = await _create_tenant(client, admin_b, "tenant-b")
        victim = await _register_and_login(client, f"victim-{uuid.uuid4().hex[:8]}@example.com")
        victim_id = _user_id_from_headers(victim)
        await _add_member(client, admin_b, tenant_b, victim_id)

        # admin_a has genuine members:manage authority over tenant_a, but
        # the victim is a member of tenant_b, not tenant_a.
        response = await client.post(
            _reset_url(victim_id),
            headers=admin_a,
            json={"tenant_id": tenant_a, "bucket": "login"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_naming_the_victims_actual_tenant_without_authority_there_is_refused(
        self, client: Any
    ) -> None:
        """The other half: naming the RIGHT tenant with no authority over it."""
        admin_a = await _register_and_login(client, f"admin-a-{uuid.uuid4().hex[:8]}@example.com")

        admin_b = await _register_and_login(client, f"admin-b-{uuid.uuid4().hex[:8]}@example.com")
        tenant_b = await _create_tenant(client, admin_b, "tenant-b2")
        victim = await _register_and_login(client, f"victim-{uuid.uuid4().hex[:8]}@example.com")
        victim_id = _user_id_from_headers(victim)
        await _add_member(client, admin_b, tenant_b, victim_id)

        response = await client.post(
            _reset_url(victim_id),
            headers=admin_a,
            json={"tenant_id": tenant_b, "bucket": "login"},
        )

        assert response.status_code == 403


class TestAuthorizedClearingWorks:
    """The positive path: a real lockout, really cleared."""

    @pytest.mark.asyncio
    async def test_direct_tenant_admin_clears_a_real_lockout(
        self, client: Any, app: Quart, monkeypatch: MonkeyPatch
    ) -> None:
        """Non-vacuity: the clear must actually un-block a real 429."""
        # The account-scoped window counts every submitted attempt against
        # this email, including the SUCCESSFUL login the register/login helper
        # just performed -- so max_attempts=2 leaves exactly one more before
        # the bucket trips: the helper's login (1), one bad attempt (2, still
        # admitted), a second bad attempt (3, refused).
        monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, "login", ratelimit._Window(2, 300))

        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "clear-tenant")
        victim_email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
        victim = await _register_and_login(client, victim_email)
        victim_id = _user_id_from_headers(victim)
        await _add_member(client, owner, tenant_id, victim_id)

        # Trip the 1-attempt account window with one more bad login.
        bad = await client.post(
            "/api/v1/auth/login", json={"email": victim_email, "password": "wrong"}
        )
        assert bad.status_code == 401
        locked = await client.post(
            "/api/v1/auth/login", json={"email": victim_email, "password": "wrong"}
        )
        assert locked.status_code == 429

        response = await client.post(
            _reset_url(victim_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "login"},
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body == {
            "message": "Rate limit cleared",
            "user_id": victim_id,
            "bucket": "login",
        }

        # Still a bad password -- 401, but crucially NOT 429 any more.
        retried = await client.post(
            "/api/v1/auth/login", json={"email": victim_email, "password": "wrong"}
        )
        assert retried.status_code == 401

    @pytest.mark.asyncio
    async def test_delegated_admin_of_an_ancestor_tenant_can_clear_a_descendant_member(
        self, client: Any, app: Quart, monkeypatch: MonkeyPatch
    ) -> None:
        """Delegated authority (owner/admin in an ancestor) must be honoured."""
        # The account-scoped window counts every submitted attempt against
        # this email, including the SUCCESSFUL login the register/login helper
        # just performed -- so max_attempts=2 leaves exactly one more before
        # the bucket trips: the helper's login (1), one bad attempt (2, still
        # admitted), a second bad attempt (3, refused).
        monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, "login", ratelimit._Window(2, 300))

        provider_admin = await _register_and_login(
            client, f"provider-{uuid.uuid4().hex[:8]}@example.com"
        )
        provider_id = await _create_tenant(client, provider_admin, "provider")
        customer_id = await _create_tenant(client, provider_admin, "customer")

        response = await client.put(
            f"/api/v1/tenants/{customer_id}/parent",
            headers=provider_admin,
            json={"parent_tenant_id": provider_id},
        )
        assert response.status_code == 200, await response.get_json()

        member_email = f"cust-member-{uuid.uuid4().hex[:8]}@example.com"
        member = await _register_and_login(client, member_email)
        member_id = _user_id_from_headers(member)
        await _add_member(client, provider_admin, customer_id, member_id)

        bad = await client.post(
            "/api/v1/auth/login", json={"email": member_email, "password": "wrong"}
        )
        assert bad.status_code == 401
        locked = await client.post(
            "/api/v1/auth/login", json={"email": member_email, "password": "wrong"}
        )
        assert locked.status_code == 429

        # provider_admin has NO tenant_members row in customer_id -- their
        # authority is entirely delegated from owning the ancestor.
        response = await client.post(
            _reset_url(member_id),
            headers=provider_admin,
            json={"tenant_id": customer_id, "bucket": "login"},
        )
        assert response.status_code == 200, await response.get_json()

        retried = await client.post(
            "/api/v1/auth/login", json={"email": member_email, "password": "wrong"}
        )
        assert retried.status_code == 401


class TestInputValidation:
    """Malformed requests never reach the scope or membership checks."""

    @pytest.mark.asyncio
    async def test_missing_tenant_id_is_rejected(self, client: Any) -> None:
        """A body with no tenant_id is rejected before any authority check."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "validation-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        response = await client.post(_reset_url(member_id), headers=owner, json={"bucket": "login"})

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_bucket_is_rejected(self, client: Any) -> None:
        """A bucket name outside CLEARABLE_ACCOUNT_BUCKETS is rejected."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "bucket-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        response = await client.post(
            _reset_url(member_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "not_a_real_bucket"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_ratelimit_reset_itself_is_not_a_clearable_bucket(
        self, client: Any
    ) -> None:
        """The admin action's own bucket protects itself, not a user."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "self-protect-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        response = await client.post(
            _reset_url(member_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "admin_ratelimit_reset"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_a_bool_tenant_id_is_not_silently_coerced_to_tenant_one(
        self, client: Any
    ) -> None:
        """Bool is an int subclass -- True must not resolve to tenant 1."""
        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")

        response = await client.post(
            _reset_url(_user_id_from_headers(owner)),
            headers=owner,
            json={"tenant_id": True, "bucket": "login"},
        )

        assert response.status_code == 400


class TestAudit:
    """Clearing a lockout is an account-security action, so it is logged."""

    @pytest.mark.asyncio
    async def test_clearing_a_lockout_is_audit_logged(
        self, client: Any, app: Quart, monkeypatch: MonkeyPatch
    ) -> None:
        """A cleared bucket leaves a real row naming the actor, target and bucket."""
        monkeypatch.setitem(ratelimit._ACCOUNT_WINDOWS, "login", ratelimit._Window(1, 300))

        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "audit-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        response = await client.post(
            _reset_url(member_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "mfa_verify"},
        )
        assert response.status_code == 200

        async with app.app_context():
            db = get_db()
            rows = await db(
                (db.audit_logs.tenant_id == tenant_id)
                & (db.audit_logs.action_type == "user.ratelimit.reset")
                & (db.audit_logs.resource_id == str(member_id))
            ).select()

        assert len(rows) == 1
        assert rows[0].metadata == "mfa_verify"


class TestSelfRateLimited:
    """The admin route protects itself, not just the users it manages."""

    @pytest.mark.asyncio
    async def test_the_route_refuses_once_its_own_bucket_is_exhausted(
        self, client: Any, monkeypatch: MonkeyPatch
    ) -> None:
        """Otherwise this route becomes the hole in the protection it manages."""
        monkeypatch.setitem(
            ratelimit._ACCOUNT_WINDOWS, "admin_ratelimit_reset", ratelimit._Window(1, 300)
        )
        monkeypatch.setitem(
            ratelimit._IP_WINDOWS, "admin_ratelimit_reset", ratelimit._Window(1000, 300)
        )

        owner = await _register_and_login(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
        tenant_id = await _create_tenant(client, owner, "self-limit-tenant")
        member = await _register_and_login(client, f"member-{uuid.uuid4().hex[:8]}@example.com")
        member_id = _user_id_from_headers(member)
        await _add_member(client, owner, tenant_id, member_id)

        first = await client.post(
            _reset_url(member_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "login"},
        )
        assert first.status_code == 200

        second = await client.post(
            _reset_url(member_id),
            headers=owner,
            json={"tenant_id": tenant_id, "bucket": "mfa_verify"},
        )

        assert second.status_code == 429


def test_the_derived_credential_route_guard_does_not_already_force_this() -> None:
    """Documents the deliberate choice: rate limiting here is NOT guard-mandated.

    ``reset_user_rate_limit`` calls no credential-verification primitive
    (see ``CREDENTIAL_VERIFICATION_PRIMITIVES`` in
    ``test_credential_routes_are_rate_limited.py``) and is not in
    ``auth_bp``, so the derived guard's ``credential_accepting`` set does
    not sweep it in. The ``@ratelimit.rate_limited`` decorator on it is a
    deliberate defensive choice for an admin action that can itself be
    abused, not something the existing guard already required -- this test
    pins that distinction so it does not silently get "explained away" as
    guard coverage that was never actually there.
    """
    import test_credential_routes_are_rate_limited as guard

    analysis = guard._Analysis()

    assert "reset_user_rate_limit" not in analysis.credential_accepting
    assert "reset_user_rate_limit" in analysis.gated
