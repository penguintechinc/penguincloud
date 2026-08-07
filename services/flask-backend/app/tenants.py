"""Tenant Management APIs (async Quart).

Authorization here resolves through ``app.tenancy.authz`` rather than reading
``tenant_members`` directly, so an MSP admin's delegated authority over a
descendant tenant is honoured by ordinary endpoints and not only by the
switch endpoint. See that module for the direct-vs-delegated split.

Every response is projected through an explicit slots-dataclass DTO. No
route returns a raw ``dict(row)``: the tenants table carries a ``settings``
blob and a ``license_key`` that must never reach a response body, and an
unscoped passthrough exports them the moment a column is added.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from quart import Blueprint, request
from quart_schema import validate_request, validate_response

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
    get_tenant_product_connections,
    get_user_by_id,
    get_user_tenant_role,
    get_user_tenants,
    tenant_quota,
    DEFAULT_MAX_PRODUCTS,
    DEFAULT_MAX_USERS,
    VALID_PLANS,
    VALID_TENANT_KINDS,
    VALID_TENANT_ROLES,
)
from .tenancy import (
    EFFECTIVE_ADMIN_ROLES,
    get_hierarchy,
    invalidate_tenant,
    may_switch_to_tenant,
    resolve_effective_role,
    resolve_scopes,
    set_parent,
    tenancy_aware,
    validate_origin_authority,
    validate_parent,
)

tenants_bp = Blueprint("tenants", __name__)


# Response DTOs
#
# Field lists are explicit and exhaustive. A new column on `tenants` must be
# added here deliberately to become visible, which is the entire point --
# `settings` and `license_key` are absent by construction, not by filtering.


@dataclass(slots=True, frozen=True)
class TenantSummary:
    """The projection a caller with no membership may see.

    Used for subtree rows surfaced by include_children: a delegated admin
    needs to know a descendant exists and whether it is live, and nothing
    further until they switch into it.
    """

    id: int
    name: str
    kind: str
    status: str


@dataclass(slots=True, frozen=True)
class TenantDetail:
    """The projection a member (or delegated admin) may see."""

    id: int
    name: str
    slug: str
    display_name: str
    kind: str
    status: str
    plan: str
    parent_tenant_id: int | None
    depth: int
    owner_id: int
    max_users: int
    max_products: int
    user_role: str | None


@dataclass(slots=True, frozen=True)
class TenantListResponse:
    """Envelope for tenant listings; rows are mixed detail/summary."""

    tenants: list[dict[str, Any]]
    count: int


@dataclass(slots=True, frozen=True)
class TenantSwitchResponse:
    """Token re-issue result for a tenant switch.

    ``tenant`` is a full TenantDetail, not a TenantSummary. The caller has
    just been authorized into this tenant, so they are entitled to exactly
    what GET /tenants/<id> would hand them — and the webui populates its
    entire ``currentTenant`` from this one object (tenantStore.ts), so a
    summary here starves every consumer that reads it. LicenseGate.tsx falls
    back to "free" on a missing ``plan``, which silently hides every licensed
    feature from every user rather than failing visibly.
    """

    access_token: str
    tenant: TenantDetail
    tenant_role: str
    scope: list[str]


@dataclass(slots=True, frozen=True)
class TenantMemberResponse:
    """A tenant membership row plus the member's contact identity.

    PII policy (deliberate, not incidental): ``user_email`` and
    ``user_full_name`` ARE included, because administering a tenant means
    administering its member accounts and an MSP admin cannot do that
    against opaque user ids. NO other column from the users table is
    exposed here — not role, not is_active, not timestamps, not
    password_hash — and this DTO is the only path membership data takes to a
    response body. Adding a column to `users` must not widen this.

    Field set is reconciled with the webui's TenantMember interface
    (services/webui/src/client/types/index.ts).
    """

    id: int
    tenant_id: int
    user_id: int
    role: str
    invited_by_id: int | None
    joined_at: str | None
    user_email: str | None
    user_full_name: str | None


@dataclass(slots=True, frozen=True)
class TenantMemberListResponse:
    """Envelope for a tenant's membership list."""

    members: list[TenantMemberResponse]
    count: int


