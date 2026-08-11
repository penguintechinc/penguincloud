"""Regression tests for SSRF in POST /api/v1/discovery/scan.

Vulnerability: caller-supplied ``ranges`` went straight into ``_scan_network``
-> ``_probe_endpoint`` unvalidated. An authenticated tenant admin could aim
the portal at ``169.254.169.254`` (cloud metadata), ``127.0.0.1`` (the
portal's own internal surfaces), or any internal host, and the scan results
report which host:port answered and which signature matched — an internal
port scanner with cloud-metadata reach.

The fix is deliberately *not* a private-IP ban: this is a LAN discovery
feature, so blocking RFC1918 would delete its purpose. The operator's
``DISCOVERY_RANGES`` allowlist is the primary control, with special-use
space (loopback, link-local, multicast, reserved, unspecified) always
blocked on top of it.

Every rejection test below is paired with an acceptance test, so a gate that
simply refuses everything cannot pass this suite.
"""

import socket
import uuid
from typing import Any

import jwt
import pytest
from quart import Quart

ALLOWLIST = "10.0.0.0/24,192.168.7.0/24"


async def _new_user(client: Any) -> tuple[dict[str, str], int]:
    """Register and log in a fresh user; return (auth headers, user id)."""
    email = f"disc-{uuid.uuid4().hex[:10]}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Disc User"},
    )
    assert register.status_code in (200, 201), await register.get_json()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert login.status_code == 200, await login.get_json()
    token = (await login.get_json())["access_token"]
    user_id = int(jwt.decode(token, options={"verify_signature": False})["sub"])
    return {"Authorization": f"Bearer {token}"}, user_id


async def _new_tenant(client: Any, headers: dict[str, str]) -> int:
    """Create a tenant; the creator becomes its owner."""
    response = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": "Discovery Tenant",
            "slug": f"disc-{uuid.uuid4().hex[:8]}",
            "plan": "free",
        },
    )
    assert response.status_code == 201, await response.get_json()
    return int((await response.get_json())["id"])


@pytest.fixture
def allowlist(monkeypatch: pytest.MonkeyPatch) -> str:
    """Configure an operator allowlist of two ordinary private LAN ranges."""
    monkeypatch.setattr("app.config.Config.DISCOVERY_RANGES", ALLOWLIST)
    return ALLOWLIST


