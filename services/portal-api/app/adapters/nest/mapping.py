"""Nest payload → portal DTO mapping.

Every field the portal renders generically is mapped onto a named
:class:`~app.adapters.base.Resource` field here; genuinely Nest-specific
extras go to ``metadata``. Nothing is invented — where Nest does not report
something, the DTO field stays ``None`` rather than being synthesised.

Identity
========
Nest identifies most resources by ``name``, not by an id. Only a
DataResource carries a separate ``id``, and even there ``name`` is what
every route addresses (``/data-resources/<name>``, not ``/<id>``). So
``Resource.id`` is the NAME for every kind, and a DataResource's UUID is
preserved in ``metadata["nest_id"]``. Using the UUID as ``Resource.id``
would produce rows whose id cannot be fed back into any Nest route — the
portal would render a detail link that 404s.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from ..base import Operation, OperationState, Resource

__all__ = [
    "KIND_DATABASE",
    "KIND_SNAPSHOT",
    "KIND_PROTECTION_POLICY",
    "KIND_SEARCH_POOL",
    "RESOURCE_KINDS",
    "OP_KIND",
    "OPERATION_KINDS",
    "CREATE_FIELD_ALIASES",
    "COLLECTION_ENVELOPE_KEYS",
    "NEST_LIST_HANDLERS",
    "envelope_key",
    "parse_timestamp",
    "to_create_payload",
    "to_resource",
    "to_operation",
]

#: Portal-facing resource kinds. ``database`` is the portal's name for a
#: Nest DataResource — the UI calls the screen Databases, and the contract's
#: ``kind`` is the portal's vocabulary, not the product's.
KIND_DATABASE: Final[str] = "database"
KIND_SNAPSHOT: Final[str] = "snapshot"
KIND_PROTECTION_POLICY: Final[str] = "protection_policy"
KIND_SEARCH_POOL: Final[str] = "search_pool"

RESOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {KIND_DATABASE, KIND_SNAPSHOT, KIND_PROTECTION_POLICY, KIND_SEARCH_POOL}
)

#: Nest has ONE operation family — every long-running action (snapshot,
#: restore, introspect, migrate, and every create) is polled at the same
#: route, ``/tenants/{tid}/operations/{op_id}``. ``Operation.kind`` names the
#: poll route rather than the resource, so a single value is correct here;
#: Nest's own ``type`` field (which action produced it) is carried in
#: ``metadata`` for display.
OP_KIND: Final[str] = "operation"
OPERATION_KINDS: Final[frozenset[str]] = frozenset({OP_KIND})

#: Nest's operation phases (``models.py:14``), lowercased for lookup. Nest
#: has no cancellation phase — it exposes no cancel route at the API service
#: — so ``CANCELLED`` is deliberately absent rather than mapped to something
#: adjacent.
_PHASES: Final[dict[str, OperationState]] = {
    "pending": OperationState.PENDING,
    "running": OperationState.RUNNING,
    "succeeded": OperationState.SUCCEEDED,
    "failed": OperationState.FAILED,
}

#: Per-kind mapping of the payload keys that feed named ``Resource`` fields.
_STATUS_KEYS: Final[dict[str, str]] = {
    KIND_DATABASE: "phase",
    KIND_SEARCH_POOL: "phase",
}

#: Keys already promoted to named DTO fields, excluded from ``metadata`` so
#: the same value is not published twice under two spellings.
_PROMOTED: Final[frozenset[str]] = frozenset(
    {"name", "phase", "createdAt", "updatedAt", "creationTime"}
)


#: Nest's DataResource create READS different field names than it WRITES.
#:
#: ``handlers/dataresource.py:103-104`` takes ``type`` and ``class``, while
#: ``models.py:75,77`` (``DataResourceRecord.to_dict``) emits ``resourceType``
#: and ``storageClass`` — so a caller that round-trips a resource it just read
#: gets ``400 nest.dataresource.invalid: name and type are required``.
#:
#: **The spec documents this faithfully; it is not a spec-vs-handler
#: contradiction.** ``openapi/v1.yaml:1018`` (``CreateDataResourceRequest``)
#: is ``required: [name, type]`` with ``type``/``class``, matching the handler
#: exactly. ``resourceType``/``storageClass`` appear at ``:1048`` in
#: ``CreateDataResourceResponse``. What is asymmetric is the request schema
#: against the response schema of the same resource — which the spec states
#: and which is still a trap for any caller that renders a row and posts it
#: back.
#:
#: (An earlier version of this note claimed the spec documented the create
#: body as ``resourceType``/``storageClass`` and that the handler ignored it.
#: That was wrong, and it was written as if live-verified. The aliasing below
#: is unaffected — it was verified against a running Nest, which is where the
#: 400 above comes from.)
#:
#: Normalising here means one form in the UI cannot be silently wrong in one
#: direction. Nest's own names are passed through untouched, so a caller that
#: already speaks the wire format is unaffected.
CREATE_FIELD_ALIASES: Final[dict[str, dict[str, str]]] = {
    KIND_DATABASE: {"resourceType": "type", "storageClass": "class"},
}


#: Which key each collection's rows arrive under. **Nest has no single
#: collection envelope** — only data-resources uses ``items``:
#:
#: ===================  ===============  =========================================
#: kind                 envelope key     Nest handler
#: ===================  ===============  =========================================
#: ``database``         ``items``        ``handlers/dataresource.py:47``
#: ``snapshot``         ``snapshots``    ``handlers/protection.py:26``
#: ``protection_policy``  ``policies``   ``handlers/protection.py:206``
#: ``search_pool``      ``searchPools``  ``handlers/searchpool.py:25``
#: ===================  ===============  =========================================
#:
#: Reading ``items`` for all four and falling back to ``[]`` shipped a screen
#: that told the operator "No snapshots have been taken from this resource"
#: whatever Nest answered — three of the four kinds decoded as permanently
#: empty, with no error anywhere. A silent fallback turns an unrecognised shape
#: into a factual-looking "none", so :meth:`NestResponse.items` raises for an
#: absent key instead; see the note there.
COLLECTION_ENVELOPE_KEYS: Final[dict[str, str]] = {
    KIND_DATABASE: "items",
    KIND_SNAPSHOT: "snapshots",
    KIND_PROTECTION_POLICY: "policies",
    KIND_SEARCH_POOL: "searchPools",
}

#: The Nest list handler each kind is served by, so the table above can be
#: bound to Nest's own source rather than to this comment.
#: ``tests/api/test_nest_source_fixture.py`` parses these functions out of
#: ``apps/api/handlers/*.py`` and asserts the key each one emits.
NEST_LIST_HANDLERS: Final[dict[str, str]] = {
    KIND_DATABASE: "list_data_resources",
    KIND_SNAPSHOT: "list_snapshots",
    KIND_PROTECTION_POLICY: "list_protection_policies",
    KIND_SEARCH_POOL: "list_search_pools",
}


def envelope_key(kind: str) -> str:
    """Return the key a kind's rows arrive under.

    Raises:
        KeyError: for a kind with no declared key. Deliberately not a default
            of ``"items"`` — a new kind whose envelope nobody looked up would
            then decode as empty forever, which is the defect this table
            replaces.
    """
    return COLLECTION_ENVELOPE_KEYS[kind]


def to_create_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite a create payload into the field names Nest's handler reads.

    An alias is applied only when the target key is absent, so an explicit
    wire-format value always wins over an aliased one rather than one
    silently overwriting the other.
    """
    aliases = CREATE_FIELD_ALIASES.get(kind)
    if not aliases:
        return dict(payload)

    body = dict(payload)
    for portal_name, wire_name in aliases.items():
        if portal_name in body and wire_name not in body:
            body[wire_name] = body.pop(portal_name)
    return body


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse one of Nest's ISO-8601 strings into an aware datetime.

    Returns ``None`` for anything unparseable rather than raising: a
    malformed timestamp on one row must not fail the whole listing, and a
    missing "created" column renders as blank rather than as an outage.
    Naive values are assumed UTC, which is what Nest emits.
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def to_resource(kind: str, payload: dict[str, Any]) -> Resource:
    """Map one Nest record onto a portal :class:`Resource`.

    ``name`` is the identity for every kind — see the module docstring.
    """
    name = str(payload.get("name") or "")
    status_key = _STATUS_KEYS.get(kind)
    status = payload.get(status_key) if status_key else None

    created = parse_timestamp(payload.get("createdAt")) or parse_timestamp(
        payload.get("creationTime")
    )
    updated = parse_timestamp(payload.get("updatedAt"))

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in _PROMOTED and value not in (None, "")
    }
    if kind == KIND_DATABASE and payload.get("id"):
        metadata["nest_id"] = payload["id"]

    parent_id: str | None = None
    parent_kind: str | None = None
    if kind == KIND_SNAPSHOT:
        # A VolumeSnapshot names the PVC it was taken from; that edge is what
        # lets the Databases screen show a resource's snapshots without a
        # second lookup.
        source = payload.get("sourcePVC")
        if isinstance(source, str) and source:
            parent_id = source
            parent_kind = KIND_DATABASE

    return Resource(
        id=name,
        kind=kind,
        name=name,
        status=str(status) if status else None,
        created_at=created,
        updated_at=updated,
        parent_id=parent_id,
        parent_kind=parent_kind,
        metadata=metadata,
    )