@dataclass(slots=True, frozen=True)
class RollupProduct:
    """One product connection's status inside a rollup row."""

    connection_id: int
    product: str
    status: str


@dataclass(slots=True, frozen=True)
class RollupEntry:
    """Per-tenant rollup row."""

    tenant_id: int
    tenant_name: str
    products: list[RollupProduct]


@dataclass(slots=True, frozen=True)
class RollupResponse:
    """Provider dashboard rollup envelope."""

    rollup: list[RollupEntry]
    count: int


@dataclass(slots=True)
class ReparentRequest:
    """Request body for moving a tenant within the hierarchy."""

    parent_tenant_id: int | None = None


def _status_of(tenant: dict[str, Any]) -> str:
    """Render the is_active flag as a stable string status."""
    return "active" if tenant.get("is_active") else "inactive"


def to_summary(tenant: dict[str, Any]) -> TenantSummary:
    """Project a tenant row down to the non-member-safe field set."""
    return TenantSummary(
        id=int(tenant["id"]),
        name=str(tenant.get("name", "")),
        kind=str(tenant.get("kind") or "customer"),
        status=_status_of(tenant),
    )


def to_detail(tenant: dict[str, Any], user_role: str | None) -> TenantDetail:
    """Project a tenant row to the member-visible field set."""
    parent_raw = tenant.get("parent_tenant_id")
    return TenantDetail(
        id=int(tenant["id"]),
        name=str(tenant.get("name", "")),
        slug=str(tenant.get("slug", "")),
        display_name=str(tenant.get("display_name") or tenant.get("name", "")),
        kind=str(tenant.get("kind") or "customer"),
        status=_status_of(tenant),
        plan=str(tenant.get("plan_tier") or "free"),
        parent_tenant_id=int(parent_raw) if parent_raw is not None else None,
        depth=int(tenant.get("depth") or 0),
        owner_id=int(tenant["owner_id"]),
        max_users=tenant_quota(tenant, "max_users", DEFAULT_MAX_USERS),
        max_products=tenant_quota(tenant, "max_products", DEFAULT_MAX_PRODUCTS),
        user_role=user_role,
    )


def _isoformat(value: Any) -> str | None:
    """Render a datetime column as ISO-8601, tolerating NULL or a string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def to_member(row: dict[str, Any]) -> TenantMemberResponse:
    """Project a tenant_members row (optionally user-joined) to its DTO.

    Reads only the whitelisted keys. A row carrying extra user columns —
    which get_tenant_members' join could grow at any time — cannot leak them
    through here.
    """
    invited_by = row.get("invited_by_id")
    return TenantMemberResponse(
        id=int(row["id"]),
        tenant_id=int(row["tenant_id"]),
        user_id=int(row["user_id"]),
        role=str(row.get("role") or "member"),
        invited_by_id=int(invited_by) if invited_by is not None else None,
        joined_at=_isoformat(row.get("joined_at")),
        user_email=row.get("user_email"),
        user_full_name=row.get("user_full_name"),
    )


async def _member_with_identity(
    tenant_id: int, member_user_id: int
) -> TenantMemberResponse | None:
    """Load one membership row joined to its user's contact identity."""
    db = get_db()
    rows: Any = await db(
        (db.tenant_members.tenant_id == tenant_id)
        & (db.tenant_members.user_id == member_user_id)
    ).select()
    if not rows:
        return None

    row = dict(rows[0])
    member_user = await get_user_by_id(member_user_id)
    if member_user:
        row["user_email"] = member_user.get("email")
        row["user_full_name"] = member_user.get("full_name")
    return to_member(row)


