"""Gough payload -> portal DTO mapping.

Every field name here was read off Gough's live api-manager handlers rather
than its ``docs/api/openapi-spec.yaml``, which is stale: the committed spec
still describes ``/servers``, ``/servers/{id}/power/{action}`` and ``/stats``,
none of which the service registers today. Nodes, biomes, agents and
deployments are what actually exist.

Two traps this module exists to contain:

* **Gough nodes have no ``status``.** They have ``state`` (the lifecycle) and
  ``posture`` (compliance). Mapping ``status`` would silently yield ``None``
  on every row and produce a dashboard whose status column is always empty.
* **Gough's ``total`` is not a total.** ``GET /api/v1/nodes`` returns
  ``{"nodes": [...], "total": len(page)}`` — the length of the page it just
  serialised, not the collection size. Forwarding it as
  :attr:`~app.adapters.base.Page.total` would report "12 nodes" on every page
  of a 400-node fleet, so it is deliberately dropped and pagination is
  reported through the cursor instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from ..base import (
    Operation,
    OperationLogLine,
    OperationState,
    Resource,
)

__all__ = [
    "parse_timestamp",
    "map_node",
    "map_biome",
    "map_biome_group",
    "map_agent",
    "map_cluster",
    "map_deployment",
    "map_upgrade_run",
    "upgrade_operation_id",
    "split_upgrade_operation_id",
    "map_log_line",
    "OP_DEPLOYMENT",
    "OP_BIOME_UPGRADE",
    "OPERATION_KINDS",
]

#: Operation families. ``kind`` selects the poll route, so these strings are
#: part of the portal's URL surface and are matched against this literal set
#: before use — never interpolated from caller input.
OP_DEPLOYMENT: Final[str] = "deployment"
OP_BIOME_UPGRADE: Final[str] = "biome_upgrade"
OPERATION_KINDS: Final[frozenset[str]] = frozenset({OP_DEPLOYMENT, OP_BIOME_UPGRADE})

#: Gough deployment/upgrade status -> portal control-flow state. Gough spells
#: a running deployment ``in_progress`` and a finished one ``succeeded``;
#: upgrade runs add ``rolling_back``. Anything unrecognised maps to RUNNING
#: rather than a terminal state — see :func:`_state_from_status`.
_STATE_BY_STATUS: Final[dict[str, OperationState]] = {
    "pending": OperationState.PENDING,
    "queued": OperationState.PENDING,
    "in_progress": OperationState.RUNNING,
    "running": OperationState.RUNNING,
    "rolling_back": OperationState.RUNNING,
    "succeeded": OperationState.SUCCEEDED,
    "success": OperationState.SUCCEEDED,
    "completed": OperationState.SUCCEEDED,
    "failed": OperationState.FAILED,
    "rolled_back": OperationState.FAILED,
    "error": OperationState.FAILED,
    "cancelled": OperationState.CANCELLED,
    "canceled": OperationState.CANCELLED,
}


def _state_from_status(status: str) -> OperationState:
    """Map a Gough status string onto a portal state.

    An unknown status resolves to RUNNING, never to a terminal state. The two
    failure modes are not symmetric: treating a live operation as finished
    stops the poll loop and freezes the UI on a stale frame that never
    corrects itself, whereas treating a finished one as live costs a few
    redundant polls and resolves as soon as Gough reports a status we know.
    """
    return _STATE_BY_STATUS.get(status.strip().lower(), OperationState.RUNNING)


def parse_timestamp(value: Any) -> datetime | None:
    """Parse one of Gough's ISO-8601 timestamps.

    Gough serialises with ``datetime.isoformat()`` from a mix of
    ``utcnow()`` (naive) and ``now(timezone.utc)`` (aware) call sites, so both
    forms genuinely arrive. A naive value is assumed UTC and made aware,
    because :class:`~app.adapters.base.Resource` promises timezone-aware
    timestamps and mixing the two makes any comparison raise.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        from datetime import timezone

        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _identifier(payload: dict[str, Any], *names: str) -> str:
    """First present identifier, as a string.

    Gough returns integer ids for nodes and biomes and string ids (UUIDs) for
    deployments and agents; the portal addresses everything by string, so
    normalising here keeps the ``int``/``str`` split out of every call site.
    """
    for name in names:
        value = payload.get(name)
        if value is not None and value != "":
            return str(value)
    return ""


