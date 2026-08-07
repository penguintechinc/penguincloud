"""Tenant Management APIs (async Quart)."""

import json
from datetime import UTC, datetime
from typing import Any

from quart import Blueprint, request

from .middleware import auth_required, get_current_user
from .models import (
    add_tenant_member,
    create_audit_log,
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
async def create_tenant_endpoint() -> tuple[dict[str, Any], int]:
    """Create new tenant (authenticated users)."""
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()
    plan = data.get("plan", "free")

    if not name or len(name) > 255:
        return {"error": "Tenant name required (1-255 chars)"}, 400

    if not slug or not validate_tenant_slug(slug):
        return {
            "error": "Invalid slug (3-63 chars, lowercase alphanumeric + hyphens)"
        }, 400

    if plan not in VALID_PLANS:
        return {"error": f"Invalid plan. Must be one of: {', '.join(VALID_PLANS)}"}, 400

    # Check slug uniqueness
    existing = await get_tenant_by_slug(slug)
    if existing is not None:
        return {"error": "Tenant slug already exists"}, 409

    tenant_id = await create_tenant(name, slug, user["id"], plan)
    if tenant_id is None:
        return {"error": "Failed to create tenant"}, 500

    tenant = await get_tenant_by_id(tenant_id)
    if tenant is None:
        return {"error": "Failed to retrieve created tenant"}, 500

    await create_audit_log(
        user_id=user["id"],
        action="tenant.create",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    return tenant, 201


@tenants_bp.route("", methods=["GET"])
@auth_required
async def list_user_tenants() -> tuple[dict[str, Any], int]:
    """List user's tenants."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    tenants = await get_user_tenants(user["id"])
    return {"tenants": tenants, "count": len(tenants)}, 200


@tenants_bp.route("/<int:tenant_id>", methods=["GET"])
@auth_required
async def get_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Get tenant details (members only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    tenant = await get_tenant_by_id(tenant_id)

    if not tenant:
        return {"error": "Tenant not found"}, 404

    role = await get_user_tenant_role(user["id"], tenant_id)
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    tenant["user_role"] = role
    return tenant, 200


@tenants_bp.route("/<int:tenant_id>", methods=["PUT"])
@auth_required
async def update_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Update tenant (admin/owner only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    db = get_db()
    update_data: dict[str, Any] = {}

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
        update_data["updated_at"] = datetime.now(UTC)
        await db(db.tenants.id == tenant_id).update(**update_data)

    await create_audit_log(
        user_id=user["id"],
        action="tenant.update",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    updated = await get_tenant_by_id(tenant_id)
    return updated or {}, 200


@tenants_bp.route("/<int:tenant_id>", methods=["DELETE"])
@auth_required
async def delete_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Delete tenant (owner only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    tenant = await get_tenant_by_id(tenant_id)

    if not tenant:
        return {"error": "Tenant not found"}, 404

    if tenant.get("owner_id") != user["id"]:
        return {"error": "Only owner can delete tenant"}, 403

    db = get_db()
    # Delete members and connections first
    await db(db.tenant_members.tenant_id == tenant_id).delete()
    await db(db.product_connections.tenant_id == tenant_id).delete()
    await db(db.tenant_product_features.tenant_id == tenant_id).delete()
    await db(db.tenants.id == tenant_id).delete()

    await create_audit_log(
        user_id=user["id"],
        action="tenant.delete",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    return {"message": "Tenant deleted"}, 200


@tenants_bp.route("/<int:tenant_id>/switch", methods=["POST"])
@auth_required
async def switch_tenant(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Switch active tenant — returns new JWT with tenant claim."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return {"error": "Not a member of this tenant"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant or not tenant.get("is_active"):
        return {"error": "Tenant not available"}, 404

    # Generate new access token with tenant_id claim
    from .auth import create_token_set_async

    token_set = await create_token_set_async(
        user_id=user["id"],
        tenant_id=str(tenant_id),
        role=user["role"],
    )

    return {
        "access_token": token_set["access_token"],
        "tenant": tenant,
        "tenant_role": role,
    }, 200


@tenants_bp.route("/<int:tenant_id>/members", methods=["GET"])
@auth_required
async def list_tenant_members(tenant_id: int) -> tuple[dict[str, Any], int]:
    """List tenant members."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return {"error": "Not a member of this tenant"}, 403

    members = await get_tenant_members(tenant_id)
    return {"members": members, "count": len(members)}, 200


@tenants_bp.route("/<int:tenant_id>/members", methods=["POST"])
@auth_required
async def add_tenant_member_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Add member to tenant (admin/owner only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    # Check quota
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    current_count = await get_tenant_member_count(tenant_id)
    if current_count >= tenant.get("max_users", 10):
        return {"error": "Tenant member limit reached"}, 403

    data = await request.get_json()
    if not data:
        return {"error": "Request body required"}, 400

    user_id = data.get("user_id")
    member_role = data.get("role", "member")

    if not user_id:
        return {"error": "user_id required"}, 400

    if member_role not in VALID_TENANT_ROLES or member_role == "owner":
        return {"error": "Valid role required (admin, member, viewer)"}, 400

    target_user = await get_user_by_id(user_id)
    if not target_user:
        return {"error": "User not found"}, 404

    # Check if already member
    existing_role = await get_user_tenant_role(user_id, tenant_id)
    if existing_role:
        return {"error": "User already a member"}, 409

    member = await add_tenant_member(tenant_id, user_id, member_role, user["id"])
    if not member:
        return {"error": "Failed to add tenant member"}, 500

    await create_audit_log(
        user_id=user["id"],
        action="tenant.member.add",
        resource_type="tenant_member",
        resource_id=str(user_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    return member, 201


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["PUT"])
@auth_required
async def update_tenant_member_role(
    tenant_id: int, member_user_id: int
) -> tuple[dict[str, Any], int]:
    """Update member role (admin/owner only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    data = await request.get_json()
    new_role = data.get("role") if data else None

    if not new_role or new_role not in ["admin", "member", "viewer"]:
        return {"error": "Valid role required (admin, member, viewer)"}, 400

    db = get_db()
    await db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).update(role=new_role)

    members = await db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).select()

    if members:
        return dict(members[0]), 200
    return {}, 200


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["DELETE"])
@auth_required
async def remove_tenant_member(
    tenant_id: int, member_user_id: int
) -> tuple[dict[str, Any], int]:
    """Remove member from tenant (admin/owner only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if role not in ["owner", "admin"]:
        return {"error": "Admin access required"}, 403

    # Cannot remove the owner
    tenant = await get_tenant_by_id(tenant_id)
    if tenant and tenant.get("owner_id") == member_user_id:
        return {"error": "Cannot remove tenant owner"}, 400

    db = get_db()
    deleted = await db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).delete()

    if not deleted:
        return {"error": "Member not found"}, 404

    await create_audit_log(
        user_id=user["id"],
        action="tenant.member.remove",
        resource_type="tenant_member",
        resource_id=str(member_user_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    return {"message": "Member removed"}, 200


@tenants_bp.route("/<int:tenant_id>/usage", methods=["GET"])
@auth_required
async def get_tenant_usage(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Get tenant resource usage and quotas."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await get_user_tenant_role(user["id"], tenant_id)

    if not role:
        return {"error": "Not a member of this tenant"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    member_count = await get_tenant_member_count(tenant_id)
    product_count = await get_tenant_product_count(tenant_id)

    return {
        "tenant_id": tenant_id,
        "plan": tenant.get("plan_tier", "free"),
        "usage": {
            "members": {
                "current": member_count,
                "max": tenant.get("max_users", 10),
            },
            "products": {
                "current": product_count,
                "max": tenant.get("max_products", 5),
            },
        },
    }, 200
