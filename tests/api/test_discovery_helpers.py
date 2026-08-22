"""Unit coverage for app.discovery's validation and probing internals.

test_discovery_ssrf.py already covers the SSRF-critical rejections
end-to-end through POST /discovery/scan (loopback, link-local/cloud
metadata, allowlist containment). This file covers the remaining pure
helpers directly -- multicast/reserved/unspecified rejection, the
IPv4-mapped-IPv6 unwrap, allowlist parsing's malformed-entry handling,
hostname resolution failure modes, and the network probe functions
(_format_host, _probe_endpoint, _scan_network) with aiohttp faked at the
module boundary -- none of which the SSRF-focused endpoint tests exercise.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any

import aiohttp
import pytest
from app.adapters.discovery_profiles import DiscoveryProfile
from app.discovery import (
    DiscoveryTargetError,
    _expand,
    _format_host,
    _is_subnet,
    _probe_endpoint,
    _reject_reason,
    _resolve_hostname,
    _scan_network,
    parse_allowlist,
    resolve_scan_targets,
)


class TestRejectReason:
    """Reject Reason."""

    @pytest.mark.parametrize(
        ("literal", "expected_fragment"),
        [
            # Asserting REJECTION of this literal, not a bind target -- ruff's
            # own suppression (noqa) must stay on the flagged line, same as
            # bandit's (nosec); see the line below.
            ("0.0.0.0", "unspecified"),  # noqa: S104  # nosec B104
            ("224.0.0.1", "multicast"),
            ("240.0.0.1", "reserved"),
        ],
    )
    def test_special_use_addresses_are_rejected(self, literal: str, expected_fragment: str) -> None:
        """Special use addresses are rejected."""
        addr = ipaddress.ip_address(literal)
        reason = _reject_reason(addr)
        assert reason is not None
        assert expected_fragment in reason

    def test_ordinary_private_address_is_scannable(self) -> None:
        """Ordinary private address is scannable."""
        addr = ipaddress.ip_address("10.0.0.5")
        assert _reject_reason(addr) is None

    def test_ipv4_mapped_ipv6_loopback_unwraps_and_is_rejected(self) -> None:
        """::ffff:127.0.0.1 reports False for is_loopback on the v6 object.

        Without unwrapping to the mapped v4 address first, this bypasses
        every special-use check -- the exact DNS-rebinding-adjacent shape
        the unwrap exists to close.
        """
        addr = ipaddress.ip_address("::ffff:127.0.0.1")
        reason = _reject_reason(addr)
        assert reason is not None
        assert "loopback" in reason

    def test_ipv4_mapped_ipv6_ordinary_address_is_scannable(self) -> None:
        """Ipv4 mapped ipv6 ordinary address is scannable."""
        addr = ipaddress.ip_address("::ffff:10.0.0.5")
        assert _reject_reason(addr) is None


class TestParseAllowlist:
    """Parse Allowlist."""

    def test_unparseable_entry_is_dropped_with_a_warning(self) -> None:
        """Unparseable entry is dropped with a warning."""
        networks = parse_allowlist("10.0.0.0/24,not-a-cidr,192.168.1.0/24")
        assert [str(n) for n in networks] == ["10.0.0.0/24", "192.168.1.0/24"]

    def test_all_entries_unparseable_yields_empty_list(self) -> None:
        """All entries unparseable yields empty list."""
        assert parse_allowlist("garbage,also-garbage") == []

    def test_blank_and_whitespace_entries_are_skipped(self) -> None:
        """Blank and whitespace entries are skipped."""
        networks = parse_allowlist(" , 10.0.0.0/24 ,, ")
        assert [str(n) for n in networks] == ["10.0.0.0/24"]


class TestIsSubnet:
    """Is Subnet."""

    def test_ipv6_network_contained_in_ipv6_allowed(self) -> None:
        """Ipv6 network contained in ipv6 allowed."""
        network = ipaddress.ip_network("2001:db8::/64")
        allowed = ipaddress.ip_network("2001:db8::/32")
        assert _is_subnet(network, allowed) is True

    def test_ipv6_network_not_contained(self) -> None:
        """Ipv6 network not contained."""
        network = ipaddress.ip_network("2001:db9::/64")
        allowed = ipaddress.ip_network("2001:db8::/32")
        assert _is_subnet(network, allowed) is False

    def test_mixed_address_families_never_match(self) -> None:
        """Mixed address families never match."""
        network = ipaddress.ip_network("10.0.0.0/24")
        allowed = ipaddress.ip_network("2001:db8::/32")
        assert _is_subnet(network, allowed) is False


class TestExpand:
    """Expand."""

    def test_ipv6_network_expands_to_its_hosts(self) -> None:
        # IPv6 has no broadcast address, so .hosts() on a /126 drops only
        # the network address itself -- 3 usable hosts, not 4.
        """Ipv6 network expands to its hosts."""
        network = ipaddress.ip_network("2001:db8::/126")
        addresses = _expand(network, "2001:db8::/126")
        assert [str(a) for a in addresses] == ["2001:db8::1", "2001:db8::2", "2001:db8::3"]

    def test_single_ipv6_host_expands_to_itself(self) -> None:
        """Single ipv6 host expands to itself."""
        network = ipaddress.ip_network("2001:db8::1/128")
        addresses = _expand(network, "2001:db8::1/128")
        assert [str(a) for a in addresses] == ["2001:db8::1"]

    def test_oversized_network_is_rejected(self) -> None:
        """Oversized network is rejected."""
        network = ipaddress.ip_network("10.0.0.0/8")
        with pytest.raises(DiscoveryTargetError, match="limit is"):
            _expand(network, "10.0.0.0/8")


class TestResolveHostname:
    """Resolve Hostname."""

    @pytest.mark.asyncio
    async def test_unresolvable_hostname_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unresolvable hostname raises."""

        async def _fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            """Fake to thread."""
            raise socket.gaierror("Name or service not known")

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
        with pytest.raises(DiscoveryTargetError, match="could not be resolved"):
            await _resolve_hostname("nowhere.invalid")

    @pytest.mark.asyncio
    async def test_empty_resolution_result_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty resolution result raises."""

        async def _fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            """Fake to thread."""
            return []

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
        with pytest.raises(DiscoveryTargetError, match="could not be resolved"):
            await _resolve_hostname("empty-result.invalid")

    @pytest.mark.asyncio
    async def test_duplicate_addresses_across_records_are_deduplicated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Duplicate addresses across records are deduplicated."""

        async def _fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            """Fake to thread."""
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
            ]

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
        addresses = await _resolve_hostname("dup.invalid")
        assert [str(a) for a in addresses] == ["10.0.0.5"]


