"""Auto-Discovery Service for PenguinTech Products."""

import asyncio
import logging
import socket
from typing import Any

import aiohttp
from quart import Blueprint, request

from .adapters import ADAPTER_REGISTRY
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    create_product_connection,
    get_user_tenant_role,
)

logger = logging.getLogger(__name__)

discovery_bp = Blueprint("discovery", __name__)

# In-memory store for latest scan results per tenant
_scan_results: dict[int, list[dict]] = {}


async def _probe_endpoint(
    host: str, port: int, adapter_cls: type, session: aiohttp.ClientSession
) -> dict[str, Any] | None:
    """Probe a single host:port for a PenguinTech product (async)."""
    base_url = f"http://{host}:{port}"
    health_ep = adapter_cls.DEFAULT_HEALTH_ENDPOINT

    try:
        async with asyncio.timeout(5):
            async with session.get(f"{base_url}{health_ep}") as resp:
                body = (await resp.text()).lower()
                status = resp.status
                elapsed_ms = int((resp.elapsed or 0) * 1000)

                # Check if any discovery signature matches
                for sig in adapter_cls.DISCOVERY_SIGNATURES:
                    server = resp.headers.get("server", "").lower()
                    if sig.lower() in body or sig.lower() in server:
                        return {
                            "product_type": adapter_cls.PRODUCT_TYPE,
                            "display_name": adapter_cls.DISPLAY_NAME,
                            "base_url": base_url,
                            "health_endpoint": health_ep,
                            "status_code": status,
                            "response_time_ms": elapsed_ms,
                        }

                # Fallback: if health endpoint returns 200, still report as candidate
                if status == 200:
                    return {
                        "product_type": adapter_cls.PRODUCT_TYPE,
                        "display_name": f"{adapter_cls.DISPLAY_NAME} (unconfirmed)",
                        "base_url": base_url,
                        "health_endpoint": health_ep,
                        "status_code": status,
                        "response_time_ms": elapsed_ms,
                        "unconfirmed": True,
                    }
    except (asyncio.TimeoutError, aiohttp.ClientError, socket.error):
        pass

    return None


async def _scan_network(network_ranges: list[str]) -> list[dict[str, Any]]:
    """Scan network ranges for PenguinTech products (async)."""
    discovered: list[dict[str, Any]] = []
    tasks: list[Any] = []

    async with aiohttp.ClientSession() as session:
        for host in network_ranges:
            for _ptype, adapter_cls in ADAPTER_REGISTRY.items():
                if _ptype == "generic":
                    continue
                for port in adapter_cls.DISCOVERY_PORTS:
                    tasks.append(_probe_endpoint(host, port, adapter_cls, session))

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
    """Trigger network scan for PenguinTech products."""
    user = get_current_user()
    data = await request.get_json() or {}

    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    role = await get_user_tenant_role(user["id"], tenant_id)
    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    # Get scan targets from request or config
    from .config import Config

    ranges = data.get("ranges", [])
    if not ranges:
        default_ranges = getattr(Config, "DISCOVERY_RANGES", "")
        if default_ranges:
            ranges = [r.strip() for r in default_ranges.split(",") if r.strip()]

    if not ranges:
        return {
            "error": "No network ranges specified. "
            "Provide 'ranges' or set DISCOVERY_RANGES."
        }, 400

    results = await _scan_network(ranges)
    _scan_results[tenant_id] = results

    await create_audit_log(
        user_id=user["id"],
        action="discovery.scan",
        resource_type="discovery",
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return {
        "discovered": results,
        "count": len(results),
        "ranges_scanned": ranges,
    }, 200


@discovery_bp.route("/results", methods=["GET"])
@auth_required
async def get_scan_results() -> tuple[dict[str, Any], int]:
    """Get latest scan results."""
    user = get_current_user()
    tenant_id = request.args.get("tenant_id", type=int)

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    role = await get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    results = _scan_results.get(tenant_id, [])
    return {"discovered": results, "count": len(results)}, 200


@discovery_bp.route("/accept/<int:discovery_id>", methods=["POST"])
@auth_required
async def accept_discovered_product(discovery_id: int) -> tuple[
    dict[str, Any], int
]:
    """Accept a discovered product and create a connection."""
    user = get_current_user()
    data = await request.get_json() or {}

    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    role = await get_user_tenant_role(user["id"], tenant_id)
    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    results = _scan_results.get(tenant_id, [])
    discovered = next((r for r in results if r.get("id") == discovery_id), None)

    if not discovered:
        return {"error": "Discovery result not found"}, 404

    conn = await create_product_connection(
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

    await create_audit_log(
        user_id=user["id"],
        action="discovery.accept",
        resource_type="product_connection",
        resource_id=str(conn["id"]),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return conn, 201
