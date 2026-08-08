"""Delegated-admin authorization for the tenant hierarchy.

One place decides "may this user act on this tenant, and as what role".
Endpoints call :func:`resolve_effective_role` instead of reading
``tenant_members`` directly, so delegated MSP authority is a property of the
model rather than something each route re-derives (and half of them forget).

Two distinct questions, deliberately separate functions:

* :func:`resolve_effective_role` — *what may this caller do here*. Direct
  membership wins; failing that, owner/admin in any ancestor confers
  ``admin`` on the descendant. This is what route authorization asks.
* :func:`may_bind_tenant` — *may this caller name this tenant as the target
  of a write scoped to another tenant*. Guards path/body parameters that
  identify a tenant other than the one already authorized against.

Membership predicates that must stay strictly direct (is user X already a
member of tenant Y?) keep calling ``models.get_user_tenant_role``; granting
a delegated answer there would let an ancestor admin appear as a member of
every descendant.
"""

from __future__ import annotations

from typing import Final

from app.models import get_user_tenant_role

from .resolver import get_ancestors, get_descendants

#: Roles that confer administrative authority within a tenant.
ADMIN_ROLES: Final[frozenset[str]] = frozenset({"owner", "admin"})

#: Effective role handed to a caller whose authority comes from an ancestor
#: rather than from a ``tenant_members`` row in the target tenant. It is a
#: distinct string so responses and audit records can tell delegated
#: authority apart from a real membership, while still comparing equal to
#: nothing in ``VALID_TENANT_ROLES`` by accident.
DELEGATED_ADMIN: Final[str] = "delegated_admin"

#: Effective roles that satisfy an "admin or owner" gate on an endpoint.
EFFECTIVE_ADMIN_ROLES: Final[frozenset[str]] = ADMIN_ROLES | {DELEGATED_ADMIN}


async def has_delegated_admin(user_id: int, tenant_id: int) -> bool:
    """True when the user holds owner/admin in any ancestor of a tenant.

    This is the single predicate behind every delegated-authority decision:
    tenant switching, cross-tenant binds, and effective-role resolution all
    reduce to it, so they cannot drift apart.
    """
    ancestors = await get_ancestors(tenant_id)
    for ancestor_id in sorted(ancestors):
        if await get_user_tenant_role(user_id, ancestor_id) in ADMIN_ROLES:
            return True
    return False


async def resolve_effective_role(user_id: int, tenant_id: int) -> str | None:
    """Resolve the role a user effectively holds in a tenant.

    Returns the direct ``tenant_members`` role when one exists, otherwise
    :data:`DELEGATED_ADMIN` when the user administers an ancestor, otherwise
    None. Callers gate on membership with ``if not role`` and on admin
    rights with ``role in EFFECTIVE_ADMIN_ROLES``.
    """
    direct_role = await get_user_tenant_role(user_id, tenant_id)
    if direct_role:
        return direct_role
    if await has_delegated_admin(user_id, tenant_id):
        return DELEGATED_ADMIN
    return None


async def may_switch_to_tenant(user_id: int, tenant_id: int) -> bool:
    """True when the user may make a tenant their active tenant.

    Direct membership of any role, or delegated admin from an ancestor.
    """
    return await resolve_effective_role(user_id, tenant_id) is not None


async def may_bind_tenant(
    user_id: int, scope_tenant_id: int, target_tenant_id: int
) -> bool:
    """True when a write authorized against one tenant may name another.

    Endpoints that authorize against a resource's owning tenant
    (``scope_tenant_id``) but then bind a caller-supplied
    ``target_tenant_id`` must run this check, or the path parameter is an
    unauthenticated cross-tenant write primitive.

    Allowed when the target *is* the scope tenant, or is a descendant of it
    and the caller administers the scope tenant (directly or by delegation).
    """
    if target_tenant_id == scope_tenant_id:
        return True

    scope_role = await resolve_effective_role(user_id, scope_tenant_id)
    if scope_role not in EFFECTIVE_ADMIN_ROLES:
        return False

    return target_tenant_id in await get_descendants(scope_tenant_id)


# Resolved scope bundles
#
# Roles are bundles of scopes expanded at token issue time (security.md:
# authorization decisions are made on `scope`, never on a role name). The
# token carries the expanded list for the ACTIVE tenant only -- no
# descendant id list ever goes into a token.

_ROLE_SCOPE_BUNDLES: Final[dict[str, tuple[str, ...]]] = {
    "owner": (
        "tenants:read",
        "tenants:manage",
        "tenants:delete",
        "members:read",
        "members:manage",
        "products:read",
        "products:manage",
    ),
    "admin": (
        "tenants:read",
        "tenants:manage",
        "members:read",
        "members:manage",
        "products:read",
        "products:manage",
    ),
    DELEGATED_ADMIN: (
        "tenants:read",
        "tenants:manage",
        "members:read",
        "members:manage",
        "products:read",
        "products:manage",
    ),
    "member": (
        "tenants:read",
        "members:read",
        "products:read",
    ),
    "viewer": (
        "tenants:read",
        "members:read",
        "products:read",
    ),
}

#: Granted on top of the role bundle when the caller administers at least
#: one descendant of the active tenant. Names the *capability*, never the
#: descendant ids, so the claim stays a fixed size regardless of fleet size.
SCOPE_MANAGE_DESCENDANTS: Final[str] = "tenants:manage:descendants"

#: Issued with a token that has no real active tenant (login, refresh). The
#: holder can enumerate their tenants and switch into one; nothing else.
UNSCOPED_SCOPES: Final[tuple[str, ...]] = ("tenants:read", "tenants:switch")


async def resolve_scopes(user_id: int, tenant_id: int) -> list[str]:
    """Expand a user's authority in a tenant into a sorted scope list.

    Combines the role bundle for their effective role with
    :data:`SCOPE_MANAGE_DESCENDANTS` when they administer any descendant of
    the active tenant. Returns an empty list when the user has no authority
    at all, which is what an unauthorized switch attempt would have produced
    had it not already been rejected.
    """
    role = await resolve_effective_role(user_id, tenant_id)
    if role is None:
        return []

    scopes: set[str] = set(_ROLE_SCOPE_BUNDLES.get(role, ()))
    scopes.add("tenants:switch")

    if role in EFFECTIVE_ADMIN_ROLES and await get_descendants(tenant_id):
        scopes.add(SCOPE_MANAGE_DESCENDANTS)

    return sorted(scopes)
