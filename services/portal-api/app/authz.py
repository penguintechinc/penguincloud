"""Scope-based authorization for the portal's own endpoints.

security.md is unambiguous: authorization decisions are made on ``scope``,
never on a role name. Scopes were already *issued* at token time by
:func:`app.tenancy.authz.resolve_scopes`, but every route still re-derived a
role and compared it against a name list, so the claim was decorative. This
module is the consuming half.

Three entry points, one enforcement primitive
---------------------------------------------
Everything below funnels through :class:`~app.adapters.base.RBACEnforcer`
and :func:`~app.tenancy.authz.resolve_scopes` — the same pair the proxy's
``RouteRule`` allowlist uses — so a portal route and a proxied product route
cannot drift into disagreeing about what a scope means.

* :func:`require_scope` with no ``tenant_arg`` — gates on the scope list the
  token was issued with, i.e. the caller's authority in their *active*
  tenant. Use for routes that act on the active tenant or on nothing
  tenant-shaped at all (profile, dashboard, platform catalogues).
* :func:`require_scope` with ``tenant_arg`` — the route names a tenant in its
  path, which may not be the active one. Gates on the scopes resolved *for
  that tenant*.
* :func:`require_tenant_scope` — the in-body form, for routes that must load
  a resource before they know which tenant owns it (``product_id`` ->
  ``connection.tenant_id``). Returns an error tuple to return, or None.

Why the target tenant, not just the token claim
-----------------------------------------------
A token carries the scope bundle for one active tenant. A route that names a
different tenant in its path is asking a different question — "what may this
caller do *there*" — and the answer is whatever ``resolve_scopes`` says for
that tenant. Resolving it is what preserves delegated administration: an MSP
admin whose authority over a customer tenant comes from an ancestor holds no
``tenant_members`` row there, so a check against the token's claim alone
would either deny them (breaking delegation) or force descendant ids into
the token (unbounded claim size). ``resolve_scopes`` -> ``resolve_effective_role``
already answers it correctly, and is the same function that minted the claim,
so the two paths agree by construction rather than by convention.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, Final, ParamSpec, TypeVar

from quart import g

from .adapters.base import RBACEnforcer
from .middleware import get_current_user
from .tenancy.authz import resolve_scopes

P = ParamSpec("P")
R = TypeVar("R")

__all__ = [
    "SCOPE_TENANTS_READ",
    "SCOPE_TENANTS_MANAGE",
    "SCOPE_TENANTS_DELETE",
    "SCOPE_TENANTS_BILLING",
    "SCOPE_TENANTS_SWITCH",
    "SCOPE_MEMBERS_READ",
    "SCOPE_MEMBERS_MANAGE",
    "SCOPE_PRODUCTS_READ",
    "SCOPE_PRODUCTS_MANAGE",
    "SCOPE_USERS_READ",
    "SCOPE_USERS_MANAGE",
    "SCOPE_AUDIT_READ",
    "SCOPE_TEAMS_READ",
    "SCOPE_TEAMS_MANAGE",
    "SCOPE_TEAMS_DELETE",
    "current_scopes",
    "require_scope",
    "require_tenant_scope",
    "require_team_scope",
    "has_tenant_scope",
    "team_scopes",
]

# Scope names, defined once. Routes import these rather than repeating string
# literals, so a typo is an ImportError at startup instead of a permanently
# unsatisfiable gate discovered in production.
SCOPE_TENANTS_READ: Final[str] = "tenants:read"
SCOPE_TENANTS_MANAGE: Final[str] = "tenants:manage"
SCOPE_TENANTS_DELETE: Final[str] = "tenants:delete"
#: Plan tier and activation changes. Owner bundle only — deliberately
#: absent from delegated admin, who manages a tenant without owning it.
SCOPE_TENANTS_BILLING: Final[str] = "tenants:billing"
SCOPE_TENANTS_SWITCH: Final[str] = "tenants:switch"
SCOPE_MEMBERS_READ: Final[str] = "members:read"
SCOPE_MEMBERS_MANAGE: Final[str] = "members:manage"
SCOPE_PRODUCTS_READ: Final[str] = "products:read"
SCOPE_PRODUCTS_MANAGE: Final[str] = "products:manage"

# Platform-level scopes. Not tenant-scoped: they come from the user row's
# role, expanded into the token by app.tenancy.authz.platform_scopes.
SCOPE_USERS_READ: Final[str] = "users:read"
SCOPE_USERS_MANAGE: Final[str] = "users:manage"
SCOPE_AUDIT_READ: Final[str] = "audit:read"

# Team scopes. Teams carry their own membership table with its own role
# column, independent of tenant membership, so these are resolved per-team
# at request time (see team_scopes) rather than issued into the token: a
# token would otherwise have to enumerate every team the caller belongs to
# and re-issue whenever any of those memberships changed.
SCOPE_TEAMS_READ: Final[str] = "teams:read"
SCOPE_TEAMS_MANAGE: Final[str] = "teams:manage"
SCOPE_TEAMS_DELETE: Final[str] = "teams:delete"

_TEAM_ROLE_SCOPES: Final[dict[str, tuple[str, ...]]] = {
    "owner": (SCOPE_TEAMS_READ, SCOPE_TEAMS_MANAGE, SCOPE_TEAMS_DELETE),
    "admin": (SCOPE_TEAMS_READ, SCOPE_TEAMS_MANAGE),
    "member": (SCOPE_TEAMS_READ,),
    "viewer": (SCOPE_TEAMS_READ,),
}


def current_scopes() -> list[str]:
    """Return the scope list carried by the request's verified token.

    Accepts both the list form penguin-aaa issues and the space-delimited
    string form RFC 6749 defines, so a token minted by a different issuer in
    the same trust domain is not silently read as having no scopes at all —
    which would fail *open* for any check written as "deny only if a
    forbidden scope is present" and fail confusingly for every other.
    """
    claims: dict[str, Any] = g.get("current_claims", None) or {}
    raw = claims.get("scope", [])
    if isinstance(raw, str):
        return raw.split()
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    return []


async def has_tenant_scope(user_id: int, tenant_id: int, *required: str) -> bool:
    """True when the user holds every required scope *in a given tenant*.

    Resolves the tenant's scope bundle through the issue-time function, so
    delegated admins (authority inherited from an ancestor) are answered the
    same way here as they would be at token issuance.
    """
    granted = await resolve_scopes(user_id, tenant_id)
    return RBACEnforcer(list(required)).enforce(granted)


def _forbidden(required: tuple[str, ...]) -> tuple[dict[str, Any], int]:
    """Build the 403 body for a failed scope check.

    Names the scope that was required but not the scopes the caller holds:
    echoing the granted set back turns any endpoint into an oracle for
    enumerating a token's authority.
    """
    return (
        {
            "error": "insufficient_scope",
            "required_scope": list(required),
        },
        403,
    )


async def require_tenant_scope(
    user_id: int, tenant_id: int, *required: str
) -> tuple[dict[str, Any], int] | None:
    """In-body scope gate for a specific tenant.

    Returns None when the caller is authorized, or the ``(body, status)``
    tuple the view should return when they are not::

        denied = await require_tenant_scope(user["id"], conn["tenant_id"],
                                            SCOPE_PRODUCTS_MANAGE)
        if denied:
            return denied

    Used where the tenant is only knowable after a database read, which a
    decorator cannot do without duplicating the query.
    """
    if await has_tenant_scope(user_id, tenant_id, *required):
        return None
    return _forbidden(required)


async def team_scopes(user_id: int, team_id: int) -> list[str]:
    """Expand a user's role in a team into its scope bundle.

    Non-members get an empty list, which fails every gate below. Team
    membership is deliberately *not* delegated through the tenant
    hierarchy — a tenant admin is not automatically an admin of every team
    inside it, and granting that here would silently widen team authority.
    """
    from .models import get_user_team_role

    role = await get_user_team_role(user_id, team_id)
    if not role:
        return []
    return sorted(_TEAM_ROLE_SCOPES.get(role, ()))


async def require_team_scope(
    user_id: int, team_id: int, *required: str
) -> tuple[dict[str, Any], int] | None:
    """In-body scope gate for a team, mirroring :func:`require_tenant_scope`.

    Returns None when authorized, or the ``(body, status)`` tuple to return.
    """
    granted = await team_scopes(user_id, team_id)
    if RBACEnforcer(list(required)).enforce(granted):
        return None
    return _forbidden(required)


def _coerce_tenant_id(raw: Any) -> int | None:
    """Narrow a view kwarg to an int tenant id, or None when unusable.

    Route kwargs arrive typed as ``object`` under ParamSpec. ``bool`` is
    rejected explicitly because it is an ``int`` subclass, and ``True`` would
    otherwise resolve to tenant 1.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def require_scope(
    *required: str,
    tenant_arg: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Any]]]:
    """Build a decorator enforcing scopes on a view.

    Args:
        required: Scopes the caller must hold. ALL are required (AND).
        tenant_arg: Name of the view kwarg naming the tenant this request
            acts on. When given, scopes are resolved for *that* tenant.
            When omitted, the token's own issue-time scope list is used,
            which is the caller's authority in their active tenant.

    Must sit below ``@auth_required`` in the decorator stack, which is what
    verifies the token and populates ``g.current_claims``. If it is applied
    to an unauthenticated route it denies rather than reading an absent
    claim as an empty (and therefore trivially unsatisfiable) scope set.
    """
    enforcer = RBACEnforcer(list(required))

    def decorator(f: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[Any]]:
        @wraps(f)
        async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
            if g.get("current_claims", None) is None:
                return {"error": "Authentication required"}, 401

            if tenant_arg is None:
                if not enforcer.enforce(current_scopes()):
                    return _forbidden(required)
                return await f(*args, **kwargs)

            user = get_current_user()
            if not user:
                return {"error": "Authentication required"}, 401

            tenant_id = _coerce_tenant_id(kwargs.get(tenant_arg))
            if tenant_id is None:
                return {"error": f"{tenant_arg} required"}, 400

            if not await has_tenant_scope(user["id"], tenant_id, *required):
                return _forbidden(required)
            return await f(*args, **kwargs)

        # Surfaced for the OpenAPI exporter and for tests that assert a route
        # is gated at all, rather than asserting on a 403 that a bug in the
        # view body could also produce.
        decorated.__required_scopes__ = list(required)  # type: ignore[attr-defined]
        decorated.__scope_tenant_arg__ = tenant_arg  # type: ignore[attr-defined]
        return decorated

    return decorator
