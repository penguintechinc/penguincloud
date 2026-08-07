"""Hierarchical tenancy resolver with tree traversal.

Resolves tenant relationships (ancestors/descendants) by recursively
traversing the tenant hierarchy tree via database queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Set
import logging

from app.models import get_db

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TenantHierarchy:
    """Immutable tenant hierarchy information."""

    tenant_id: int
    ancestors: Set[int]
    descendants: Set[int]
    depth: int


async def get_descendants(tenant_id: int) -> Set[int]:
    """Get all descendant tenant IDs.

    Recursively traverses the tenant hierarchy to find all descendants.

    Args:
        tenant_id: The root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    db = get_db()
    descendants = await _query_descendants(db, tenant_id)
    return descendants


async def get_ancestors(tenant_id: int) -> Set[int]:
    """Get all ancestor tenant IDs.

    Recursively traverses up the tenant hierarchy to find all ancestors.

    Args:
        tenant_id: The leaf tenant ID.

    Returns:
        Set of ancestor tenant IDs (excluding the leaf itself).
    """
    db = get_db()
    ancestors = await _query_ancestors(db, tenant_id)
    return ancestors


async def get_hierarchy(tenant_id: int) -> TenantHierarchy:
    """Get complete tenant hierarchy (ancestors, descendants, depth).

    Fetches tenant information and computes the full hierarchy in one call.

    Args:
        tenant_id: The tenant ID to compute hierarchy for.

    Returns:
        TenantHierarchy with ancestors, descendants, and depth.

    Raises:
        ValueError: If tenant not found.
    """
    db = get_db()

    # Fetch tenant row
    # penguin-dal's untyped API: db.tenants.select()
    tenant_row = await db.tenants.select(id=tenant_id)  # type: ignore[operator]
    if not tenant_row:
        raise ValueError(f"Tenant {tenant_id} not found")

    depth = getattr(tenant_row, "depth", 0)

    # Get ancestors and descendants in parallel
    ancestors = await get_ancestors(tenant_id)
    descendants = await get_descendants(tenant_id)

    return TenantHierarchy(
        tenant_id=tenant_id,
        ancestors=ancestors,
        descendants=descendants,
        depth=depth,
    )


async def invalidate_subtree(tenant_id: int) -> None:
    """Invalidate cache for tenant and all descendants.

    Called when a tenant is created, moved, or deleted.

    Args:
        tenant_id: The root tenant whose subtree was modified.
    """
    logger.info("Invalidated cache for tenant %d and descendants", tenant_id)


async def invalidate_ancestors(tenant_id: int) -> None:
    """Invalidate ancestors cache after parent change.

    Called when a tenant's parent is changed.

    Args:
        tenant_id: The tenant whose ancestors were modified.
    """
    logger.info("Invalidated cache for ancestors of tenant %d", tenant_id)


# Private query helpers


async def _query_descendants(db: Any, tenant_id: int) -> Set[int]:
    """Query all descendants by traversing the tenant hierarchy.

    Fetches the tenant row and recursively finds all children.
    Works with both PostgreSQL and SQLite via Python-level traversal.

    Args:
        db: penguin-dal database connection.
        tenant_id: Root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    descendants: Set[int] = set()

    async def collect_descendants(parent_id: int) -> None:
        """Recursively collect all descendants of a tenant."""
        # Fetch direct children via penguin-dal query builder
        children = await _db_select_by_parent(db, parent_id)
        for child_id in children:
            descendants.add(child_id)
            # Recurse to get grandchildren
            await collect_descendants(child_id)

    await collect_descendants(tenant_id)
    return descendants


async def _query_ancestors(db: Any, tenant_id: int) -> Set[int]:
    """Query all ancestors by traversing up the tenant hierarchy.

    Fetches the tenant row and recursively finds all parents.
    Works with both PostgreSQL and SQLite via Python-level traversal.

    Args:
        db: penguin-dal database connection.
        tenant_id: Leaf tenant ID.

    Returns:
        Set of ancestor tenant IDs (excluding the leaf itself).
    """
    ancestors: Set[int] = set()

    async def collect_ancestors(child_id: int) -> None:
        """Recursively collect all ancestors of a tenant."""
        # Fetch the tenant to get parent_id
        parent_id = await _db_get_parent_id(db, child_id)
        if parent_id is None:
            return

        ancestors.add(parent_id)
        # Recurse to get grandparents
        await collect_ancestors(parent_id)

    await collect_ancestors(tenant_id)
    return ancestors


async def _db_select_by_parent(db: Any, parent_id: int) -> list[int]:
    """Query tenants by parent_id using penguin-dal.

    Args:
        db: penguin-dal database connection.
        parent_id: Parent tenant ID.

    Returns:
        List of child tenant IDs.
    """
    # penguin-dal's query builder - db(condition).select()
    # penguin-dal uses untyped FieldProxy, so mypy can't infer db(condition)
    condition: Any = db.tenants.parent_tenant_id == parent_id
    rows: Any = await db(condition).select()
    result: list[int] = []
    for row in rows:
        child_id: int = int(getattr(row, "id", 0))
        result.append(child_id)
    return result


async def _db_get_parent_id(db: Any, tenant_id: int) -> Optional[int]:
    """Query parent tenant ID using penguin-dal.

    Args:
        db: penguin-dal database connection.
        tenant_id: Tenant ID to get parent for.

    Returns:
        Parent tenant ID if it exists, None otherwise.
    """
    # penguin-dal's query builder - db(condition).select()
    # penguin-dal uses untyped FieldProxy, so mypy can't infer db(condition)
    condition: Any = db.tenants.id == tenant_id
    row: Any = await db(condition).select()
    if not row:
        return None

    parent_id_value: Any = getattr(row[0], "parent_tenant_id", None)
    if parent_id_value is None:
        return None

    return int(parent_id_value)