class TestResolveScanTargets:
    """Resolve Scan Targets."""

    @pytest.mark.asyncio
    async def test_blank_entries_are_skipped(self) -> None:
        """Blank entries are skipped."""
        allowlist = [ipaddress.ip_network("10.0.0.0/24")]
        targets = await resolve_scan_targets(["", "  ", "10.0.0.5"], allowlist)
        assert targets == ["10.0.0.5"]

    @pytest.mark.asyncio
    async def test_exceeding_max_targets_mid_loop_raises(self) -> None:
        """Exceeding max targets mid loop raises."""
        allowlist = [ipaddress.ip_network("10.0.0.0/16")]
        # Two /23 entries (510 usable hosts each) push the running total
        # over MAX_SCAN_TARGETS (1024) on the second entry, inside the loop
        # -- not on the size of either single entry (which _expand alone
        # would allow).
        entries = ["10.0.0.0/23", "10.0.4.0/23", "10.0.8.0/23"]
        with pytest.raises(DiscoveryTargetError, match="more than 1024"):
            await resolve_scan_targets(entries, allowlist)

    @pytest.mark.asyncio
    async def test_overlapping_entries_deduplicate(self) -> None:
        """Overlapping entries deduplicate."""
        allowlist = [ipaddress.ip_network("10.0.0.0/24")]
        targets = await resolve_scan_targets(["10.0.0.5", "10.0.0.5"], allowlist)
        assert targets == ["10.0.0.5"]