def validate_tenant_slug(slug: str) -> bool:
    """Validate tenant slug format (lowercase alphanumeric + hyphens)."""
    if not slug or len(slug) < 3 or len(slug) > 63:
        return False
    return all(c.isalnum() or c == "-" for c in slug) and slug[0].isalnum()


@tenants_bp.route("", methods=["POST"])
@auth_required
@tenancy_aware
async def create_tenant_endpoint() -> tuple[dict[str, Any], int]:
    """Create new tenant, optionally beneath an existing parent tenant.

    ``parent_tenant_id`` is what makes a hierarchy constructible at all: with
    no way to set it at creation, every tenant is a root and the delegated
    admin model has nothing to delegate over. The parent is validated for
    existence, caller authority, and depth before any row is written.
    """
    user = get_current_user()
    if not user:
        return {"error": "User not authenticated"}, 401
    data = await request.get_json()

    if not data:
        return {"error": "Request body required"}, 400

    name = data.get("name", "").strip()
    slug = data.get("slug", "").strip().lower()
    plan = data.get("plan", "free")
    kind = str(data.get("kind", "customer")).strip().lower()

    if not name or len(name) > 255:
        return {"error": "Tenant name required (1-255 chars)"}, 400

    if not slug or not validate_tenant_slug(slug):
        return {
            "error": "Invalid slug (3-63 chars, lowercase alphanumeric + hyphens)"
        }, 400

    if plan not in VALID_PLANS:
        return {"error": f"Invalid plan. Must be one of: {', '.join(VALID_PLANS)}"}, 400

    if kind not in VALID_TENANT_KINDS:
        return {
            "error": f"Invalid kind. Must be one of: {', '.join(VALID_TENANT_KINDS)}"
        }, 400

    parent_tenant_id = data.get("parent_tenant_id")
    depth = 0
    if parent_tenant_id is not None:
        if not isinstance(parent_tenant_id, int) or isinstance(parent_tenant_id, bool):
            return {"error": "parent_tenant_id must be an integer"}, 400
        validation = await validate_parent(user["id"], parent_tenant_id)
        if not validation.ok:
            return {"error": validation.error}, validation.status
        depth = validation.parent_depth + 1

    # Check slug uniqueness
    existing = await get_tenant_by_slug(slug)
    if existing is not None:
        return {"error": "Tenant slug already exists"}, 409

    tenant_id = await create_tenant(
        name,
        slug,
        user["id"],
        plan,
        parent_tenant_id=parent_tenant_id,
        kind=kind,
        depth=depth,
    )
    if tenant_id is None:
        return {"error": "Failed to create tenant"}, 500

    tenant = await get_tenant_by_id(tenant_id)
    if tenant is None:
        return {"error": "Failed to retrieve created tenant"}, 500

    # A new child falsifies every ancestor's memoised descendant set.
    await invalidate_tenant(tenant_id)

    await create_audit_log(
        user_id=user["id"],
        action="tenant.create",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    return asdict(to_detail(tenant, "owner")), 201


@tenants_bp.route("", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(TenantListResponse)
async def list_user_tenants() -> tuple[Any, int]:
    """List user's tenants (with optional subtree expansion).

    Query params:
      - include_children=true: also list tenants in subtrees the caller
        administers. Those rows come back as TenantSummary, not
        TenantDetail: holding admin over an ancestor grants the right to
        know a descendant exists, not to read its plan, quotas or owner
        without switching into it.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401

    include_children = request.args.get("include_children", "false").lower() == "true"

    user_tenants = await get_user_tenants(user["id"])
    direct_ids = {
        int(t["id"]) for t in user_tenants if isinstance(t.get("id"), int)
    }

    rows: list[dict[str, Any]] = [
        asdict(to_detail(t, t.get("user_role"))) for t in user_tenants
    ]

    if include_children:
        subtree_ids: set[int] = set()
        for tenant in user_tenants:
            tenant_id_val = tenant.get("id")
            if not isinstance(tenant_id_val, int):
                continue
            if tenant.get("user_role") not in EFFECTIVE_ADMIN_ROLES:
                continue
            try:
                hierarchy = await get_hierarchy(tenant_id_val)
            except ValueError:  # pragma: no cover - row read moments ago
                continue
            subtree_ids.update(hierarchy.descendants)

        for child_id in sorted(subtree_ids - direct_ids):
            child = await get_tenant_by_id(child_id)
            if child:
                rows.append(asdict(to_summary(child)))

    rows.sort(key=lambda r: int(r["id"]))
    return TenantListResponse(tenants=rows, count=len(rows)), 200


@tenants_bp.route("/<int:tenant_id>", methods=["GET"])
@auth_required
@tenancy_aware
async def get_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Get tenant details (members and delegated admins only)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401

    # Authorize before disclosing existence: a 404 that only an unauthorized
    # caller can distinguish from a 403 enumerates the tenant id space.
    role = await resolve_effective_role(user["id"], tenant_id)
    if not role:
        return {"error": "Not a member of this tenant"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    return asdict(to_detail(tenant, role)), 200


@tenants_bp.route("/<int:tenant_id>", methods=["PUT"])
@auth_required
@tenancy_aware
async def update_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Update tenant (admin/owner, directly or by delegation)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

    if role not in EFFECTIVE_ADMIN_ROLES:
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
    if not updated:  # pragma: no cover - row read moments ago
        return {"error": "Tenant not found"}, 404
    return asdict(to_detail(updated, role)), 200


@tenants_bp.route("/<int:tenant_id>/parent", methods=["PUT"])
@auth_required
@tenancy_aware
@validate_request(ReparentRequest)
async def reparent_tenant_endpoint(
    tenant_id: int, data: ReparentRequest
) -> tuple[Any, int]:
    """Move a tenant (and its subtree) under a new parent, or to a root.

    Requires admin authority in BOTH the tenant being moved and the
    destination parent — moving a subtree under a parent you administer is
    a grant of authority over that subtree, so authority over only one side
    is not enough. Rejects cycles, maintains ``depth`` for the whole moved
    subtree, and invalidates caches on both the old and new ancestor chains.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401

    role = await resolve_effective_role(user["id"], tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    # Origin side first, and unconditionally: a detach (parent_tenant_id
    # null) has no destination to validate, so checking only the destination
    # left the "sever a provider's authority over a whole subtree" case
    # completely ungated.
    origin = await validate_origin_authority(user["id"], tenant)
    if not origin.ok:
        return {"error": origin.error}, origin.status

    new_parent_id = data.parent_tenant_id
    if new_parent_id is not None:
        validation = await validate_parent(user["id"], new_parent_id, tenant_id)
        if not validation.ok:
            return {"error": validation.error}, validation.status

    await set_parent(tenant_id, new_parent_id)

    await create_audit_log(
        user_id=user["id"],
        action="tenant.reparent",
        resource_type="tenant",
        resource_id=str(tenant_id),
        tenant_id=tenant_id,
        changes=json.dumps({"parent_tenant_id": new_parent_id}),
        ip_address=request.remote_addr or "unknown",
    )

    moved = await get_tenant_by_id(tenant_id)
    if not moved:  # pragma: no cover - row updated moments ago
        return {"error": "Tenant not found"}, 404
    return asdict(to_detail(moved, role)), 200


@tenants_bp.route("/<int:tenant_id>", methods=["DELETE"])
@auth_required
@tenancy_aware
async def delete_tenant_endpoint(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Delete tenant (owner only).

    Stays strictly owner-gated: delegated admin confers management, not
    destruction of a tenant somebody else owns.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    tenant = await get_tenant_by_id(tenant_id)

    # Authorize before disclosing existence, matching switch and GET: a
    # missing tenant and a real one the caller does not own must be
    # indistinguishable, or the path parameter enumerates the id space.
    if not tenant or tenant.get("owner_id") != user["id"]:
        return {"error": "Only owner can delete tenant"}, 403

    db = get_db()
    # Drop cached sets while the row still exists, so the ancestor chain is
    # still walkable; after the delete the parentage is gone.
    await invalidate_tenant(tenant_id)

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
@tenancy_aware
@validate_response(TenantSwitchResponse)
async def switch_tenant(tenant_id: int) -> tuple[Any, int]:
    """Switch active tenant — returns a new JWT scoped to it.

    Allowed if the caller is a direct member of the tenant, or holds
    admin/owner in one of its ancestors (delegated MSP admin).

    Authorization runs BEFORE the existence/active check on purpose. The
    other order answers "does tenant 4127 exist?" for any authenticated
    user, because a non-existent tenant 404s while a real one they cannot
    reach 403s. Now every unauthorized caller sees the same 403 regardless.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401

    if not await may_switch_to_tenant(user["id"], tenant_id):
        return {"error": "Not authorized to access this tenant"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant or not tenant.get("is_active"):
        return {"error": "Tenant not available"}, 404

    role = await resolve_effective_role(user["id"], tenant_id)
    if role is None:  # pragma: no cover - may_switch_to_tenant just said yes
        return {"error": "Not authorized to access this tenant"}, 403

    # Resolve the caller's authority into concrete scopes at ISSUE time, so
    # downstream services authorize on `scope` without re-walking the tree.
    scopes = await resolve_scopes(user["id"], tenant_id)

    from quart import g
    from .auth import create_token_set_async

    # Home tenant is the original scoped tenant from the login session
    # If the user is switching within their hierarchy, home_tenant stays the same
    claims = g.get("current_claims", {})
    home_tenant = claims.get("ext", {}).get("home_tenant", str(tenant_id))

    token_set = await create_token_set_async(
        user_id=user["id"],
        tenant_id=str(tenant_id),
        role=user["role"],
        home_tenant=home_tenant,
        scopes=scopes,
    )

    return (
        TenantSwitchResponse(
            access_token=token_set["access_token"],
            tenant=to_detail(tenant, role),
            tenant_role=role,
            scope=scopes,
        ),
        200,
    )


@tenants_bp.route("/<int:tenant_id>/members", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(TenantMemberListResponse)
async def list_tenant_members(tenant_id: int) -> tuple[Any, int]:
    """List tenant members.

    Now reachable by delegated admins as well as direct members, which is
    precisely why the rows go through TenantMemberResponse: get_tenant_members
    returns raw joined rows, so a wider audience on the endpoint would have
    meant a wider audience for every column that join happens to carry.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

    if not role:
        return {"error": "Not a member of this tenant"}, 403

    members = [to_member(row) for row in await get_tenant_members(tenant_id)]
    return TenantMemberListResponse(members=members, count=len(members)), 200


@tenants_bp.route("/<int:tenant_id>/members", methods=["POST"])
@auth_required
@tenancy_aware
@validate_response(TenantMemberResponse, status_code=201)
async def add_tenant_member_endpoint(tenant_id: int) -> tuple[Any, int]:
    """Add member to tenant (admin/owner, directly or by delegation)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

    # Check quota
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    current_count = await get_tenant_member_count(tenant_id)
    if current_count >= tenant_quota(tenant, "max_users", DEFAULT_MAX_USERS):
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

    # Direct membership, deliberately: an ancestor admin is not "already a
    # member" of this tenant, and resolving delegation here would refuse to
    # ever enrol them.
    existing_role = await get_user_tenant_role(user_id, tenant_id)
    if existing_role:
        return {"error": "User already a member"}, 409

    member = await add_tenant_member(tenant_id, user_id, member_role, user["id"])
    if not member:
        return {"error": "Failed to add tenant member"}, 500

    await invalidate_tenant(tenant_id)

    await create_audit_log(
        user_id=user["id"],
        action="tenant.member.add",
        resource_type="tenant_member",
        resource_id=str(user_id),
        tenant_id=tenant_id,
        ip_address=request.remote_addr or "unknown",
    )

    created = await _member_with_identity(tenant_id, user_id)
    if created is None:  # pragma: no cover - row inserted moments ago
        return {"error": "Failed to retrieve created member"}, 500
    return created, 201


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["PUT"])
@auth_required
@tenancy_aware
@validate_response(TenantMemberResponse)
async def update_tenant_member_role(
    tenant_id: int, member_user_id: int
) -> tuple[Any, int]:
    """Update member role (admin/owner, directly or by delegation)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

    if role not in EFFECTIVE_ADMIN_ROLES:
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

    await invalidate_tenant(tenant_id)

    updated = await _member_with_identity(tenant_id, member_user_id)
    if updated is None:
        return {"error": "Member not found"}, 404
    return updated, 200


@tenants_bp.route("/<int:tenant_id>/members/<int:member_user_id>", methods=["DELETE"])
@auth_required
@tenancy_aware
async def remove_tenant_member(
    tenant_id: int, member_user_id: int
) -> tuple[dict[str, Any], int]:
    """Remove member from tenant (admin/owner, directly or by delegation)."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

    if role not in EFFECTIVE_ADMIN_ROLES:
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

    await invalidate_tenant(tenant_id)

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
@tenancy_aware
async def get_tenant_usage(tenant_id: int) -> tuple[dict[str, Any], int]:
    """Get tenant resource usage and quotas."""
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401
    role = await resolve_effective_role(user["id"], tenant_id)

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
                "max": tenant_quota(tenant, "max_users", DEFAULT_MAX_USERS),
            },
            "products": {
                "current": product_count,
                "max": tenant_quota(tenant, "max_products", DEFAULT_MAX_PRODUCTS),
            },
        },
    }, 200


@tenants_bp.route("/<int:tenant_id>/dashboard/rollup", methods=["GET"])
@auth_required
@tenancy_aware
@validate_response(RollupResponse)
async def get_dashboard_rollup(tenant_id: int) -> tuple[Any, int]:
    """Get per-child-tenant × per-product rollup for provider dashboard.

    Available to admin/owner in this tenant, directly or by delegation.
    Product health is stubbed until the Phase 4 adapters land; the product
    identity is not — it comes from ``product_type``.
    """
    user = get_current_user()
    if not user:  # pragma: no cover
        return {"error": "User not authenticated"}, 401

    role = await resolve_effective_role(user["id"], tenant_id)
    if role not in EFFECTIVE_ADMIN_ROLES:
        return {"error": "Admin access required"}, 403

    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    try:
        hierarchy = await get_hierarchy(tenant_id)
    except ValueError:  # pragma: no cover - row read moments ago
        return {"error": "Tenant not found"}, 404

    # Include the parent tenant itself
    all_tenant_ids: set[int] = {tenant_id}
    all_tenant_ids.update(hierarchy.descendants)

    rollup: list[RollupEntry] = []
    for child_id in sorted(all_tenant_ids):
        child_tenant = await get_tenant_by_id(child_id)
        if not child_tenant:
            continue

        connections = await get_tenant_product_connections(child_id)
        products = [
            RollupProduct(
                connection_id=int(conn["id"]),
                # product_type is the column that exists. The previous
                # `external_id` lookup was never a column on this row, so
                # .get() silently returned the "unknown" fallback for every
                # connection and the rollup carried no product identity.
                product=str(conn.get("product_type") or "unknown"),
                status=str(conn.get("health_status") or "unknown"),
            )
            for conn in connections
        ]

        rollup.append(
            RollupEntry(
                tenant_id=child_id,
                tenant_name=str(child_tenant.get("name") or f"Tenant {child_id}"),
                products=products,
            )
        )

    return RollupResponse(rollup=rollup, count=len(rollup)), 200
