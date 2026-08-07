"""Hierarchical tenancy resolver with CTE-based tree traversal.

Resolves tenant relationships (ancestors/descendants) via SQL
WITH RECURSIVE CTEs through penguin-dal executesql.
Cache via in-process dict or Redis/Valkey when configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Set

from app.models import get_db

logger = logging.getLogger(__name__)

# In-process cache fallback (used in tests or when Redis unavailable)
_LOCAL_CACHE: dict[str, str] = {}


@dataclass(slots=True, frozen=True)
class TenantHierarchy:
    """Immutable tenant hierarchy information."""

    tenant_id: int
    ancestors: Set[int]
    descendants: Set[int]
    depth: int


async def get_descendants(tenant_id: int) -> Set[int]:
    """Get all descendant tenant IDs via SQL WITH RECURSIVE CTE.

    Executes a single recursive query that finds all descendants efficiently.

    Args:
        tenant_id: The root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    cache_key = f"tenancy:subtree:{tenant_id}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return set(json.loads(cached))

    db = get_db()
    descendants = await _query_descendants_cte(db, tenant_id)

    await _cache_set(cache_key, json.dumps(sorted(list(descendants))))
    return descendants


async def get_ancestors(tenant_id: int) -> Set[int]:
    """Get all ancestor tenant IDs via SQL WITH RECURSIVE CTE.

    Executes a single recursive query that finds all ancestors efficiently.

    Args:
        tenant_id: The leaf tenant ID.

    Returns:
        Set of ancestor tenant IDs (excluding the leaf itself).
    """
    db = get_db()
    ancestors = await _query_ancestors_cte(db, tenant_id)
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
    ancestors, descendants = await asyncio.gather(
        get_ancestors(tenant_id),
        get_descendants(tenant_id),
    )

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
    # Invalidate subtree cache
    await _cache_delete(f"tenancy:subtree:{tenant_id}")
    logger.info("Invalidated cache for tenant %d and descendants", tenant_id)


async def invalidate_ancestors(tenant_id: int) -> None:
    """Invalidate ancestors cache after parent change.

    Called when a tenant's parent is changed.

    Args:
        tenant_id: The tenant whose ancestors were modified.
    """
    # Get ancestors and invalidate their subtree caches
    db = get_db()
    ancestors = await _query_ancestors_cte(db, tenant_id)
    for ancestor_id in ancestors:
        await _cache_delete(f"tenancy:subtree:{ancestor_id}")
    logger.info("Invalidated cache for ancestors of tenant %d", tenant_id)


# Cache layer


async def _cache_get(key: str) -> Optional[str]:
    """Get value from cache (Redis/Valkey or local fallback)."""
    try:
        # Try Redis/Valkey if configured
        redis_url = os.environ.get("CACHE_URL")
        if redis_url and _has_redis():
            return await _redis_get(redis_url, key)
    except Exception as e:
        logger.debug("Redis cache get failed: %s", e)

    # Fallback to local cache
    return _LOCAL_CACHE.get(key)


async def _cache_set(key: str, value: str, ttl: int = 3600) -> None:
    """Set value in cache (Redis/Valkey or local fallback)."""
    try:
        # Try Redis/Valkey if configured
        redis_url = os.environ.get("CACHE_URL")
        if redis_url and _has_redis():
            return await _redis_set(redis_url, key, value, ttl)
    except Exception as e:
        logger.debug("Redis cache set failed: %s", e)

    # Fallback to local cache
    _LOCAL_CACHE[key] = value


async def _cache_delete(key: str) -> None:
    """Delete value from cache (Redis/Valkey or local fallback)."""
    try:
        # Try Redis/Valkey if configured
        redis_url = os.environ.get("CACHE_URL")
        if redis_url and _has_redis():
            return await _redis_delete(redis_url, key)
    except Exception as e:
        logger.debug("Redis cache delete failed: %s", e)

    # Fallback to local cache
    _LOCAL_CACHE.pop(key, None)


def _has_redis() -> bool:
    """Check if Redis/Valkey is available."""
    try:
        import redis  # noqa: F401

        return True
    except ImportError:
        return False


async def _redis_get(url: str, key: str) -> Optional[str]:
    """Get from Redis/Valkey."""
    # Simplified Redis client usage - in production, use a connection pool
    import redis

    r = redis.from_url(url)  # type: ignore[no-untyped-call]
    try:
        val = r.get(key)
        return val.decode() if val else None
    finally:
        r.close()


async def _redis_set(url: str, key: str, value: str, ttl: int) -> None:
    """Set in Redis/Valkey."""
    import redis

    r = redis.from_url(url)  # type: ignore[no-untyped-call]
    try:
        r.setex(key, ttl, value)
    finally:
        r.close()


async def _redis_delete(url: str, key: str) -> None:
    """Delete from Redis/Valkey."""
    import redis

    r = redis.from_url(url)  # type: ignore[no-untyped-call]
    try:
        r.delete(key)
    finally:
        r.close()


# CTE-based query helpers


async def _query_descendants_cte(db: Any, tenant_id: int) -> Set[int]:
    """Query all descendants via SQL WITH RECURSIVE CTE.

    Works on PostgreSQL and SQLite.

    Args:
        db: penguin-dal database connection.
        tenant_id: Root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    # WITH RECURSIVE CTE that works on both PostgreSQL and SQLite
    cte_sql = """
        WITH RECURSIVE tenant_tree AS (
            SELECT id FROM tenants WHERE parent_tenant_id = ?
            UNION ALL
            SELECT t.id FROM tenants t
            INNER JOIN tenant_tree tt ON t.parent_tenant_id = tt.id
        )
        SELECT id FROM tenant_tree
    """

    # Execute via penguin-dal executesql
    # Returns list[tuple] by default
    rows: Any = db.executesql(cte_sql, (tenant_id,))
    descendants = {int(row[0]) for row in (rows or [])}
    return descendants


async def _query_ancestors_cte(db: Any, tenant_id: int) -> Set[int]:
    """Query all ancestors via SQL WITH RECURSIVE CTE.

    Works on PostgreSQL and SQLite.

    Args:
        db: penguin-dal database connection.
        tenant_id: Leaf tenant ID.

    Returns:
        Set of ancestor tenant IDs (excluding the leaf itself).
    """
    # WITH RECURSIVE CTE that traverses upward
    cte_sql = """
        WITH RECURSIVE tenant_tree AS (
            SELECT parent_tenant_id FROM tenants
            WHERE id = ? AND parent_tenant_id IS NOT NULL
            UNION ALL
            SELECT t.parent_tenant_id FROM tenants t
            INNER JOIN tenant_tree tt ON t.id = tt.parent_tenant_id
            WHERE t.parent_tenant_id IS NOT NULL
        )
        SELECT parent_tenant_id FROM tenant_tree
        WHERE parent_tenant_id IS NOT NULL
    """

    # Execute via penguin-dal executesql
    rows: Any = db.executesql(cte_sql, (tenant_id,))
    ancestors = {int(row[0]) for row in (rows or []) if row[0] is not None}
    return ancestors
