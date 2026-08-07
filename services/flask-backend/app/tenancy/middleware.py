"""Hierarchical tenancy middleware for Quart.

Wraps penguin-aaa auth flow to attach tenant context (hierarchy, ancestors,
descendants) to the request. Runs after JWT validation (auth_required) and
before scope/role checks.

The middleware loads the tenant row and attaches a TenancyContext to g,
containing the active tenant's full hierarchy information.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, ParamSpec, TypeVar

from quart import g

from .resolver import get_hierarchy, TenantHierarchy

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
    """Attach tenancy context to request after auth validation.

    Expects auth_required to have already run (verified JWT, set g.current_claims).
    Loads tenant row and hierarchy, attaches TenancyContext to g.

    Returns 403 if:
    - No tenant claim in the token
    - Tenant not found in the database

    Usage:
        @app.route("/api/v1/protected")
        @auth_required
        @tenancy_aware
        async def protected_route():
            context = g.tenancy_context
            print(context.tenant_id, context.hierarchy.descendants)
    """

    @wraps(f)
    async def decorated(*args: P.args, **kwargs: P.kwargs) -> Any:
        # Get tenant from already-validated JWT claims
        claims: Optional[dict[str, Any]] = g.get("current_claims", None)
        if not claims:
            return {"error": "Authentication required"}, 401

        tenant_id_claim = claims.get("tenant")
        if not tenant_id_claim:
            return {"error": "No active tenant in token"}, 403

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


def get_tenancy_context() -> Optional[TenancyContext]:
    """Get the tenancy context from the current request.

    Returns None if tenancy_aware was not applied to the route.
    """
    context: Optional[TenancyContext] = g.get("tenancy_context", None)
    return context
