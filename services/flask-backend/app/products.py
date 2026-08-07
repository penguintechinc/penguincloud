"""Product Connection Management APIs (async Quart)."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_request, validate_response

from .adapters import get_adapter, get_all_product_types
from .middleware import auth_required, get_current_user
from .models import (
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
    DEFAULT_MAX_PRODUCTS,
    PRODUCT_TYPES,
    VALID_AUTH_TYPES,
)
from .tenancy import (
    EFFECTIVE_ADMIN_ROLES,
    may_bind_tenant,
    resolve_effective_role,
    tenancy_aware,
)

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
    if not user:
        return {"error": "User not authenticated"}, 401
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    tenant_id = data.get("tenant_id") or await _get_tenant_id_from_request()
    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    role = await resolve_effective_role(user["id"], tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

    # Check quota
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    current_count = await get_tenant_product_count(tenant_id)
    if current_count >= tenant_quota(tenant, "max_products", DEFAULT_MAX_PRODUCTS):
        return {"error": "Product connection limit reached"}, 403

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
async def list_products() -> tuple[dict[str, Any], int]:
    """List connected products for current tenant."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    tenant_id = await _get_tenant_id_from_request()

    if not tenant_id:
        return {"error": "tenant_id required"}, 400

    role = await resolve_effective_role(user["id"], tenant_id)
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    connections = await get_tenant_product_connections(tenant_id)
    return {"products": connections, "count": len(connections)}, 200


@products_bp.route("/<int:product_id>", methods=["GET"])
@auth_required
@tenancy_aware
async def get_product(product_id: int) -> tuple[dict[str, Any], int]:
    """Get product connection details."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn["tenant_id"])
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    return conn, 200


@products_bp.route("/<int:product_id>", methods=["PUT"])
@auth_required
@tenancy_aware
async def update_product(product_id: int) -> tuple[dict[str, Any], int]:
    """Update product connection config."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn["tenant_id"])
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

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
    if not user:
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn["tenant_id"])
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

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
async def test_product_connection(product_id: int) -> tuple[dict[str, Any], int]:
    """Test a product connection."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    conn_masked = await get_product_connection_by_id(product_id)

    if not conn_masked:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn_masked["tenant_id"])
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return {"error": "Product connection not found"}, 404
    adapter = get_adapter(conn_raw["product_type"], conn_raw)
    result = await asyncio.to_thread(adapter.health_check)

    await update_product_health(product_id, result["status"])

    return result, 200


@products_bp.route("/<int:product_id>/health", methods=["GET"])
@auth_required
@tenancy_aware
async def get_product_health(product_id: int) -> tuple[dict[str, Any], int]:
    """Get latest health status for a product."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn["tenant_id"])
    if not role:
        return {"error": "Not a member of this tenant"}, 403

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
    if not user:
        return {"error": "User not authenticated"}, 401
    conn = await get_product_connection_by_id(product_id)

    if not conn:
        return {"error": "Product connection not found"}, 404

    role = await resolve_effective_role(user["id"], conn["tenant_id"])
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    conn_raw = await get_product_connection_raw(product_id)
    if not conn_raw:
        return {"error": "Product connection not found"}, 404
    adapter = get_adapter(conn_raw["product_type"], conn_raw)
    schema = await asyncio.to_thread(adapter.get_management_schema)

    return schema, 200


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
async def get_product_tenant_mapping(
    product_id: int, tenant_id: int
) -> tuple[Any, int]:
    """Get product tenant external mapping."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return {"error": "Product connection not found"}, 404

    scope_tenant_id = int(conn["tenant_id"])
    role = await resolve_effective_role(user["id"], scope_tenant_id)
    if not role:
        return {"error": "Not a member of this tenant"}, 403

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
    if not user:
        return ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return ({"error": "Product connection not found"}, 404)

    scope_tenant_id = int(conn["tenant_id"])
    role = await resolve_effective_role(user["id"], scope_tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return ({"error": "Admin access required"}, 403)

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
            {
                "error": f"Product type '{product_type}' unsupported for mapping"
            },
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
    if not user:
        return ({"error": "User not authenticated"}, 401)

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return ({"error": "Product connection not found"}, 404)

    scope_tenant_id = int(conn["tenant_id"])
    role = await resolve_effective_role(user["id"], scope_tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return ({"error": "Admin access required"}, 403)

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
            {
                "error": f"Product type '{product_type}' unsupported for mapping"
            },
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
    if not user:
        return {"error": "User not authenticated"}, 401

    conn = await get_product_connection_by_id(product_id)
    if not conn:
        return {"error": "Product connection not found"}, 404

    scope_tenant_id = int(conn["tenant_id"])
    role = await resolve_effective_role(user["id"], scope_tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

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
