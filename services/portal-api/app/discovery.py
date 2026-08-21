"""Auto-Discovery Service for PenguinTech Products.

Scan targets are attacker-influenced input: /scan probes whatever it is
given and reports which host:port answered and what it looked like, which
is an SSRF primitive and an internal port scanner unless the target set is
constrained. :func:`resolve_scan_targets` is that constraint and every scan
path goes through it — see its docstring for the model.
"""

import asyncio
import ipaddress
import logging
import socket
import time
from typing import Any, Final

import aiohttp
from quart import Blueprint, request

from .adapters.discovery_profiles import DISCOVERY_PROFILES, DiscoveryProfile
from .authz import (
    SCOPE_PRODUCTS_MANAGE,
    SCOPE_PRODUCTS_READ,
    require_tenant_scope,
)
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    create_product_connection,
    get_product_connection_by_id,
)

logger = logging.getLogger(__name__)

discovery_bp = Blueprint("discovery", __name__)

# In-memory store for latest scan results per tenant
_scan_results: dict[int, list[dict[str, Any]]] = {}

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: Ceiling on how many individual addresses one scan may expand to.
#:
#: Without it, an allowlisted /8 expands to ~16.7M addresses times every
#: adapter times every discovery port, which is a self-inflicted DoS rather
#: than a discovery scan. Exceeding it is a 400, not a silent truncation —
#: a partial scan that looks complete is worse than a clear error.
MAX_SCAN_TARGETS: Final[int] = 1024


class DiscoveryTargetError(ValueError):
    """A requested scan target is not permitted.

    Carries a caller-safe message: it names the rejected entry and the rule
    it broke, never anything about hosts the caller did not already supply.
    """


def _reject_reason(addr: IPAddress) -> str | None:
    """Return why an address may never be scanned, or None if it may be.

    These rejections hold *even for an allowlisted address*. This is a LAN
    product-discovery feature, so RFC1918 is explicitly not disqualifying —
    blanket-blocking private space would remove the feature's entire
    purpose. What is blocked is the special-use space that turns discovery
    into an attack primitive: link-local carries the cloud metadata service
    (169.254.169.254), and loopback reaches the portal's own internal
    surfaces that never expected an off-box caller.

    Determined from :mod:`ipaddress` properties rather than a hand-written
    CIDR list, so the ranges cannot drift from the standard.
    """
    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) reports False for
    # is_loopback et al. on the IPv6 object, so unwrap it and judge the
    # address that will actually be connected to.
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped

    if addr.is_unspecified:
        return "unspecified address"
    if addr.is_loopback:
        return "loopback address"
    if addr.is_link_local:
        return "link-local address (cloud metadata range)"
    if addr.is_multicast:
        return "multicast address"
    if addr.is_reserved:
        return "reserved address"
    return None


def _assert_scannable(addr: IPAddress, entry: str) -> None:
    """Raise DiscoveryTargetError if an address is in blocked special-use space."""
    reason = _reject_reason(addr)
    if reason is not None:
        raise DiscoveryTargetError(f"'{entry}' resolves to {addr}: {reason} is blocked")


def parse_allowlist(raw: str) -> list[IPNetwork]:
    """Parse DISCOVERY_RANGES into the authoritative CIDR allowlist.

    The operator allowlist — not a private-IP ban — is the primary control
    on where this service may send traffic. Unparseable entries are dropped
    with a warning rather than failing the request: one typo in operator
    config should not silently widen the allowlist, and must not take the
    endpoint down either.
    """
    networks: list[IPNetwork] = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            logger.warning("Ignoring unparseable DISCOVERY_RANGES entry: %r", candidate)
    return networks


def _is_subnet(network: IPNetwork, allowed: IPNetwork) -> bool:
    """True when ``network`` is wholly contained in ``allowed``.

    The isinstance pairs are what let the type checker see a same-family
    comparison. ``subnet_of`` raises on a mixed-family argument at runtime
    too, so this states the existing requirement in a checkable way rather
    than adding one.
    """
    if isinstance(network, ipaddress.IPv4Network) and isinstance(allowed, ipaddress.IPv4Network):
        return network.subnet_of(allowed)
    if isinstance(network, ipaddress.IPv6Network) and isinstance(allowed, ipaddress.IPv6Network):
        return network.subnet_of(allowed)
    return False


def _assert_allowlisted(network: IPNetwork, entry: str, allowlist: list[IPNetwork]) -> None:
    """Raise unless a requested network sits entirely inside an allowlisted CIDR.

    Containment is checked against the whole network, not against one
    address in it: a caller supplying a CIDR must have all of it permitted,
    or a /8 request would pass on the strength of its first host.
    """
    if any(_is_subnet(network, allowed) for allowed in allowlist):
        return
    raise DiscoveryTargetError(f"'{entry}' is outside the DISCOVERY_RANGES allowlist")