def map_node(payload: dict[str, Any]) -> Resource:
    """Map a Gough node.

    ``state`` becomes the portal's ``status`` because it is the lifecycle
    field — the thing an operator scans a node list for. ``posture`` is kept
    in metadata rather than merged in: they answer different questions
    ("where is it in provisioning" vs "is it compliant"), and a node can be
    ``ready`` while non-compliant.

    ``firmware_type`` is ALWAYS ``None``, and that is a property of Gough, not
    of a given node. ``_serialize_node`` emits the key through its tolerant
    ``_g(node, "firmware_type")`` getter, but no ``firmware_type`` column
    exists on ``nodes`` and no Gough model declares one — verified against a
    live database (``information_schema.columns`` returns no such column in
    any table). The same is true of ``ipv4_static``, which is why it is not
    mapped at all. The key is kept here so the mapping starts working by
    itself if Gough ever adds the column; it is documented so nobody spends
    an afternoon asking why the UI's "Firmware" row is permanently blank.
    """
    return Resource(
        id=_identifier(payload, "id"),
        kind="nodes",
        name=str(payload.get("name") or _identifier(payload, "id")),
        status=payload.get("state"),
        created_at=parse_timestamp(payload.get("created_at")),
        updated_at=parse_timestamp(payload.get("updated_at")),
        metadata={
            "posture": payload.get("posture"),
            "tenant_id": payload.get("tenant_id"),
            "ipv4": payload.get("ipv4"),
            "ipv6": payload.get("ipv6"),
            "primary_nic_mac": payload.get("primary_nic_mac"),
            "firmware_type": payload.get("firmware_type"),
            "attestation_method": payload.get("attestation_method"),
            "hardware_tags": payload.get("hardware_tags") or [],
            "discovered_at": payload.get("discovered_at"),
            "deployed_at": payload.get("deployed_at"),
        },
    )


def map_biome(payload: dict[str, Any]) -> Resource:
    """Map a Gough biome (a deployable workload definition).

    Biomes carry no lifecycle status; ``is_active`` is the closest thing and
    is rendered as ``active``/``inactive`` so the column means something. The
    alternative — leaving status ``None`` — makes every biome look stateless
    in a table shared with nodes.
    """
    active = payload.get("is_active")
    return Resource(
        id=_identifier(payload, "id"),
        kind="biomes",
        name=str(payload.get("name") or _identifier(payload, "id")),
        status=None if active is None else ("active" if active else "inactive"),
        created_at=parse_timestamp(payload.get("created_at")),
        updated_at=parse_timestamp(payload.get("updated_at")),
        metadata={
            "biome_type": payload.get("biome_type"),
            "biome_kind": payload.get("biome_kind"),
            "phase": payload.get("phase"),
            "category": payload.get("category"),
            "version": payload.get("version"),
            "workload_type": payload.get("workload_type"),
            "is_default": payload.get("is_default"),
            "lock_to_host": payload.get("lock_to_host"),
            "requires_hardware_tags": payload.get("requires_hardware_tags") or [],
            "forbids_hardware_tags": payload.get("forbids_hardware_tags") or [],
            "signing_key_id": payload.get("signing_key_id"),
        },
    )