class TestFormatHost:
    """Format Host."""

    def test_ipv4_literal_is_unbracketed(self) -> None:
        """Ipv4 literal is unbracketed."""
        assert _format_host("10.0.0.5") == "10.0.0.5"

    def test_ipv6_literal_is_bracketed(self) -> None:
        """Ipv6 literal is bracketed."""
        assert _format_host("2001:db8::1") == "[2001:db8::1]"

    def test_hostname_passthrough(self) -> None:
        """Hostname passthrough."""
        assert _format_host("not-an-ip.example.com") == "not-an-ip.example.com"


_TEST_PROFILE = DiscoveryProfile(
    product_type="testproduct",
    display_name="Test Product",
    ports=(8080,),
    health_endpoint="/healthz",
    signatures=("testproduct-signature",),
)


class _FakeResponse:
    """Fake Response."""

    def __init__(self, status: int, text: str, headers: dict[str, str] | None = None) -> None:
        """Init."""
        self.status = status
        self._text = text
        self.headers = headers or {}

    async def text(self) -> str:
        """Text."""
        return self._text

    async def __aenter__(self) -> _FakeResponse:
        """Aenter."""
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        """Aexit."""
        return False


class _FakeSession:
    """Fake Session."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        """Init."""
        self._response = response

    def get(self, url: str) -> Any:
        """Get."""
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestProbeEndpoint:
    """Probe Endpoint."""

    @pytest.mark.asyncio
    async def test_signature_match_is_reported(self) -> None:
        """Signature match is reported."""
        session = _FakeSession(
            _FakeResponse(200, "this body mentions testproduct-signature somewhere")
        )
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is not None
        assert result["product_type"] == "testproduct"
        assert result["base_url"] == "http://10.0.0.5:8080"
        assert "unconfirmed" not in result

    @pytest.mark.asyncio
    async def test_server_header_signature_match_is_reported(self) -> None:
        """Server header signature match is reported."""
        session = _FakeSession(
            _FakeResponse(200, "no match in body", headers={"server": "TestProduct-Signature/1.0"})
        )
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is not None
        assert result["product_type"] == "testproduct"

    @pytest.mark.asyncio
    async def test_200_without_signature_is_an_unconfirmed_candidate(self) -> None:
        """200 without signature is an unconfirmed candidate."""
        session = _FakeSession(_FakeResponse(200, "generic ok body"))
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is not None
        assert result["unconfirmed"] is True
        assert "unconfirmed" in result["display_name"]

    @pytest.mark.asyncio
    async def test_non_200_without_signature_is_not_reported(self) -> None:
        """Non 200 without signature is not reported."""
        session = _FakeSession(_FakeResponse(404, "not found"))
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_connection_error_is_swallowed_as_no_result(self) -> None:
        """Connection error is swallowed as no result."""
        session = _FakeSession(aiohttp.ClientConnectionError("refused"))
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_os_error_is_swallowed_as_no_result(self) -> None:
        """Os error is swallowed as no result."""
        session = _FakeSession(OSError("network unreachable"))
        result = await _probe_endpoint("10.0.0.5", 8080, _TEST_PROFILE, session)  # type: ignore[arg-type]
        assert result is None


class TestScanNetwork:
    """Scan Network."""

    @pytest.mark.asyncio
    async def test_scan_deduplicates_by_base_url_and_assigns_ids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two profiles/ports resolving to the same base_url count once."""
        hit = {
            "product_type": "testproduct",
            "display_name": "Test Product",
            "base_url": "http://10.0.0.5:8080",
            "health_endpoint": "/healthz",
            "status_code": 200,
            "response_time_ms": 5,
        }

        async def _fake_probe(
            host: str, port: int, profile: DiscoveryProfile, session: Any
        ) -> dict[str, Any] | None:
            """Fake probe."""
            return dict(hit) if host == "10.0.0.5" else None

        monkeypatch.setattr("app.discovery._probe_endpoint", _fake_probe)
        monkeypatch.setattr("app.discovery.DISCOVERY_PROFILES", {"testproduct": _TEST_PROFILE})

        results = await _scan_network(["10.0.0.5", "10.0.0.6"])

        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["base_url"] == "http://10.0.0.5:8080"

    @pytest.mark.asyncio
    async def test_scan_with_no_hits_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Scan with no hits returns empty."""

        async def _fake_probe(
            host: str, port: int, profile: DiscoveryProfile, session: Any
        ) -> dict[str, Any] | None:
            """Fake probe."""
            return None

        monkeypatch.setattr("app.discovery._probe_endpoint", _fake_probe)
        monkeypatch.setattr("app.discovery.DISCOVERY_PROFILES", {"testproduct": _TEST_PROFILE})

        results = await _scan_network(["10.0.0.5"])
        assert results == []

    @pytest.mark.asyncio
    async def test_scan_tolerates_a_probe_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One bad probe must not sink the whole scan.

        Relies on asyncio.gather(..., return_exceptions=True).
        """

        async def _fake_probe(
            host: str, port: int, profile: DiscoveryProfile, session: Any
        ) -> dict[str, Any] | None:
            """Fake probe."""
            raise RuntimeError("boom")

        monkeypatch.setattr("app.discovery._probe_endpoint", _fake_probe)
        monkeypatch.setattr("app.discovery.DISCOVERY_PROFILES", {"testproduct": _TEST_PROFILE})

        results = await _scan_network(["10.0.0.5"])
        assert results == []