def _expand(network: IPNetwork, entry: str) -> list[IPAddress]:
    """Expand a validated network into the addresses that will be probed."""
    if network.num_addresses > MAX_SCAN_TARGETS:
        raise DiscoveryTargetError(
            f"'{entry}' expands to {network.num_addresses} addresses; "
            f"the limit is {MAX_SCAN_TARGETS}"
        )
    # hosts() drops the network and broadcast addresses, which are not
    # probe targets -- except for /31 and /32 (and /127, /128), where the
    # single address itself is what is wanted.
    #
    # The two branches are deliberately not collapsed: only the concrete
    # IPv4Network/IPv6Network overrides of hosts() are typed as yielding a
    # concrete address, the shared base declares the untyped _BaseAddress.
    addresses: list[IPAddress]
    if isinstance(network, ipaddress.IPv4Network):
        addresses = list(network.hosts())
    else:
        addresses = list(network.hosts())
    return addresses or [network.network_address]


async def _resolve_hostname(name: str) -> list[IPAddress]:
    """Resolve a hostname to every address it currently maps to.

    Every returned address is validated by the caller, because a single
    name can resolve to several addresses and only one of them needs to be
    internal for a DNS-rebinding-style bypass to succeed. The resolved
    addresses are what get connected to (never the name), so the check and
    the connection cannot disagree about where the traffic went.
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, name, None, 0, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DiscoveryTargetError(f"'{name}' could not be resolved") from exc

    resolved: list[IPAddress] = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address not in resolved:
            resolved.append(address)
    if not resolved:
        raise DiscoveryTargetError(f"'{name}' could not be resolved")
    return resolved


async def resolve_scan_targets(entries: list[str], allowlist: list[IPNetwork]) -> list[str]:
    """Validate scan entries and return the concrete addresses to probe.

    The single gate between caller input and outbound traffic. An entry may
    be an IP, a CIDR, or a hostname; whichever it is, the result is a list
    of literal IP addresses, so the probe connects to exactly what was
    validated.

    Two independent conditions must both hold for every address:

    1. it falls inside an operator-allowlisted CIDR (:func:`parse_allowlist`)
    2. it is not blocked special-use space (:func:`_reject_reason`)

    Raises DiscoveryTargetError on the first violation.
    """
    targets: list[str] = []

    for raw_entry in entries:
        entry = raw_entry.strip()
        if not entry:
            continue

        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            # Not an IP or CIDR, so treat it as a hostname.
            addresses = await _resolve_hostname(entry)
            for address in addresses:
                _assert_scannable(address, entry)
                _assert_allowlisted(ipaddress.ip_network(address), entry, allowlist)
                targets.append(str(address))
        else:
            # Special-use rejection is evaluated before the allowlist, so it
            # holds unconditionally: an operator who allowlists
            # 169.254.0.0/16 still cannot reach the metadata service, and
            # the error names the real reason rather than blaming the
            # allowlist.
            addresses = _expand(network, entry)
            for address in addresses:
                _assert_scannable(address, entry)
            _assert_allowlisted(network, entry, allowlist)
            targets.extend(str(address) for address in addresses)

        if len(targets) > MAX_SCAN_TARGETS:
            raise DiscoveryTargetError(f"scan expands to more than {MAX_SCAN_TARGETS} addresses")

    # Preserve order while dropping duplicates -- overlapping entries should
    # not multiply the probe count.
    return list(dict.fromkeys(targets))


def _format_host(host: str) -> str:
    """Render an address for use in a URL authority, bracketing IPv6."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{host}]" if address.version == 6 else host


async def _probe_endpoint(
    host: str,
    port: int,
    profile: DiscoveryProfile,
    session: aiohttp.ClientSession,
) -> dict[str, Any] | None:
    """Probe a single host:port for a PenguinTech product (async).

    ``host`` is always a literal IP address already cleared by
    :func:`resolve_scan_targets` — never a caller-supplied hostname, so no
    second name resolution can land somewhere the validation did not see.
    """
    base_url = f"http://{_format_host(host)}:{port}"
    health_ep = profile.health_endpoint

    try:
        async with asyncio.timeout(5):
            started = time.perf_counter()
            async with session.get(f"{base_url}{health_ep}") as resp:
                body = (await resp.text()).lower()
                status = resp.status
                # aiohttp's ClientResponse has no `.elapsed` (that is a
                # requests attribute), so measure the round trip directly.
                elapsed_ms = int((time.perf_counter() - started) * 1000)

                # Check if any discovery signature matches
                for sig in profile.signatures:
                    server = resp.headers.get("server", "").lower()
                    if sig.lower() in body or sig.lower() in server:
                        return {
                            "product_type": profile.product_type,
                            "display_name": profile.display_name,
                            "base_url": base_url,
                            "health_endpoint": health_ep,
                            "status_code": status,
                            "response_time_ms": elapsed_ms,
                        }

                # Fallback: if health endpoint returns 200, still report as candidate
                if status == 200:
                    return {
                        "product_type": profile.product_type,
                        "display_name": f"{profile.display_name} (unconfirmed)",
                        "base_url": base_url,
                        "health_endpoint": health_ep,
                        "status_code": status,
                        "response_time_ms": elapsed_ms,
                        "unconfirmed": True,
                    }
    except (TimeoutError, OSError, aiohttp.ClientError):
        pass

    return None


