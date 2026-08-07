"""Tenant Management APIs."""

import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from .middleware import auth_required, get_current_user
from .models import (
    create_tenant,
    get_db,
    get_tenant_by_id,
    get_tenant_by_slug,
    get_tenant_member_count,
    get_tenant_members,
    get_tenant_product_count,
    get_user_by_id,
    get_user_tenant_role,
    get_user_tenants,
    add_tenant_member,
    create_audit_log,
    VALID_PLANS,
    VALID_TENANT_ROLES,
)

tenants_bp = Blueprint("tenants", __name__)


def validate_tenant_slug(slug: str) -> bool:
    """Validate tenant slug format (lowercase alphanumeric + hyphens)."""
    if not slug or len(slug) < 3 or len(slug) > 63:
        return False
    return all(c.isalnum() or c == "-" for c in slug) and slug[0].isalnum()


@tenants_bp.route("", methods=["POST"])
@auth_required
def create_tenant_endpoint():
    """Create new tenant (authenticated users)."""
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    plan = data.get("plan", "free")

    if not name or len(name) > 255:
        return jsonify({"error": "Tenant name required (1-255 chars)"}), 400

    if not slug or not validate_tenant_slug(slug):
        return jsonify(
            {"error": "Invalid slug (3-63 chars, lowercase alphanumeric + hyphens)"}
        ), 400

    if plan not in VALID_PLANS:
        return jsonify({"error": f"Invalid plan. Must be one of: {', '.join(VALID_PLANS)}"}), 400

    # Check slug uniqueness
    existing = get_tenant_by_slug(slug)
    if existing:
        return jsonify({"error": "Tenant slug already exists"}), 409

    tenant = create_tenant(name, slug, user["id"], display_name, plan)

    create_audit_log(
        user_id=user["id"],
        action="tenant.create",
        resource_type="tenant",
        resource_id=str(tenant["id"]),
        tenant_id=tenant["id"],
        ip_address=request.remote_addr,
    )

    return jsonify(tenant), 201


@tenants_bp.route("", methods=["GET"])
@auth_required
def list_user_tenants():
    """List user's tenants."""
    user = get_current_user()
    tenants = get_user_tenants(user["id"])
    return jsonify({"tenants": tenants, "count": len(tenants)}), 200


@tenants_bp.route("/<int:tenant_id>", methods=["GET"])
@auth_required
def get_tenant_endpoint(tenant_id: int):
    """Get tenant details (members only)."""
    user = get_current_user()
    tenant = get_tenant_by_id(tenant_id)

    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    role = get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    tenant["user_role"] = role
    return jsonify(tenant), 200


@tenants_bp.route("/<int:tenant_id>", methods=["PUT"])
@auth_required
def update_tenant_endpoint(tenant_id: int):
    """Update tenant (admin/owner only)."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    db = get_db()
    update_data = {}

    if "name" in data:
        name = data["name"].strip()
        if name and len(name) <= 255:
            update_data["name"] = name

    if "display_name" in data:
        update_data["display_name"] = data["display_name"].strip()

    if "settings" in data:
        update_data["settings"] = json.dumps(data["settings"])

    if "plan" in data and role == "owner":
        if data["plan"] in VALID_PLANS:
            update_data["plan_tier"] = data["plan"]

    if "is_active" in data and role == "owner":
        update_data["is_active"] = bool(data["is_active"])

    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        db(db.tenants.id == tenant_id).update(**update_data)
        db.commit()

    create_audit_log(
        user_id=user["id"],
        action="tenant.update",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return jsonify(get_tenant_by_id(tenant_id)), 200


@tenants_bp.route("/<int:tenant_id>", methods=["DELETE"])
@auth_required
def delete_tenant_endpoint(tenant_id: int):
    """Delete tenant (owner only)."""
    user = get_current_user()
    tenant = get_tenant_by_id(tenant_id)

    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    if tenant.get("owner_id") != user["id"]:
        return jsonify({"error": "Only owner can delete tenant"}), 403

    db = get_db()
    # Delete members and connections first
    db(db.tenant_members.tenant_id == tenant_id).delete()
    db(db.product_connections.tenant_id == tenant_id).delete()
    db(db.tenant_product_features.tenant_id == tenant_id).delete()
    db(db.tenants.id == tenant_id).delete()
    db.commit()

    create_audit_log(
        user_id=user["id"],
        action="tenant.delete",
        resource_type="tenant",
        resource_id=str(tenant_id),
        ip_address=request.remote_addr,
    )

    return jsonify({"message": "Tenant deleted"}), 200


@tenants_bp.route("/<int:tenant_id>/switch", methods=["POST"])
@auth_required
def switch_tenant(tenant_id: int):
    """Switch active tenant — returns new JWT with tenant claim."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    tenant = get_tenant_by_id(tenant_id)
    if not tenant or not tenant.get("is_active"):
        return jsonify({"error": "Tenant not available"}), 404

    # Generate new access token with tenant_id claim
    from .auth import create_access_token
    token = create_access_token(
        user_id=user["id"],
        role=user["role"],
        extra_claims={"current_tenant_id": tenant_id, "tenant_role": role},
    )

    return jsonify({
        "access_token": token,
        "tenant": tenant,
        "tenant_role": role,
    }), 200