def map_biome_group(payload: dict[str, Any]) -> Resource:
    """Map a Gough biome group — an ordered bundle of biomes.

    **Membership lives under ``biomes``, not ``biome_ids``.** This mapper read
    ``biome_ids``, a field Gough does not emit anywhere in a group response —
    the column is ``biome_groups.biomes`` and ``serialize_biome_group``
    forwards it under that name. The old key therefore resolved to ``None`` on
    every group ever returned and the ``or []`` turned it into an empty list,
    so a group's membership silently rendered as "no biomes" no matter how
    many it contained. Nothing failed; the data just was not there.

    The shape was wrong too, not only the name. ``biomes`` is a JSON array of
    ``{"biome_id": int, "order": int}`` objects (the ``POST /biomes/groups``
    handler validates exactly that), so even reading the right key as a flat
    list of ids would have produced dicts where ids were expected.

    Both are exposed: ``biomes`` verbatim, because the order and the per-entry
    ``order`` field are the group's actual content, and ``biome_ids`` as the
    flat projection callers already expect. The projection preserves Gough's
    stored order rather than sorting on ``order`` — re-sorting here would make
    the portal disagree with the sequence Gough itself returns, and the
    adapter is not the place to decide that question.
    """
    raw_members = payload.get("biomes")
    members = (
        [entry for entry in raw_members if isinstance(entry, dict)]
        if isinstance(raw_members, list)
        else []
    )
    return Resource(
        id=_identifier(payload, "id"),
        kind="biome_groups",
        name=str(payload.get("name") or _identifier(payload, "id")),
        created_at=parse_timestamp(payload.get("created_at")),
        updated_at=parse_timestamp(payload.get("updated_at")),
        metadata={
            "description": payload.get("description"),
            "display_name": payload.get("display_name"),
            "is_default": payload.get("is_default"),
            "biomes": members,
            "biome_ids": [
                entry["biome_id"]
                for entry in members
                if entry.get("biome_id") is not None
            ],
        },
    )


def map_agent(payload: dict[str, Any]) -> Resource:
    """Map a Gough access agent.

    Addressed by ``agent_id`` (the UUID Gough's detail and suspend/resume
    routes take), not the numeric row ``id``. Using the row id would build a
    list whose every link 404s.
    """
    return Resource(
        id=_identifier(payload, "agent_id", "id"),
        kind="agents",
        name=str(payload.get("hostname") or _identifier(payload, "agent_id", "id")),
        status=payload.get("status"),
        created_at=parse_timestamp(payload.get("enrolled_at")),
        updated_at=parse_timestamp(payload.get("last_heartbeat")),
        metadata={
            "row_id": payload.get("id"),
            "ip_address": payload.get("ip_address"),
            "capabilities": payload.get("capabilities"),
            "last_heartbeat": payload.get("last_heartbeat"),
            "enrolled_at": payload.get("enrolled_at"),
            "enrollment_completed": payload.get("enrollment_completed"),
        },
    )


def map_cluster(cluster_id: str, payload: dict[str, Any]) -> Resource:
    """Map a Gough LXD cluster health document.

    Built from ``/clusters/{id}/lxd/status`` because Gough has no cluster
    object endpoint — see :meth:`GoughAdapter.list_resources`. ``cluster_id``
    is passed in rather than read from the body so the resource is addressable
    by what the caller asked for even if the body omits it.
    """
    healthy = payload.get("healthy")
    return Resource(
        id=cluster_id,
        kind="clusters",
        name=str(payload.get("cluster_id") or cluster_id),
        status=None if healthy is None else ("healthy" if healthy else "degraded"),
        metadata={
            "quorum_status": payload.get("quorum_status"),
            "member_count": payload.get("member_count"),
            "members_online": payload.get("members_online"),
            "members_offline": payload.get("members_offline"),
        },
    )


