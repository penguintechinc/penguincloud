"""Product Connection Management APIs."""

from flask import Blueprint, jsonify, request

from .adapters import get_adapter, get_adapter_metadata, get_all_product_types
from .middleware import auth_required, get_current_user
from .models import (
    create_audit_log,
    create_product_connection,
    get_db,
    get_product_connection_by_id,
    get_product_connection_raw,
    get_tenant_by_id,
    get_tenant_product_connections,
    get_tenant_product_count,
    get_user_tenant_role,
    PRODUCT_TYPES,
    VALID_AUTH_TYPES,
)

products_bp = Blueprint("products", __name__)


def _get_tenant_id_from_request():
    """Extract current tenant ID from JWT claims or query param."""
    from .middleware import decode_token, get_token_from_header

    token = get_token_from_header()
    if token:
        payload = decode_token(token)
        if payload and payload.get("current_tenant_id"):
            return payload["current_tenant_id"]
    return request.args.get("tenant_id", type=int)


@products_bp.route("/types", methods=["GET"])
@auth_required
def list_product_types():
    """List all available product types with metadata."""
    return jsonify({"product_types": get_all_product_types()}), 200


@products_bp.route("", methods=["POST"])
@auth_required
def register_product():
    """Register a new product connection (manual)."""
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    tenant_id = data.get("tenant_id") or _get_tenant_id_from_request()
    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    # Check quota
    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    current_count = get_tenant_product_count(tenant_id)
    if current_count >= tenant.get("max_products", 5):
        return jsonify({"error": "Product connection limit reached"}), 403

    product_type = data.get("product_type", "generic")
    if product_type not in PRODUCT_TYPES:
        return jsonify({"error": f"Invalid product type"}), 400

    display_name = data.get("display_name", "").strip()
    base_url = data.get("base_url", "").strip()
    auth_type = data.get("auth_type", "bearer")

    if not display_name:
        return jsonify({"error": "display_name required"}), 400
    if not base_url:
        return jsonify({"error": "base_url required"}), 400
    if auth_type not in VALID_AUTH_TYPES:
        return jsonify({"error": "Invalid auth_type"}), 400

    conn = create_product_connection(
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

    create_audit_log(
        user_id=user["id"],
        action="product.register",
        resource_type="product_connection",
        resource_id=str(conn["id"]),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return jsonify(conn), 201


@products_bp.route("", methods=["GET"])
@auth_required
def list_products():
    """List connected products for current tenant."""
    user = get_current_user()
    tenant_id = _get_tenant_id_from_request()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    connections = get_tenant_product_connections(tenant_id)
    return jsonify({"products": connections, "count": len(connections)}), 200


@products_bp.route("/<int:product_id>", methods=["GET"])
@auth_required
def get_product(product_id: int):
    """Get product connection details."""
    user = get_current_user()
    conn = get_product_connection_by_id(product_id)

    if not conn:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn["tenant_id"])
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    return jsonify(conn), 200


@products_bp.route("/<int:product_id>", methods=["PUT"])
@auth_required
def update_product(product_id: int):
    """Update product connection config."""
    user = get_current_user()
    conn = get_product_connection_by_id(product_id)

    if not conn:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn["tenant_id"])
    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    from .encryption import encrypt_value
    from datetime import datetime

    db = get_db()
    update_data = {}

    for field in ["display_name", "base_url", "auth_type", "health_endpoint", "api_version"]:
        if field in data:
            update_data[field] = data[field]

    if "api_key" in data and data["api_key"]:
        update_data["api_key"] = encrypt_value(data["api_key"])
    if "api_secret" in data and data["api_secret"]:
        update_data["api_secret"] = encrypt_value(data["api_secret"])
    if "is_active" in data:
        update_data["is_active"] = bool(data["is_active"])

    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        db(db.product_connections.id == product_id).update(**update_data)
        db.commit()

    return jsonify(get_product_connection_by_id(product_id)), 200


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@auth_required
def delete_product(product_id: int):
    """Remove product connection."""
    user = get_current_user()
    conn = get_product_connection_by_id(product_id)

    if not conn:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn["tenant_id"])
    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    db = get_db()
    db(db.product_connections.id == product_id).delete()
    db.commit()

    create_audit_log(
        user_id=user["id"],
        action="product.delete",
        resource_type="product_connection",
        resource_id=str(product_id),
        tenant_id=conn["tenant_id"],
        ip_address=request.remote_addr,
    )

    return jsonify({"message": "Product connection removed"}), 200


@products_bp.route("/<int:product_id>/test", methods=["POST"])
@auth_required
def test_product_connection(product_id: int):
    """Test a product connection."""
    user = get_current_user()
    conn_masked = get_product_connection_by_id(product_id)

    if not conn_masked:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn_masked["tenant_id"])
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    conn_raw = get_product_connection_raw(product_id)
    adapter = get_adapter(conn_raw["product_type"], conn_raw)
    result = adapter.health_check()

    from .models import update_product_health
    update_product_health(product_id, result["status"])

    return jsonify(result), 200


@products_bp.route("/<int:product_id>/health", methods=["GET"])
@auth_required
def get_product_health(product_id: int):
    """Get latest health status for a product."""
    user = get_current_user()
    conn = get_product_connection_by_id(product_id)

    if not conn:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn["tenant_id"])
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    return jsonify({
        "product_id": product_id,
        "health_status": conn.get("health_status", "unknown"),
        "last_health_check": conn.get("last_health_check"),
    }), 200


@products_bp.route("/<int:product_id>/schema", methods=["GET"])
@auth_required
def get_product_schema(product_id: int):
    """Get management schema (available actions) for a product."""
    user = get_current_user()
    conn = get_product_connection_by_id(product_id)

    if not conn:
        return jsonify({"error": "Product connection not found"}), 404

    role = get_user_tenant_role(user["id"], conn["tenant_id"])
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    conn_raw = get_product_connection_raw(product_id)
    adapter = get_adapter(conn_raw["product_type"], conn_raw)
    schema = adapter.get_management_schema()

    return jsonify(schema), 200