@pytest.fixture
def probed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture the targets handed to _scan_network instead of probing them.

    Keeps the suite off the network and makes the assertion exact: what
    matters is precisely which addresses cleared validation, not what a
    probe of them would have returned.
    """
    captured: list[str] = []

    async def _fake_scan(targets: list[str]) -> list[dict[str, Any]]:
        captured.extend(targets)
        return []

    monkeypatch.setattr("app.discovery._scan_network", _fake_scan)
    return captured


@pytest.mark.usefixtures("allowlist")
class TestDiscoveryScanSSRF:
    """The scan endpoint may only reach operator-allowlisted, non-special-use IPs."""

    @pytest.mark.asyncio
    async def test_cloud_metadata_ip_rejected(
        self, client: Any, probed: list[str]
    ) -> None:
        """169.254.169.254 is the payload that made this a critical finding."""
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["169.254.169.254"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert probed == [], "metadata IP must never reach the prober"

    @pytest.mark.asyncio
    async def test_loopback_rejected(self, client: Any, probed: list[str]) -> None:
        """127.0.0.1 would expose the portal's own internal surfaces."""
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["127.0.0.1"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert probed == []

    @pytest.mark.asyncio
    async def test_hostname_resolving_to_blocked_address_rejected(
        self, client: Any, probed: list[str]
    ) -> None:
        """A name is judged by what it resolves to, not by its spelling."""
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["localhost"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert probed == []

    @pytest.mark.asyncio
    async def test_hostname_with_one_blocked_address_rejected(
        self,
        client: Any,
        probed: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every resolved address is checked, not just the first.

        A name that resolves to both an allowlisted host and a blocked one
        is the DNS-rebinding shape: validating only ``[0]`` would let the
        second address through.
        """
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        def _fake_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[Any]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["rebind.example.com"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert probed == []

    @pytest.mark.asyncio
    async def test_range_outside_allowlist_rejected(
        self, client: Any, probed: list[str]
    ) -> None:
        """A routable public address the operator never allowlisted."""
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["8.8.8.8"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert "allowlist" in (await response.get_json())["error"]
        assert probed == []

    @pytest.mark.asyncio
    async def test_range_wider_than_allowlist_rejected(
        self, client: Any, probed: list[str]
    ) -> None:
        """A CIDR must be contained entirely, not merely overlap.

        10.0.0.0/8 shares its first address with the allowlisted
        10.0.0.0/24; containment is checked against the whole network so the
        overlap does not admit the other ~16M addresses.
        """
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["10.0.0.0/8"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert probed == []

    @pytest.mark.asyncio
    async def test_allowlisted_private_range_accepted(
        self, client: Any, probed: list[str]
    ) -> None:
        """The feature still works: an allowlisted LAN range is scanned.

        The counterweight to every rejection above — a fix that blocked
        RFC1918 outright would pass all of them and fail this one.
        """
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["10.0.0.0/30"]},
        )

        assert response.status_code == 200, await response.get_json()
        assert probed == ["10.0.0.1", "10.0.0.2"]

    @pytest.mark.asyncio
    async def test_allowlisted_single_host_accepted(
        self, client: Any, probed: list[str]
    ) -> None:
        """A single allowlisted host is the common real-world call."""
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["192.168.7.42"]},
        )

        assert response.status_code == 200, await response.get_json()
        assert probed == ["192.168.7.42"]


class TestDiscoveryScanAllowlistUnset:
    """With no DISCOVERY_RANGES configured, the endpoint fails closed."""

    @pytest.mark.asyncio
    async def test_caller_ranges_rejected_when_allowlist_unset(
        self,
        client: Any,
        probed: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No allowlist means nothing to validate against, so nothing is scanned.

        Note the range requested here is an ordinary private LAN address
        that *would* be accepted under a configured allowlist — what is
        being tested is the absence of the allowlist, not the address.
        """
        monkeypatch.setattr("app.config.Config.DISCOVERY_RANGES", "")
        headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, headers)

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=headers,
            json={"tenant_id": tenant_id, "ranges": ["10.0.0.5"]},
        )

        assert response.status_code == 400, await response.get_json()
        assert "DISCOVERY_RANGES" in (await response.get_json())["error"]
        assert probed == []


@pytest.mark.usefixtures("allowlist")
class TestDiscoveryScanAuthorization:
    """Scanning requires owner/admin authority on the tenant."""

    @pytest.mark.asyncio
    async def test_tenant_member_rejected(
        self,
        client: Any,
        app: Quart,
        probed: list[str],
    ) -> None:
        """A real member of the tenant — not an outsider — is refused.

        The subject is given genuine ``member`` membership so the request
        reaches the admin gate under test. An outsider would be stopped by
        the membership check first and prove nothing about the role gate.
        """
        owner_headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, owner_headers)

        member_headers, member_id = await _new_user(client)
        async with app.app_context():
            from app.models import add_tenant_member

            await add_tenant_member(tenant_id, member_id, role="member")

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=member_headers,
            json={"tenant_id": tenant_id, "ranges": ["10.0.0.5"]},
        )

        assert response.status_code == 403, await response.get_json()
        assert probed == []

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("enterprise_license")
    # Builds a multi-tenant / delegated-admin structure, which the tier
    # model sells at Enterprise.
    async def test_tenant_admin_accepted(
        self,
        client: Any,
        app: Quart,
        probed: list[str],
    ) -> None:
        """The same user promoted to admin may scan — the gate is role-based.

        Paired with the member test above: together they show the 403 comes
        from the role, not from something incidental about the caller.
        """
        owner_headers, _ = await _new_user(client)
        tenant_id = await _new_tenant(client, owner_headers)

        admin_headers, admin_id = await _new_user(client)
        async with app.app_context():
            from app.models import add_tenant_member

            await add_tenant_member(tenant_id, admin_id, role="admin")

        response = await client.post(
            "/api/v1/discovery/scan",
            headers=admin_headers,
            json={"tenant_id": tenant_id, "ranges": ["10.0.0.5"]},
        )

        assert response.status_code == 200, await response.get_json()
        assert probed == ["10.0.0.5"]