class TestDiscoveryEndpointValidation:
    """HTTP-level validation branches not reached by test_discovery_ssrf.py."""

    @pytest.mark.asyncio
    async def test_trigger_scan_requires_tenant_id(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Trigger scan requires tenant id."""
        response = await client.post("/api/v1/discovery/scan", headers=admin_headers, json={})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"

    @pytest.mark.asyncio
    async def test_trigger_scan_no_ranges_and_no_allowlist_is_rejected(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trigger scan no ranges and no allowlist is rejected."""
        monkeypatch.setattr("app.config.Config.DISCOVERY_RANGES", "")
        response = await client.post(
            "/api/v1/discovery/scan",
            headers=admin_headers,
            json={"tenant_id": tenant_id},
        )
        assert response.status_code == 400
        assert "No network ranges" in (await response.get_json())["error"]

    @pytest.mark.asyncio
    async def test_get_scan_results_requires_tenant_id(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Get scan results requires tenant id."""
        response = await client.get("/api/v1/discovery/results", headers=admin_headers)
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"

    @pytest.mark.asyncio
    async def test_accept_requires_tenant_id(
        self, client: Any, admin_headers: dict[str, str]
    ) -> None:
        """Accept requires tenant id."""
        response = await client.post("/api/v1/discovery/accept/1", headers=admin_headers, json={})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "tenant_id required"

    @pytest.mark.asyncio
    async def test_accept_full_success_creates_a_product_connection(
        self,
        client: Any,
        admin_headers: dict[str, str],
        tenant_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A previously-discovered candidate becomes a real connection."""
        import app.discovery as discovery_module

        discovered = {
            "id": 1,
            "product_type": "gough",
            "display_name": "Gough",
            "base_url": "http://10.0.0.5:8080",
            "health_endpoint": "/healthz",
            "status_code": 200,
            "response_time_ms": 5,
        }
        monkeypatch.setitem(discovery_module._scan_results, tenant_id, [discovered])

        response = await client.post(
            "/api/v1/discovery/accept/1",
            headers=admin_headers,
            json={"tenant_id": tenant_id},
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["base_url"] == "http://10.0.0.5:8080"
        assert data["product_type"] == "gough"
        assert data["discovered"] is True

    @pytest.mark.asyncio
    async def test_accept_unknown_discovery_id_is_not_found(
        self, client: Any, admin_headers: dict[str, str], tenant_id: int
    ) -> None:
        """Accept unknown discovery id is not found."""
        response = await client.post(
            "/api/v1/discovery/accept/999",
            headers=admin_headers,
            json={"tenant_id": tenant_id},
        )
        assert response.status_code == 404
