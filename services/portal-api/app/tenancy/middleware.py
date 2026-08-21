"""Hierarchical tenancy middleware for Quart.

Wraps penguin-aaa auth flow to attach tenant context (hierarchy, ancestors,
descendants) to the request. Runs after JWT validation (auth_required) and
before scope/role checks.

The middleware loads the tenant row and attaches a TenancyContext to g,
containing the active tenant's full hierarchy information.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from quart import g

from .resolver import TenantHierarchy, get_hierarchy

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(slots=True, frozen=True)
class TenancyContext:
    """Immutable tenancy context attached to the request."""

    tenant_id: int
    tenant_name: str
    tenant_kind: str  # 'provider' or 'customer'
    hierarchy: TenantHierarchy

    def covers(self, candidate_tenant_id: int) -> bool:
        """True when a tenant is the active one or sits beneath it."""
        return (
            candidate_tenant_id == self.tenant_id
            or candidate_tenant_id in self.hierarchy.descendants
        )


async def load_tenancy_context(tenant_id: int) -> TenancyContext:
    """Load tenant row and hierarchy from the database.

    Args:
        tenant_id: The active tenant ID from the JWT claim.

    Returns:
        TenancyContext with hierarchy information.

    Raises:
        ValueError: If tenant not found.
    """
    from app.models import get_db

    db = get_db()

    # Load tenant row via penguin-dal query builder API
    rows: Any = await db(db.tenants.id == tenant_id).select()
    if not rows:
        raise ValueError(f"Tenant {tenant_id} not found")
    tenant_row = rows[0]

    tenant_name = getattr(tenant_row, "name", f"Tenant {tenant_id}")
    tenant_kind = getattr(tenant_row, "kind", "customer")

    # Load hierarchy
    hierarchy = await get_hierarchy(tenant_id)

    return TenancyContext(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_kind=tenant_kind,
        hierarchy=hierarchy,
    )


def tenancy_aware(
    f: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[Any]]:
    """Resolve the active tenant into ``g.tenancy_context`` before the view.

    Sits between ``auth_required`` (which verifies the JWT and populates
    ``g.current_claims``) and the view's own scope/role logic, so tenancy is
    established before any authorization decision is taken — never after.

    Outcomes:

    * **Tenant claim missing or blank → 403, view never runs.** penguin-aaa
      requires a non-empty tenant claim, so this state means a token was
      minted outside the sanctioned path; it is rejected here rather than
      being allowed to reach a route that would then read tenancy off ``g``
      and find nothing.
    * **Claim names a tenant that does not exist → 403, view never runs.**
    * **Claim is the UNSCOPED_TENANT sentinel → context is None, view runs.**
      Login and refresh deliberately issue unscoped tokens; the bootstrap
      routes (create your first tenant, list your tenants, switch into one)
      have no active tenant by definition. Those routes authorize against an
      explicit tenant id instead, so an absent context is a legitimate state
      rather than a bypass.

    Usage:
        @app.route("/api/v1/protected")
        @auth_required
        @tenancy_aware
        async def protected_route():
            context = get_tenancy_context()
            if context is not None:
                print(context.tenant_id, context.hierarchy.descendants)
    """

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        from app.config import UNSCOPED_TENANT

        # Get tenant from already-validated JWT claims
        claims: dict[str, Any] | None = g.get("current_claims", None)
        if not claims:
            return {"error": "Authentication required"}, 401

        tenant_id_claim = claims.get("tenant")
        if not tenant_id_claim:
            return {"error": "No active tenant in token"}, 403

        if tenant_id_claim == UNSCOPED_TENANT:
            g.tenancy_context = None
            return await f(*args, **kwargs)

        # Normalize claim to int
        try:
            tenant_id = int(tenant_id_claim)
        except (ValueError, TypeError):
            logger.warning("Invalid tenant claim type: %s", type(tenant_id_claim))
            return {"error": "Invalid tenant claim"}, 403

        # Load tenant and hierarchy
        try:
            context = await load_tenancy_context(tenant_id)
            g.tenancy_context = context
        except ValueError:
            logger.info("Tenant not found: %d", tenant_id)
            return {"error": "Tenant not found"}, 403
        except Exception:  # pragma: no cover
            logger.exception("Failed to load tenancy context")
            return {"error": "Internal server error"}, 500

        return await f(*args, **kwargs)

    return decorated


def get_tenancy_context() -> TenancyContext | None:
    """Get the tenancy context from the current request.

    Returns None if tenancy_aware was not applied to the route.
    """
    context: TenancyContext | None = g.get("tenancy_context", None)
    return context