def to_operation(payload: dict[str, Any]) -> Operation:
    """Map a Nest operation record onto the portal's :class:`Operation`.

    ``progress`` is always ``None``: Nest publishes a phase and nothing
    countable (``models.py:OperationRecord`` has no step/total fields), and
    the contract forbids synthesising a fraction from a state — a progress
    bar advancing on invented numbers is read as fact.

    ``result`` is Nest's own ``result`` object, passed through. This is the
    channel the contract added for exactly this product: a snapshot, restore
    or migrate finishes by producing an artefact, and without ``result``
    the UI would have to re-fetch the resource and guess which change was
    the one it started.
    """
    phase = str(payload.get("phase") or "")
    state = _PHASES.get(phase.lower(), OperationState.PENDING)

    result = payload.get("result")
    metadata: dict[str, Any] = {}
    op_type = payload.get("type")
    if op_type:
        metadata["type"] = op_type
    tenant = payload.get("tenant")
    if tenant:
        metadata["tenant"] = tenant

    return Operation(
        id=str(payload.get("id") or ""),
        kind=OP_KIND,
        state=state,
        status=phase,
        resource_id=str(payload["resource"]) if payload.get("resource") else None,
        resource_kind=KIND_DATABASE if payload.get("resource") else None,
        progress=None,
        detail=str(op_type) if op_type else None,
        error=str(payload["error"]) if payload.get("error") else None,
        result=result if isinstance(result, dict) else None,
        created_at=parse_timestamp(payload.get("startedAt")),
        completed_at=parse_timestamp(payload.get("completedAt")),
        metadata=metadata,
    )