@tenants_bp.route("/<int:tenant_id>/members", methods=["GET"])
@auth_required
def list_tenant_members(tenant_id: int):
    """List tenant members."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    members = get_tenant_members(tenant_id)
    return jsonify({"members": members, "count": len(members)}), 200


@tenants_bp.route("/<int:tenant_id>/members", methods=["POST"])
@auth_required
def add_tenant_member_endpoint(tenant_id: int):
    """Add member to tenant (admin/owner only)."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    # Check quota
    tenant = get_tenant_by_id(tenant_id)
    current_count = get_tenant_member_count(tenant_id)
    if current_count >= tenant.get("max_users", 10):
        return jsonify({"error": "Tenant member limit reached"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    user_id = data.get("user_id")
    member_role = data.get("role", "member")

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    if member_role not in VALID_TENANT_ROLES or member_role == "owner":
        return jsonify({"error": "Valid role required (admin, member, viewer)"}), 400

    target_user = get_user_by_id(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    # Check if already member
    existing_role = get_user_tenant_role(user_id, tenant_id)
    if existing_role:
        return jsonify({"error": "User already a member"}), 409

    member = add_tenant_member(tenant_id, user_id, member_role, user["id"])

    create_audit_log(
        user_id=user["id"],
        action="tenant.member.add",
        resource_type="tenant_member",
        resource_id=str(user_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return jsonify(member), 201


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["PUT"])
@auth_required
def update_tenant_member_role(tenant_id: int, member_user_id: int):
    """Update member role (admin/owner only)."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json()
    new_role = data.get("role") if data else None

    if not new_role or new_role not in ["admin", "member", "viewer"]:
        return jsonify({"error": "Valid role required (admin, member, viewer)"}), 400

    db = get_db()
    db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).update(role=new_role)
    db.commit()

    member = db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).select().first()

    return jsonify(member.as_dict() if member else {}), 200


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["DELETE"])
@auth_required
def remove_tenant_member(tenant_id: int, member_user_id: int):
    """Remove member from tenant (admin/owner only)."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return jsonify({"error": "Admin access required"}), 403

    # Cannot remove the owner
    tenant = get_tenant_by_id(tenant_id)
    if tenant and tenant.get("owner_id") == member_user_id:
        return jsonify({"error": "Cannot remove tenant owner"}), 400

    db = get_db()
    deleted = db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).delete()
    db.commit()

    if not deleted:
        return jsonify({"error": "Member not found"}), 404

    create_audit_log(
        user_id=user["id"],
        action="tenant.member.remove",
        resource_type="tenant_member",
        resource_id=str(member_user_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr,
    )

    return jsonify({"message": "Member removed"}), 200


@tenants_bp.route("/<int:tenant_id>/usage", methods=["GET"])
@auth_required
def get_tenant_usage(tenant_id: int):
    """Get tenant resource usage and quotas."""
    user = get_current_user()
    role = get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return jsonify({"error": "Not a member of this tenant"}), 403

    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    member_count = get_tenant_member_count(tenant_id)
    product_count = get_tenant_product_count(tenant_id)

    return jsonify({
        "tenant_id": tenant_id,
        "plan": tenant.get("plan_tier", "free"),
        "usage": {
            "members": {"current": member_count, "max": tenant.get("max_users", 10)},
            "products": {"current": product_count, "max": tenant.get("max_products", 5)},
        },
    }), 200
