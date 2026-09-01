"""Map WaddleAI's payloads onto the portal's contract-v2 shapes.

The collection envelope table is the load-bearing part of this module, for
the same reason Gough's and Tobogganing's are: assuming ``items`` when a
product does not use it is how a collection renders as permanently empty
with nothing failing anywhere (Phase 4N).

============================ ================ ==============================
route                        envelope key      source
============================ ================ ==============================
``GET /api/v1/providers``    ``providers``     ``providers.py``'s
                                                ``ProviderListResponse``/
                                                ``list_providers()``
``GET /api/v1/knowledge``    ``documents``     ``knowledge.py``'s
                                                ``list_knowledge()``
``GET /api/v1/quotas``       ``quotas``        ``quotas.py``'s
                                                ``list_quotas()``
============================ ================ ==============================

Read from WaddleAI's own handler source
(``services/management/app/api/v1/{providers,knowledge,quotas}.py``,
``penguintechinc/waddleai``), not transcribed from the OpenAPI spec:
``knowledge`` and ``quotas`` are explicitly unannotated there ("Response
schema not yet annotated with @validate_response"), so the spec alone
cannot prove either shape.

``quota`` rows are genuinely heterogeneous
===========================================
Unlike every other resource in this codebase, ``GET /api/v1/quotas`` returns
ONE list mixing three row shapes discriminated by a ``type`` field —
``"organization"`` rows carry ``token_quota_daily``/``token_quota_monthly``,
``"user"`` rows carry the same two fields plus ``organization_id``, and
``"key"`` rows carry ``budget_limit_daily``/``budget_limit_monthly``/
``tpm_limit``/``rpm_limit`` instead. This is a fact about the product (there
is no per-type list endpoint to split them across), not a modelling choice
here — the manifest's ``absent_as`` machinery exists precisely to describe a
column that is real for some rows of a kind and absent for others.

It is also why ``quota`` ids are NOT unique within the kind: an organization,
a user and a virtual key can all report ``id=1`` in the same response. See
:meth:`~app.adapters.waddleai.adapter.WaddleAIAdapter.get_resource`'s
docstring for how that is handled rather than papered over.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from ..base import Resource

__all__ = [
    "KIND_PROVIDER",
    "KIND_KNOWLEDGE_DOCUMENT",
    "KIND_QUOTA",
    "RESOURCE_KINDS",
    "COLLECTION_ENVELOPE_KEYS",
    "KIND_LIST_ROUTES",
    "NAME_FIELDS",
    "envelope_key",
    "parse_timestamp",
    "to_resource",
]

#: Portal-facing resource kinds — the vocabulary this adapter's callers use.
KIND_PROVIDER: Final[str] = "provider"
KIND_KNOWLEDGE_DOCUMENT: Final[str] = "knowledge_document"
KIND_QUOTA: Final[str] = "quota"

RESOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {KIND_PROVIDER, KIND_KNOWLEDGE_DOCUMENT, KIND_QUOTA}
)

#: The key each kind's rows arrive under. Graded against the product's own
#: handlers — see the module docstring.
COLLECTION_ENVELOPE_KEYS: Final[dict[str, str]] = {
    KIND_PROVIDER: "providers",
    KIND_KNOWLEDGE_DOCUMENT: "documents",
    KIND_QUOTA: "quotas",
}

#: The ``"METHOD /path"`` each kind is listed from — documentation anchor for
#: the table above, matching :mod:`app.adapters.tobogganing.mapping`'s
#: precedent.
KIND_LIST_ROUTES: Final[dict[str, str]] = {
    KIND_PROVIDER: "GET /api/v1/providers",
    KIND_KNOWLEDGE_DOCUMENT: "GET /api/v1/knowledge",
    KIND_QUOTA: "GET /api/v1/quotas",
}

#: Which field carries a human-readable name, per kind, tried in order. A
#: knowledge document has no ``name`` field at all — ``source`` (the
#: original filename) is the closest thing ``knowledge.py``'s ``_serialize``
#: emits.
NAME_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    KIND_PROVIDER: ("name", "id"),
    KIND_KNOWLEDGE_DOCUMENT: ("source", "id"),
    KIND_QUOTA: ("name", "id"),
}


def envelope_key(kind: str) -> str:
    """Return the key a kind's rows arrive under.

    Raises:
        KeyError: for a kind with no declared key — deliberately not a
            default of ``"items"``, see the module docstring.
    """
    return COLLECTION_ENVELOPE_KEYS[kind]


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse one of WaddleAI's ``datetime.isoformat()`` timestamps, tolerating absence.

    Returns ``None`` rather than raising — a missing or unparseable
    timestamp should degrade one field, not fail the whole row. Naive values
    (``knowledge.py``/``providers.py`` both emit ``datetime.utcnow()``-based
    strings with no offset) are read as UTC.
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _display_name(kind: str, row: dict[str, Any]) -> str:
    """First populated name-ish field for a kind, else the id."""
    for candidate in NAME_FIELDS.get(kind, ("name", "id")):
        value = row.get(candidate)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int) and candidate == "id":
            return str(value)
    identifier = row.get("id")
    return str(identifier) if identifier is not None else ""


def _status(row: dict[str, Any]) -> str | None:
    """Verbatim lifecycle state.

    None of the three kinds carries a string status field — each has a
    boolean ``enabled`` instead (``ai_providers.enabled``,
    ``organizations.enabled``, ``users.enabled``, ``virtual_keys.enabled``).
    Rendered as ``"enabled"``/``"disabled"`` rather than left as a raw
    ``True``/``False``, which :class:`~app.adapters.base.Resource.status`'s
    own docstring already treats as free text for display — a direct,
    non-fabricated reading of the one lifecycle-shaped field these rows
    have.
    """
    enabled = row.get("enabled")
    if isinstance(enabled, bool):
        return "enabled" if enabled else "disabled"
    return None


def to_resource(kind: str, row: dict[str, Any]) -> Resource:
    """Convert one WaddleAI row into a contract-v2 :class:`Resource`.

    Everything not modelled by a named contract field is left in
    ``metadata`` rather than dropped, matching every other adapter in this
    codebase.
    """
    known = {"id", "name", "source", "enabled", "created_at"}
    identifier = row.get("id")
    return Resource(
        id=str(identifier) if identifier is not None else "",
        kind=kind,
        name=_display_name(kind, row),
        status=_status(row),
        created_at=parse_timestamp(row.get("created_at")),
        updated_at=None,  # none of these three kinds reports one
        metadata={key: value for key, value in row.items() if key not in known},
    )
