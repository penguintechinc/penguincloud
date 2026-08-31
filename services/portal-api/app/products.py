"""Product Connection Management APIs (async Quart)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from quart import Blueprint, jsonify, request
from quart_schema import validate_request, validate_response

from . import flags, quotas
from .adapter_errors import UPSTREAM_RESPONSE_HEADER, AdapterCapabilityError
from .adapters import get_adapter, get_all_product_types
from .adapters.base import AdapterContext
from .authz import (
    SCOPE_PRODUCTS_MANAGE,
    SCOPE_PRODUCTS_READ,
    require_tenant_scope,
)
from .encryption import decrypt_value
from .middleware import auth_required, get_current_user
from .models import (
    DEFAULT_MAX_PRODUCTS,
    PRODUCT_TYPES,
    VALID_AUTH_TYPES,
    create_audit_log,
    create_product_connection,
    delete_product_tenant_map,
    get_db,
    get_product_connection_by_id,
    get_product_connection_raw,
    get_product_tenant_map,
    get_tenant_by_id,
    get_tenant_product_connections,
    get_tenant_product_count,
    set_product_tenant_map,
    tenant_quota,
    update_product_health,
)
from .product_view import ProductConnection, to_product_connections
from .tenancy import (
    may_bind_tenant,
    tenancy_aware,
)

logger = logging.getLogger(__name__)

products_bp = Blueprint("products", __name__)

#: Returned when a caller names a tenant they hold no authority over as the
#: target of a mapping write. Deliberately identical for "tenant does not
#: exist", "tenant exists elsewhere in the tree" and "tenant is a descendant
#: but you are only a member here" — distinguishing them turns the path
#: parameter into a tenant-existence oracle for any authenticated user.
_TENANT_NOT_IN_SCOPE = "Tenant not within this connection's authority"


@dataclass(slots=True)
class ProductTenantMapRequest:
    """Request DTO for product tenant mapping."""

    external_id: str


@dataclass(slots=True)
class ProductTenantMapResponse:
    """Response DTO for product tenant mapping."""

    id: int
    connection_id: int
    tenant_id: int
    external_kind: str
    external_id: str
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class ProductsListResponse:
    """Envelope for GET /api/v1/products.

    Attributes:
        products: The tenant's product connections, credentials masked.
        count: Number of connections returned.
    """

    products: list[ProductConnection]
    count: int


async def _get_tenant_id_from_request() -> int | None:
    """Extract current tenant ID from query param."""
    # Note: tenant_id is typically passed via query parameter
    # JWT tenant claim is already available via get_current_user()
    args = request.args
    tenant_id_str = args.get("tenant_id")
    if tenant_id_str:
        try:
            return int(tenant_id_str)
        except (ValueError, TypeError):
            return None
    return None


@products_bp.route("/types", methods=["GET"])
@auth_required
@tenancy_aware
async def list_product_types() -> tuple[dict[str, Any], int]:
    """List all available product types with metadata."""
    return {"product_types": get_all_product_types()}, 200


@products_bp.route("", methods=["POST"])
@auth_required
@tenancy_aware
async def register_product() -> tuple[dict[str, Any], int]:
    """Register a new product connection (manual)."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    tenant_id = data.get("tenant_id") or await _get_tenant_id_from_request()
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    # VALIDATE THE REQUEST BEFORE METERING IT. The quota checks used to run
    # first, so an over-quota request carrying an invalid product_type was
    # answered 402 "upgrade your plan" when the actual problem was a typo in
    # the body — a refusal that sends the operator to sales for a 400.
    product_type = data.get("product_type", "generic")
    if product_type not in PRODUCT_TYPES:
        return {"error": "Invalid product type"}, 400

    display_name = data.get("display_name", "").strip()
    base_url = data.get("base_url", "").strip()
    auth_type = data.get("auth_type", "bearer")

    if not display_name:
        return {"error": "display_name required"}, 400
    if not base_url:
        return {"error": "base_url required"}, 400
    if auth_type not in VALID_AUTH_TYPES:
        return {"error": "Invalid auth_type"}, 400

    # Flag AND licence, server-side. `penguincloud.{product}` gates whether
    # this product module is on at all; without this check the flag governed
    # only what the browser chose to render, and any direct API call
    # connected a product the deployment had switched off.
    gate = await flags.product_gate_refusal(product_type, str(user["id"]))
    if gate is not None:
        return gate

    current_count = await get_tenant_product_count(tenant_id)
    if current_count >= tenant_quota(tenant, "max_products", DEFAULT_MAX_PRODUCTS):
        return {"error": "Product connection limit reached"}, 403

    # Deployment-wide OBJECT quota, distinct from the per-tenant
    # `max_products` row quota above. That one is an operator-set ceiling on
    # one tenant; this one is what the LICENCE sells (Free 1,000, paid
    # unlimited), so both apply and neither substitutes for the other.
    #
    # See quotas.count_objects: on this product the 1,000 wall is unlikely
    # to ever bind, and that is documented rather than assumed.
    refusal = await quotas.quota_refusal("objects", await quotas.count_objects())
    if refusal is not None:
        return refusal

    conn_id = await create_product_connection(
        tenant_id=tenant_id,
        product_type=product_type,
        display_name=display_name,
        base_url=base_url,
        auth_type=auth_type,
        api_key=data.get("api_key", ""),
        api_secret=data.get("api_secret", ""),
        health_endpoint=data.get("health_endpoint", "/healthz"),
        api_version=data.get("api_version", "v1"),
    )
    if conn_id is None:
        return {"error": "Failed to create product connection"}, 500

    conn = await get_product_connection_by_id(conn_id)
    if conn is None:
        return {"error": "Failed to retrieve created product"}, 500

    await create_audit_log(
        user_id=user["id"],
        action="product.register",
        resource_type="product_connection",
        resource_id=str(conn_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return conn, 201


@products_bp.route("", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(ProductsListResponse)
async def list_products() -> tuple[Any, int]:
    """List connected products for current tenant."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    tenant_id = await _get_tenant_id_from_request()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    denied = await require_tenant_scope(user["id"], tenant_id, SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    connections = await get_tenant_product_connections(tenant_id)
    projected = to_product_connections(connections)
    return ProductsListResponse(products=projected, count=len(projected)), 200


@products_bp.route("/<int:product_id>", methods=["GET"])
@auth_required
@tenancy_aware
async def get_product(product_id: int) -> tuple[dict[str, Any], int]:
    """Get product connection details."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    return conn, 200


@products_bp.route("/<int:product_id>", methods=["PUT"])
@auth_required
@tenancy_aware
async def update_product(product_id: int) -> tuple[dict[str, Any], int]:
    """Update product connection config."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    from .encryption import encrypt_value

    db = get_db()
    update_data = {}

    for field in [
        "display_name",
        "base_url",
        "auth_type",
        "health_endpoint",
        "api_version",
    ]:
        if field in data:
            update_data[field] = data[field]

    if "api_key" in data and data["api_key"]:
        update_data["api_key"] = encrypt_value(data["api_key"])
    if "api_secret" in data and data["api_secret"]:
        update_data["api_secret"] = encrypt_value(data["api_secret"])
    if "is_active" in data:
        update_data["is_active"] = bool(data["is_active"])

    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await db(db.product_connections.id == product_id).update(**update_data)
        await db.commit()

    updated_conn = await get_product_connection_by_id(product_id)
    if updated_conn is None:
        return {"error": "Failed to retrieve updated product"}, 500
    return updated_conn, 200


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@auth_required
@tenancy_aware
async def delete_product(product_id: int) -> tuple[dict[str, Any], int]:
    """Remove product connection."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    db = get_db()
    await db(db.product_connections.id == product_id).delete()
    await db.commit()

    await create_audit_log(
        user_id=user["id"],
        action="product.delete",
        resource_type="product_connection",
        resource_id=str(product_id),
        tenant_id=conn["tenant_id"],
        ip_address=request.remote_addr,
    )

    return {"message": "Product connection removed"}, 200


@products_bp.route("/<int:product_id>/test", methods=["POST"])
@auth_required
@tenancy_aware
async def test_product_connection(product_id: int) -> tuple[Any, int]:
    """Test a product connection."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn_masked = await get_product_connection_by_id(product_id)

    if not conn_masked:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn_masked["tenant_id"], SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return {"error": "Product connection not found"}, 404

    # This route makes a live call to the product, so the module kill switch
    # applies. Checked before decryption: a disabled module's credential is
    # never decrypted, not merely never sent.
    gate = await flags.product_gate_refusal(str(conn_raw["product_type"]), str(user["id"]))
    if gate is not None:
        return gate

    # Decrypt credentials
    api_key = decrypt_value(conn_raw.get("api_key", "")) if conn_raw.get("api_key") else ""
    api_secret = decrypt_value(conn_raw.get("api_secret", "")) if conn_raw.get("api_secret") else ""

    # Try to get product tenant mapping (may not exist yet)
    mapping = await get_product_tenant_map(product_id, conn_masked["tenant_id"])

    # Build adapter context (external_id and external_kind optional for health checks)
    ctx = AdapterContext(
        connection_id=product_id,
        portal_tenant_id=conn_masked["tenant_id"],
        external_id=mapping.get("external_id", "") if mapping else "",
        external_kind=mapping.get("external_kind", "") if mapping else "",
        base_url=conn_raw.get("base_url", ""),
        auth_type=conn_raw.get("auth_type", "bearer"),
        api_key=api_key,
        api_secret=api_secret,
    )

    # Get adapter instance and check health
    adapter = get_adapter(conn_raw["product_type"], ctx)
    result = await adapter.health(ctx)

    # Convert HealthResult to dict for response
    result_dict: dict[str, Any] = {
        "status": result.status,
        "status_code": result.status_code,
        "response_time_ms": result.response_time_ms,
    }
    if result.error:
        result_dict["error"] = result.error

    await update_product_health(product_id, result.status)

    # This is a LIVE call to the product (adapter.health() above), so the
    # whole response is upstream-derived the same way adapter_failure's is
    # — `status`/`status_code`/`response_time_ms` are not free text, but
    # `error` is `str(exc)` from Transport.health_check's own exception
    # handling (adapters/transport.py), which can embed the product's real
    # hostname/IP on a connection failure. Marked unconditionally (not only
    # when `error` is present) for the same reason adapter_failure marks
    # every AdapterError subclass: the choke point is the route, not a
    # per-field judgement call about what happens to be textual today.
    response = jsonify(result_dict)
    response.headers[UPSTREAM_RESPONSE_HEADER] = "true"
    return response, 200


@products_bp.route("/<int:product_id>/health", methods=["GET"])
@auth_required
@tenancy_aware
async def get_product_health(product_id: int) -> tuple[dict[str, Any], int]:
    """Get latest health status for a product."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    return {
        "product_id": product_id,
        "health_status": conn.get("health_status", "unknown"),
        "last_health_check": conn.get("last_health_check"),
    }, 200


@products_bp.route("/<int:product_id>/schema", methods=["GET"])
@auth_required
@tenancy_aware
async def get_product_schema(product_id: int) -> tuple[dict[str, Any], int]:
    """Get management schema (available actions) for a product."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    denied = await require_tenant_scope(user["id"], conn["tenant_id"], SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return {"error": "Product connection not found"}, 404

    # A disabled module publishes no capability schema: the schema describes
    # actions the API would now refuse, and a UI that renders them builds a
    # menu of 403s.
    gate = await flags.product_gate_refusal(str(conn_raw["product_type"]), str(user["id"]))
    if gate is not None:
        return gate

    # Decrypt credentials
    api_key = decrypt_value(conn_raw.get("api_key", "")) if conn_raw.get("api_key") else ""
    api_secret = decrypt_value(conn_raw.get("api_secret", "")) if conn_raw.get("api_secret") else ""

    # Build adapter context
    ctx = AdapterContext(
        connection_id=product_id,
        portal_tenant_id=conn["tenant_id"],
        external_id="",
        external_kind="",
        base_url=conn_raw.get("base_url", ""),
        auth_type=conn_raw.get("auth_type", "bearer"),
        api_key=api_key,
        api_secret=api_secret,
    )

    # Get adapter and retrieve capabilities.
    #
    # The two failure modes are reported differently on purpose. Collapsing
    # both into `{"capabilities": []}` (as this did) tells the UI "this
    # product supports nothing", which renders identically to a healthy
    # product that genuinely exposes nothing — so a broken adapter, an
    # unreachable product or a bad credential all appeared as a working
    # integration with an empty feature set, and nobody investigates that.
    adapter = get_adapter(conn_raw["product_type"], ctx)
    try:
        capabilities = await adapter.capabilities(ctx)
    except AdapterCapabilityError:
        # The adapter answered: it cannot enumerate capabilities. An empty
        # list IS the truthful answer here.
        return {"capabilities": [], "schema_status": "unsupported"}, 200
    except Exception:
        logger.exception(
            "product_schema_unavailable",
            extra={"product_id": product_id, "product_type": conn_raw["product_type"]},
        )
        return {
            "error": "Product capabilities unavailable",
            "schema_status": "unavailable",
        }, 502

    return {"capabilities": capabilities, "schema_status": "ok"}, 200


def _validate_external_kind(product_type: str) -> tuple[str, bool]:
    """Return the required external_kind for a product type and whether it's valid.

    Returns: (required_kind, is_valid_product_type)
    """
    mapping = {
        "gough": "tenant_id",
        "nest": "tenant_id",
        "tobogganing": "tenant_id",
        "waddleai": "organization_id",
        "waddlebot": "namespace",
    }
    return mapping.get(product_type, ""), product_type in mapping


@products_bp.route("/<int:product_id>/tenants/<int:tenant_id>/map", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(ProductTenantMapResponse)
async def get_product_tenant_mapping(product_id: int, tenant_id: int) -> tuple[Any, int]:
    """Get product tenant external mapping."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return {"error": "Product connection not found"}, 404

    scope_tenant_id = int(conn["tenant_id"])
    denied = await require_tenant_scope(user["id"], scope_tenant_id, SCOPE_PRODUCTS_READ)
    if denied:
        return denied

    # The connection is authorized against ITS tenant, but the mapping being
    # read is named by a path parameter. Without this the parameter reads any
    # tenant's external mapping through a connection the caller can reach.
    if not await may_bind_tenant(user["id"], scope_tenant_id, tenant_id):
        return {"error": _TENANT_NOT_IN_SCOPE}, 403

    mapping = await get_product_tenant_map(product_id, tenant_id)
    if not mapping:
        return {"error": "Mapping not found"}, 404

    return (
        ProductTenantMapResponse(
            id=mapping["id"],
            connection_id=mapping["connection_id"],
            tenant_id=mapping["tenant_id"],
            external_kind=mapping["external_kind"],
            external_id=mapping["external_id"],
            created_at=mapping["created_at"].isoformat(),
            updated_at=mapping["updated_at"].isoformat(),
        ),
        200,
    )


@products_bp.route("/<int:product_id>/tenants/<int:tenant_id>/map", methods=["POST"])
@auth_required
@tenancy_aware
@validate_request(ProductTenantMapRequest)
@validate_response(ProductTenantMapResponse, status_code=201)
async def set_product_tenant_mapping(
    product_id: int, tenant_id: int, data: ProductTenantMapRequest
) -> tuple[Any, int]:
    """Set product tenant external mapping."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return ({"error": "Product connection not found"}, 404)

    scope_tenant_id = int(conn["tenant_id"])
    denied = await require_tenant_scope(user["id"], scope_tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    # Authorization above is against the CONNECTION's tenant; the row written
    # below is keyed by the tenant_id path parameter. Binding an unchecked
    # parameter is a cross-tenant write primitive -- gate it against the same
    # authority the switch endpoint uses.
    if not await may_bind_tenant(user["id"], scope_tenant_id, tenant_id):
        return ({"error": _TENANT_NOT_IN_SCOPE}, 403)

    required_kind, is_valid_product = _validate_external_kind(conn["product_type"])
    if not is_valid_product:
        product_type = conn["product_type"]
        return (
            {"error": f"Product type '{product_type}' unsupported for mapping"},
            400,
        )

    mapping_id = await set_product_tenant_map(
        product_id, tenant_id, required_kind, data.external_id
    )
    if mapping_id is None:
        return ({"error": "Failed to create mapping"}, 500)

    mapping = await get_product_tenant_map(product_id, tenant_id)
    if not mapping:
        return ({"error": "Failed to retrieve created mapping"}, 500)

    await create_audit_log(
        user_id=user["id"],
        action="product_tenant_map.set",
        resource_type="product_tenant_map",
        resource_id=f"{product_id}:{tenant_id}",
        tenant_id=conn["tenant_id"],
        ip_address=request.remote_addr,
    )

    return (
        ProductTenantMapResponse(
            id=mapping["id"],
            connection_id=mapping["connection_id"],
            tenant_id=mapping["tenant_id"],
            external_kind=mapping["external_kind"],
            external_id=mapping["external_id"],
            created_at=mapping["created_at"].isoformat(),
            updated_at=mapping["updated_at"].isoformat(),
        ),
        201,
    )


@products_bp.route("/<int:product_id>/tenants/<int:tenant_id>/map", methods=["PUT"])
@auth_required
@tenancy_aware
@validate_request(ProductTenantMapRequest)
@validate_response(ProductTenantMapResponse)
async def update_product_tenant_mapping(
    product_id: int, tenant_id: int, data: ProductTenantMapRequest
) -> tuple[Any, int]:
    """Update product tenant external mapping."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return ({"error": "Product connection not found"}, 404)

    scope_tenant_id = int(conn["tenant_id"])
    denied = await require_tenant_scope(user["id"], scope_tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    # Authorization above is against the CONNECTION's tenant; the row written
    # below is keyed by the tenant_id path parameter. Binding an unchecked
    # parameter is a cross-tenant write primitive -- gate it against the same
    # authority the switch endpoint uses.
    if not await may_bind_tenant(user["id"], scope_tenant_id, tenant_id):
        return ({"error": _TENANT_NOT_IN_SCOPE}, 403)

    required_kind, is_valid_product = _validate_external_kind(conn["product_type"])
    if not is_valid_product:
        product_type = conn["product_type"]
        return (
            {"error": f"Product type '{product_type}' unsupported for mapping"},
            400,
        )

    existing = await get_product_tenant_map(product_id, tenant_id)
    if not existing:
        return ({"error": "Mapping not found"}, 404)

    mapping_id = await set_product_tenant_map(
        product_id, tenant_id, required_kind, data.external_id
    )
    if mapping_id is None:
        return ({"error": "Failed to update mapping"}, 500)

    mapping = await get_product_tenant_map(product_id, tenant_id)
    if not mapping:
        return ({"error": "Failed to retrieve updated mapping"}, 500)

    await create_audit_log(
        user_id=user["id"],
        action="product_tenant_map.update",
        resource_type="product_tenant_map",
        resource_id=f"{product_id}:{tenant_id}",
        tenant_id=conn["tenant_id"],
        ip_address=request.remote_addr,
    )

    return (
        ProductTenantMapResponse(
            id=mapping["id"],
            connection_id=mapping["connection_id"],
            tenant_id=mapping["tenant_id"],
            external_kind=mapping["external_kind"],
            external_id=mapping["external_id"],
            created_at=mapping["created_at"].isoformat(),
            updated_at=mapping["updated_at"].isoformat(),
        ),
        200,
    )


@products_bp.route("/<int:product_id>/tenants/<int:tenant_id>/map", methods=["DELETE"])
@auth_required
@tenancy_aware
async def delete_product_tenant_mapping(
    product_id: int, tenant_id: int
) -> tuple[dict[str, Any], int]:
    """Delete product tenant external mapping."""
    user = get_current_user()
    if not user:  # pragma: no cover - auth_required guarantees a user
        return {"error": "User not authenticated"}, 401

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return {"error": "Product connection not found"}, 404

    scope_tenant_id = int(conn["tenant_id"])
    denied = await require_tenant_scope(user["id"], scope_tenant_id, SCOPE_PRODUCTS_MANAGE)
    if denied:
        return denied

    if not await may_bind_tenant(user["id"], scope_tenant_id, tenant_id):
        return {"error": _TENANT_NOT_IN_SCOPE}, 403

    existing = await get_product_tenant_map(product_id, tenant_id)
    if not existing:
        return {"error": "Mapping not found"}, 404

    success = await delete_product_tenant_map(product_id, tenant_id)
    if not success:
        return {"error": "Failed to delete mapping"}, 500

    await create_audit_log(
        user_id=user["id"],
        action="product_tenant_map.delete",
        resource_type="product_tenant_map",
        resource_id=f"{product_id}:{tenant_id}",
        tenant_id=conn["tenant_id"],
        ip_address=request.remote_addr,
    )

    return {"message": "Mapping deleted"}, 200