def map_deployment(payload: dict[str, Any]) -> Operation:
    """Map a Gough deployment (a biome landing on a node).

    ``progress`` stays ``None``. Gough reports an integer ``phase`` with no
    declared maximum, so any fraction derived from it would be invented — and
    :class:`~app.adapters.base.Operation` forbids synthesising one.
    """
    status = str(payload.get("status") or "")
    state = _state_from_status(status)
    updated = parse_timestamp(payload.get("updated_at"))
    return Operation(
        id=_identifier(payload, "id"),
        kind=OP_DEPLOYMENT,
        state=state,
        status=status,
        resource_id=_identifier(payload, "node_id") or None,
        resource_kind="nodes",
        progress=None,
        detail=(
            f"phase {payload['phase']}" if payload.get("phase") is not None else None
        ),
        created_at=parse_timestamp(payload.get("created_at")),
        updated_at=updated,
        completed_at=updated if state.is_terminal else None,
        metadata={
            "biome_id": payload.get("biome_id"),
            "node_id": payload.get("node_id"),
            "phase": payload.get("phase"),
            "logs_url": payload.get("logs_url"),
        },
    )


def upgrade_operation_id(biome_id: Any, run_id: Any) -> str:
    """Build the self-contained poll key for an upgrade run.

    Gough nests upgrade runs under their biome
    (``/biomes/{biome_id}/upgrade-runs/{run_id}``), so a bare run id is not
    enough to poll one. :class:`~app.adapters.base.Operation` promises that
    ``get_operation(op.kind, op.id, ctx)`` refreshes the object without the
    caller retaining outside knowledge — so the parent id is folded into the
    id itself rather than left for the caller to remember and re-supply.

    The separator is ``:`` because it cannot appear in either component:
    both are Gough integers/UUIDs, and the adapter's id validation rejects
    anything else before it reaches a URL.
    """
    return f"{biome_id}:{run_id}"


def split_upgrade_operation_id(operation_id: str) -> tuple[str, str]:
    """Split a composite upgrade-run id back into (biome_id, run_id).

    Raises ValueError for a malformed id so the caller answers 404 rather
    than building a URL with an empty path segment.
    """
    biome_id, separator, run_id = operation_id.partition(":")
    if not separator or not biome_id or not run_id:
        raise ValueError(f"upgrade run id {operation_id!r} must be 'biome_id:run_id'")
    return biome_id, run_id


def map_upgrade_run(payload: dict[str, Any]) -> Operation:
    """Map a Gough biome upgrade run.

    Unlike a deployment this one *can* report progress: Gough publishes
    ``nodes_completed`` and ``nodes_total``. Failed nodes count as completed
    work for the bar's purposes — the run has finished with them either way,
    and excluding them makes a run that failed on every node sit at 0% while
    it is demonstrably over.
    """
    status = str(payload.get("status") or "")
    state = _state_from_status(status)
    total = payload.get("nodes_total")
    completed = payload.get("nodes_completed") or 0
    failed = payload.get("nodes_failed") or 0

    progress: float | None = None
    if isinstance(total, int) and total > 0:
        done = float(completed) + float(failed)
        progress = max(0.0, min(1.0, done / float(total)))

    return Operation(
        id=upgrade_operation_id(
            _identifier(payload, "biome_id"), _identifier(payload, "id")
        ),
        kind=OP_BIOME_UPGRADE,
        state=state,
        status=status,
        resource_id=_identifier(payload, "biome_id") or None,
        resource_kind="biomes",
        progress=progress,
        detail=str(payload["phase"]) if payload.get("phase") is not None else None,
        error=payload.get("rollback_reason"),
        created_at=parse_timestamp(payload.get("started_at")),
        updated_at=parse_timestamp(payload.get("started_at")),
        completed_at=parse_timestamp(payload.get("completed_at")),
        metadata={
            "biome_id": payload.get("biome_id"),
            "cluster_id": payload.get("cluster_id"),
            "target_version": payload.get("target_version"),
            "nodes_total": total,
            "nodes_completed": completed,
            "nodes_failed": failed,
            "rollback_reason": payload.get("rollback_reason"),
        },
    )


def map_log_line(payload: dict[str, Any]) -> OperationLogLine:
    """Map one Gough deployment log row."""
    return OperationLogLine(
        message=str(payload.get("message") or ""),
        timestamp=parse_timestamp(payload.get("created_at")),
        level=str(payload.get("level") or "info"),
    )