async def _scan_network(network_ranges: list[str]) -> list[dict[str, Any]]:
    """Scan network ranges for PenguinTech products (async)."""
    discovered: list[dict[str, Any]] = []
    tasks: list[Any] = []

    async with aiohttp.ClientSession() as session:
        for host in network_ranges:
            for profile in DISCOVERY_PROFILES.values():
                for port in profile.ports:
                    tasks.append(_probe_endpoint(host, port, profile, session))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict) and result:
                # Deduplicate by base_url
                if not any(d["base_url"] == result["base_url"] for d in discovered):
                    result["id"] = len(discovered) + 1
                    discovered.append(result)

    return discovered


@discovery_bp.route("/scan", methods=["POST"])
@auth_required
async def trigger_scan() -> tuple[dict[str, Any], int]:
    """Trigger a network scan for PenguinTech products.

    Requires ``products:manage`` on the target tenant — a scan exists to
    produce product connections, so it is gated as the write it leads to.
    Scans only addresses inside the operator's DISCOVERY_RANGES allowlist;
    caller-supplied ``ranges`` narrow that allowlist and can never widen it.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    data = await request.get_json() or {}

    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    from .config import Config

    allowlist = parse_allowlist(getattr(Config, "DISCOVERY_RANGES", "") or "")
    requested = data.get("ranges") or []

    if requested and not allowlist:
        # Fail closed. With no operator allowlist there is nothing to
        # validate caller input against, so honouring it would mean
        # scanning wherever the caller pointed us.
        return {
            "error": "DISCOVERY_RANGES is not configured; "
            "caller-supplied ranges are not permitted"
        }, 400

    entries = requested or [str(network) for network in allowlist]
    if not entries:
        return {
            "error": "No network ranges specified. " "Provide 'ranges' or set DISCOVERY_RANGES."
        }, 400

    try:
        targets = await resolve_scan_targets(entries, allowlist)
    except DiscoveryTargetError as exc:
        return {"error": str(exc)}, 400

    results = await _scan_network(targets)
    _scan_results[tenant_id] = results

    await create_audit_log(
        user_id=user["id"],
        action="discovery.scan",
        resource_type="discovery",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return {
        "discovered": results,
        "count": len(results),
        "ranges_scanned": entries,
    }, 200


@discovery_bp.route("/results", methods=["GET"])
@auth_required
async def get_scan_results() -> tuple[dict[str, Any], int]:
    """Get latest scan results for a tenant.

    Gated on ``products:read`` for the target tenant. The previous
    ``get_user_tenant_role`` check required a direct membership row, which
    denied a delegated MSP admin their own customer's scan results — the
    same defect this phase fixed in the dashboard and audit routes.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    results = _scan_results.get(tenant_id, [])
    return {"discovered": results, "count": len(results)}, 200


@discovery_bp.route("/accept/<int:discovery_id>", methods=["POST"])
@auth_required
async def accept_discovered_product(discovery_id: int) -> tuple[dict[str, Any], int]:
    """Accept a discovered product and create a connection.

    Gated on ``products:manage`` for the target tenant. The previous check
    compared a direct membership row against the literals ``owner``/``admin``
    — both halves wrong under this phase's model: it branched on role names,
    and it refused a delegated admin who holds no membership row in the
    tenant they administer.
    """
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    data = await request.get_json() or {}

    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    results = _scan_results.get(tenant_id, [])
    discovered = next((r for r in results if r.get("id") == discovery_id), None)

    if not discovered:
        return {"error": "Discovery result not found"}, 404

    conn_id = await create_product_connection(
        tenant_id=tenant_id,
        product_type=discovered["product_type"],
        display_name=data.get("display_name", discovered["display_name"]),
        base_url=discovered["base_url"],
        auth_type=data.get("auth_type", "none"),
        api_key=data.get("api_key", ""),
        api_secret=data.get("api_secret", ""),
        health_endpoint=discovered.get("health_endpoint", "/healthz"),
        discovered=True,
    )

    if not conn_id:
        return {"error": "Failed to create product connection"}, 500

    # create_product_connection returns the new row's id; re-read it so the
    # response body is the connection record, not a bare integer.
    conn = await get_product_connection_by_id(conn_id)
    if not conn:  # pragma: no cover - row was just inserted
        return {"error": "Product connection not found after creation"}, 500

    await create_audit_log(
        user_id=user["id"],
        action="discovery.accept",
        resource_type="product_connection",
        resource_id=str(conn_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return conn, 201
