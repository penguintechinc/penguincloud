"""Structural mutation of the tenant tree: parenting, re-parenting, depth.

Everything that changes ``tenants.parent_tenant_id`` goes through here, so
the three invariants that make the hierarchy trustworthy are enforced in one
place rather than per-endpoint:

1. **No cycles.** A tenant may not become a descendant of itself. Checked by
   walking the prospective parent's ancestor chain before the write.
2. **``depth`` tracks the tree.** ``depth = parent.depth + 1`` (0 at a root),
   maintained in the service layer for the whole moved subtree — the schema
   deliberately has no trigger doing it (see task brief).
3. **Caches are invalidated on both sides of a move.** The old ancestor
   chain and the new one both held stale descendant sets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.models import get_db, get_tenant_by_id

from .authz import EFFECTIVE_ADMIN_ROLES, resolve_effective_role
from .resolver import MAX_HIERARCHY_DEPTH, get_ancestors, invalidate_tenant

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ParentValidation:
    """Outcome of validating a proposed parent for a tenant."""

    ok: bool
    error: str = ""
    status: int = 400
    parent_depth: int = -1


async def validate_parent(
    user_id: int, parent_tenant_id: int, child_tenant_id: int | None = None
) -> ParentValidation:
    """Check that a user may parent a tenant under ``parent_tenant_id``.

    Requires the parent to exist, the caller to hold owner/admin in it or in
    one of its ancestors, and (when re-parenting an existing tenant) the move
    not to create a cycle or exceed the depth cap.
    """
    parent = await get_tenant_by_id(parent_tenant_id)
    if not parent:
        return ParentValidation(ok=False, error="Parent tenant not found", status=404)

    # Delegated authority counts: an MSP admin two levels up may parent a new
    # customer under one of their existing customers.
    parent_role = await resolve_effective_role(user_id, parent_tenant_id)
    if parent_role not in EFFECTIVE_ADMIN_ROLES:
        return ParentValidation(
            ok=False,
            error="Admin access required in the parent tenant",
            status=403,
        )

    parent_depth = int(parent.get("depth") or 0)

    if child_tenant_id is not None:
        if child_tenant_id == parent_tenant_id:
            return ParentValidation(ok=False, error="A tenant cannot be its own parent", status=400)
        # Walking UP from the prospective parent is the cycle test: if the
        # child already sits above the parent, the parent's ancestor chain
        # contains it, and re-parenting would close the loop.
        if child_tenant_id in await get_ancestors(parent_tenant_id):
            return ParentValidation(
                ok=False,
                error="Re-parenting would create a cycle in the tenant tree",
                status=400,
            )

    if parent_depth + 1 >= MAX_HIERARCHY_DEPTH:
        return ParentValidation(
            ok=False,
            error=f"Tenant tree depth limit ({MAX_HIERARCHY_DEPTH}) reached",
            status=400,
        )

    return ParentValidation(ok=True, parent_depth=parent_depth)


async def validate_origin_authority(user_id: int, tenant: dict[str, Any]) -> ParentValidation:
    """Check that a user may detach a tenant from where it currently sits.

    Validating only the DESTINATION is not enough. Moving a subtree out from
    under a provider — or detaching it to a root with ``parent_tenant_id:
    null``, which has no destination to validate at all — SEVERS that
    provider's authority over everything in the subtree. A mid-tier admin
    holding admin only on the node being moved could otherwise cut the
    provider out of their own customer tree.

    So the origin side requires the same authority the destination side
    does: owner/admin in the current parent, or in one of its ancestors.
    This is the same reasoning that keeps tenant deletion owner-only —
    delegated authority confers management, not the power to dismantle
    somebody else's tree.

    A tenant that is already a root has no origin authority to check: there
    is no parent whose authority could be severed.
    """
    current_parent_raw = tenant.get("parent_tenant_id")
    if current_parent_raw is None:
        return ParentValidation(ok=True)

    current_parent_id = int(current_parent_raw)
    origin_role = await resolve_effective_role(user_id, current_parent_id)
    if origin_role not in EFFECTIVE_ADMIN_ROLES:
        return ParentValidation(
            ok=False,
            error="Admin access required in the current parent tenant",
            status=403,
        )

    return ParentValidation(ok=True)


async def _child_ids(tenant_id: int) -> list[int]:
    """Direct children of a tenant, by id."""
    db = get_db()
    rows: Any = await db(db.tenants.parent_tenant_id == tenant_id).select()
    return [int(row.id) for row in rows]


async def recompute_subtree_depth(root_id: int, root_depth: int) -> int:
    """Rewrite ``depth`` for a tenant and everything beneath it.

    Breadth-first from the root, bounded by MAX_HIERARCHY_DEPTH so a cycle
    that somehow survived validation terminates instead of looping forever.

    Returns:
        Number of tenant rows whose depth was written.
    """
    db = get_db()
    await db(db.tenants.id == root_id).update(depth=root_depth)
    written = 1

    frontier = [(root_id, root_depth)]
    while frontier:
        next_frontier: list[tuple[int, int]] = []
        for parent_id, parent_depth in frontier:
            child_depth = parent_depth + 1
            if child_depth >= MAX_HIERARCHY_DEPTH:
                logger.warning(
                    "depth_cap_reached_during_recompute root_id=%d at_depth=%d",
                    root_id,
                    child_depth,
                )
                continue
            for child_id in await _child_ids(parent_id):
                await db(db.tenants.id == child_id).update(depth=child_depth)
                written += 1
                next_frontier.append((child_id, child_depth))
        frontier = next_frontier

    return written


async def set_parent(tenant_id: int, parent_tenant_id: int | None) -> None:
    """Attach a tenant to a parent (or detach it to a root) and fix depths.

    Invalidates caches twice by design: once before the write so the OLD
    ancestor chain's memoised descendant sets are dropped while they are
    still reachable, once after so the NEW chain's are. Doing it only
    afterwards leaves the previous parent serving a subtree set that still
    contains the departed child.
    """
    await invalidate_tenant(tenant_id)

    db = get_db()
    await db(db.tenants.id == tenant_id).update(parent_tenant_id=parent_tenant_id)

    new_depth = 0
    if parent_tenant_id is not None:
        parent = await get_tenant_by_id(parent_tenant_id)
        new_depth = int((parent or {}).get("depth") or 0) + 1

    await recompute_subtree_depth(tenant_id, new_depth)

    await invalidate_tenant(tenant_id)
    logger.info(
        "tenant_reparented tenant_id=%d parent_tenant_id=%s depth=%d",
        tenant_id,
        parent_tenant_id,
        new_depth,
    )
