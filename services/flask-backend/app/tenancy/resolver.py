"""Hierarchical tenancy resolver with CTE-based tree traversal.

Resolves tenant relationships (ancestors/descendants) with a single
``WITH RECURSIVE`` CTE per direction, executed through penguin-dal's
``AsyncDB.executesql`` raw-SQL escape hatch.

Caching is IN-PROCESS ONLY, and deliberately so
--------------------------------------------------
Subtree sets are memoised in a per-process dict with a short TTL
(``LOCAL_CACHE_TTL_SECONDS``). There is no Redis/Valkey tier here.

Consequences the operator must know about:

* **Single-worker assumption for freshness.** Each hypercorn worker keeps
  its own copy, and :func:`invalidate_subtree` only clears the copy in the
  worker that handled the mutating request. With more than one worker, a
  sibling worker can serve a stale subtree set for up to the TTL. The TTL
  is therefore the real correctness bound, not the invalidation calls.
* **The TTL is the backstop, invalidation is the optimisation.** Every
  mutation path calls :func:`invalidate_tenant`; the TTL exists so a missed
  call site (or a cross-worker mutation) self-heals within a minute rather
  than persisting for the process lifetime.
* Authorisation never reads a cached *decision* — only the set of tenant
  IDs in a subtree. A stale set can at worst widen or narrow a delegated
  admin's view for one TTL window; it can never grant a role the caller
  does not hold, because roles are always re-read from ``tenant_members``.

Moving to a shared tier is a drop-in change: penguin-dal already ships
``penguin_dal.cache.AsyncValkeyCache`` (Valkey is the org standard —
see devops-containers). It is intentionally NOT wired up here, because a
half-present cache backend that silently no-ops when its client library is
absent is worse than an honest in-process one.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, Set

from app.models import get_db

logger = logging.getLogger(__name__)

#: Hard ceiling on recursion depth for both CTEs. A tenant tree deeper than
#: this is a data defect (most plausibly a parentage cycle that slipped past
#: the create/re-parent validation), and the cap turns it into a bounded,
#: wrong-but-terminating answer instead of an unbounded server-side loop.
#: Paired with ``UNION`` (not ``UNION ALL``) so a cycle also stops producing
#: new rows rather than merely being truncated.
MAX_HIERARCHY_DEPTH = 32

#: Lifetime of a memoised subtree set. Short enough that a missed
#: invalidation or a mutation on a sibling worker self-heals quickly; long
#: enough to absorb the fan-out of a rollup request.
LOCAL_CACHE_TTL_SECONDS = 60.0

#: key -> (expires_at_monotonic, serialised set)
_LOCAL_CACHE: dict[str, tuple[float, frozenset[int]]] = {}


class UnsupportedParamstyleError(RuntimeError):
    """Raised when the bound driver uses a paramstyle we cannot render."""


@dataclass(slots=True, frozen=True)
class TenantHierarchy:
    """Immutable tenant hierarchy information."""

    tenant_id: int
    ancestors: Set[int]
    descendants: Set[int]
    depth: int


@dataclass(slots=True, frozen=True)
class BoundQuery:
    """A SQL string rendered for one driver plus its matching parameters.

    ``params`` is a tuple for positional paramstyles and a dict for named
    ones, matching what ``executesql`` hands straight to the DBAPI.
    """

    sql: str
    params: tuple[Any, ...] | dict[str, Any]


# Parameter binding -- driver-native, not SQLAlchemy-native
#
# penguin-dal's executesql calls SQLAlchemy's exec_driver_sql, which passes
# the SQL string to the DBAPI *verbatim*. The placeholder token is therefore
# the driver's, not ``:name``. Hardcoding "?" works on sqlite+aiosqlite and
# raises on every other backend -- notably postgresql+asyncpg, the async
# driver penguin_dal.backends maps ``postgresql://`` onto, which wants $1.

_POSITIONAL_TOKENS: dict[str, Callable[[int], str]] = {
    "qmark": lambda position: "?",  # sqlite+aiosqlite
    "format": lambda position: "%s",  # mysql+aiomysql, psycopg2
    "numeric": lambda position: f":{position}",
    "numeric_dollar": lambda position: f"${position}",  # postgresql+asyncpg
}

_NAMED_TOKENS: dict[str, Callable[[str], str]] = {
    "pyformat": lambda name: f"%({name})s",  # psycopg2 named
    "named": lambda name: f":{name}",
}

_SLOT_RE = re.compile(r"\{(\w+)\}")


def bind_query(
    template: str, paramstyle: str, values: Mapping[str, Any]
) -> BoundQuery:
    """Render ``{name}`` slots in a SQL template for one driver's paramstyle.

    Positional styles bind in order of first appearance in the template, so
    the returned tuple's order is the SQL's order rather than the mapping's.

    Raises:
        UnsupportedParamstyleError: If the driver's paramstyle is unknown.
        KeyError: If the template references a slot absent from ``values``.
    """
    if paramstyle in _NAMED_TOKENS:
        named_token = _NAMED_TOKENS[paramstyle]
        sql = _SLOT_RE.sub(lambda m: named_token(m.group(1)), template)
        return BoundQuery(sql=sql, params=dict(values))

    positional_token = _POSITIONAL_TOKENS.get(paramstyle)
    if positional_token is None:
        raise UnsupportedParamstyleError(
            f"No placeholder rendering for DBAPI paramstyle {paramstyle!r}"
        )

    ordered: list[Any] = []

    def _substitute(match: re.Match[str]) -> str:
        ordered.append(values[match.group(1)])
        return positional_token(len(ordered))

    sql = _SLOT_RE.sub(_substitute, template)
    return BoundQuery(sql=sql, params=tuple(ordered))


def get_paramstyle(db: Any) -> str:
    """Read the DBAPI paramstyle off penguin-dal's engine.

    ``AsyncDB.engine`` is a public property exposing the SQLAlchemy async
    engine, whose dialect reports the paramstyle of the driver actually in
    use: ``qmark`` for sqlite+aiosqlite, ``numeric_dollar`` for
    postgresql+asyncpg, ``format`` for mysql+aiomysql.
    """
    paramstyle: str = db.engine.dialect.paramstyle
    return paramstyle


# Recursive CTE templates
#
# UNION (not UNION ALL): a parentage cycle otherwise re-emits the same rows
# forever. The level column plus MAX_HIERARCHY_DEPTH is the second guard --
# with a level in the row, UNION alone would not dedupe a cycle away.

DESCENDANTS_TEMPLATE = """
WITH RECURSIVE tenant_tree(tenant_id, level) AS (
    SELECT id, 1
    FROM tenants
    WHERE parent_tenant_id = {root_id}
    UNION
    SELECT t.id, tt.level + 1
    FROM tenants t
    INNER JOIN tenant_tree tt ON t.parent_tenant_id = tt.tenant_id
    WHERE tt.level < {max_depth}
)
SELECT tenant_id FROM tenant_tree
""".strip()

ANCESTORS_TEMPLATE = """
WITH RECURSIVE tenant_tree(tenant_id, parent_id, level) AS (
    SELECT id, parent_tenant_id, 1
    FROM tenants
    WHERE id = {leaf_id}
    UNION
    SELECT t.id, t.parent_tenant_id, tt.level + 1
    FROM tenants t
    INNER JOIN tenant_tree tt ON t.id = tt.parent_id
    WHERE tt.level < {max_depth}
)
SELECT parent_id FROM tenant_tree WHERE parent_id IS NOT NULL
""".strip()


def build_descendants_query(paramstyle: str, tenant_id: int) -> BoundQuery:
    """Build the descendants CTE for a specific driver paramstyle."""
    return bind_query(
        DESCENDANTS_TEMPLATE,
        paramstyle,
        {"root_id": tenant_id, "max_depth": MAX_HIERARCHY_DEPTH},
    )


def build_ancestors_query(paramstyle: str, tenant_id: int) -> BoundQuery:
    """Build the ancestors CTE for a specific driver paramstyle."""
    return bind_query(
        ANCESTORS_TEMPLATE,
        paramstyle,
        {"leaf_id": tenant_id, "max_depth": MAX_HIERARCHY_DEPTH},
    )


async def get_descendants(tenant_id: int) -> Set[int]:
    """Get all descendant tenant IDs via SQL WITH RECURSIVE CTE.

    Memoised per process for LOCAL_CACHE_TTL_SECONDS; see the module
    docstring for the freshness caveats that follow from that.

    Args:
        tenant_id: The root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    cache_key = subtree_cache_key(tenant_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        return set(cached)

    db = get_db()
    descendants = await _query_descendants_cte(db, tenant_id)

    _cache_set(cache_key, descendants)
    return descendants


async def get_ancestors(tenant_id: int) -> Set[int]:
    """Get all ancestor tenant IDs via SQL WITH RECURSIVE CTE.

    Deliberately NOT cached. The ancestor chain is what every delegated-admin
    authorisation decision walks, and it is bounded by MAX_HIERARCHY_DEPTH
    rather than by subtree width, so a single indexed CTE is cheap. Caching
    it would add a second key that must be invalidated on every re-parent to
    avoid a *widening* staleness window on the authorisation path — the one
    direction where a stale answer is dangerous. The subtree cache is
    read-side fan-out only and carries no such risk.

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

    # Fetch tenant row via penguin-dal query builder API
    rows: Any = await db(db.tenants.id == tenant_id).select()
    if not rows:
        raise ValueError(f"Tenant {tenant_id} not found")
    tenant_row = rows[0]

    depth = getattr(tenant_row, "depth", 0) or 0

    # Get ancestors and descendants in parallel
    ancestors, descendants = await asyncio.gather(
        get_ancestors(tenant_id),
        get_descendants(tenant_id),
    )

    return TenantHierarchy(
        tenant_id=tenant_id,
        ancestors=ancestors,
        descendants=descendants,
        depth=int(depth),
    )


# Cache invalidation


def subtree_cache_key(tenant_id: int) -> str:
    """Cache key holding the descendant-ID set rooted at ``tenant_id``."""
    return f"tenancy:subtree:{tenant_id}"


async def invalidate_subtree(tenant_id: int) -> None:
    """Drop cached descendant sets for a tenant and everything beneath it.

    Call after a structural change *inside* a subtree (a child created,
    deleted, or moved), which invalidates the memoised set of every node at
    or below the change.

    Args:
        tenant_id: The root tenant whose subtree was modified.
    """
    _cache_delete(subtree_cache_key(tenant_id))
    try:
        db = get_db()
        for descendant_id in await _query_descendants_cte(db, tenant_id):
            _cache_delete(subtree_cache_key(descendant_id))
    except Exception:  # pragma: no cover - invalidation must never 500 a write
        logger.exception("subtree_invalidation_query_failed tenant_id=%d", tenant_id)
    logger.debug("Invalidated subtree cache at and below tenant %d", tenant_id)


async def invalidate_ancestors(tenant_id: int) -> None:
    """Drop cached descendant sets for every ancestor of a tenant.

    An ancestor's memoised set contains ``tenant_id``; any change to that
    tenant's own parentage or existence makes those sets wrong.

    Args:
        tenant_id: The tenant whose ancestors' caches are now stale.
    """
    try:
        db = get_db()
        for ancestor_id in await _query_ancestors_cte(db, tenant_id):
            _cache_delete(subtree_cache_key(ancestor_id))
    except Exception:  # pragma: no cover - invalidation must never 500 a write
        logger.exception("ancestor_invalidation_query_failed tenant_id=%d", tenant_id)
    logger.debug("Invalidated ancestor caches above tenant %d", tenant_id)


async def invalidate_tenant(tenant_id: int) -> None:
    """Invalidate every cached set a change to ``tenant_id`` can falsify.

    The single entry point mutation paths call. Covers both directions:
    sets rooted at or below the tenant, and sets rooted above it that used
    to contain it.

    A re-parent must call this **twice** — once before the write (clearing
    the old ancestor chain) and once after (clearing the new one) — because
    the ancestor query reads live rows.
    """
    await invalidate_ancestors(tenant_id)
    await invalidate_subtree(tenant_id)


def clear_local_cache() -> None:
    """Empty the in-process cache outright. Test and shutdown hook."""
    _LOCAL_CACHE.clear()


# In-process cache with TTL


def _cache_get(key: str) -> Optional[frozenset[int]]:
    """Return a live cached set, or None when missing or expired."""
    entry = _LOCAL_CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at <= time.monotonic():
        _LOCAL_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Set[int]) -> None:
    """Memoise a set until LOCAL_CACHE_TTL_SECONDS from now."""
    _LOCAL_CACHE[key] = (
        time.monotonic() + LOCAL_CACHE_TTL_SECONDS,
        frozenset(value),
    )


def _cache_delete(key: str) -> None:
    """Forget one key, if present."""
    _LOCAL_CACHE.pop(key, None)


# CTE-based query helpers


async def _execute_ids(db: Any, bound: BoundQuery) -> list[Any]:
    """Run a bound CTE and return its raw single-column rows."""
    rows: Any = await db.executesql(bound.sql, bound.params)
    return list(rows or [])


def _first_column(rows: Sequence[Any]) -> Set[int]:
    """Collect the non-NULL first column of raw cursor rows as ints."""
    return {int(row[0]) for row in rows if row[0] is not None}


async def _query_descendants_cte(db: Any, tenant_id: int) -> Set[int]:
    """Query all descendants via SQL WITH RECURSIVE CTE.

    Placeholders are rendered for the bound driver, so this works on
    sqlite+aiosqlite, postgresql+asyncpg and mysql+aiomysql alike.

    Args:
        db: penguin-dal AsyncDB instance.
        tenant_id: Root tenant ID.

    Returns:
        Set of descendant tenant IDs (excluding the root).
    """
    bound = build_descendants_query(get_paramstyle(db), tenant_id)
    return _first_column(await _execute_ids(db, bound))


async def _query_ancestors_cte(db: Any, tenant_id: int) -> Set[int]:
    """Query all ancestors via SQL WITH RECURSIVE CTE.

    Args:
        db: penguin-dal AsyncDB instance.
        tenant_id: Leaf tenant ID.

    Returns:
        Set of ancestor tenant IDs (excluding the leaf itself).
    """
    bound = build_ancestors_query(get_paramstyle(db), tenant_id)
    return _first_column(await _execute_ids(db, bound))
