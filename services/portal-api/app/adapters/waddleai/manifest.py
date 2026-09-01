"""WaddleAI's console manifest — Phase 8 acceptance test (design §8).

The onboarding proof: this manifest, the adapter it validates against, and
two lines in ``app.adapters.__init__`` (a ``MANIFEST_REGISTRY`` entry plus a
``PLANNED_PRODUCTS`` removal) are the ONLY changes needed to make WaddleAI
connectable and browsable in the webui — no new screen code, no new CLI
command code. See ``tests/architecture/test_waddleai_zero_frontend_onboarding.py``
for the mechanical proof of that claim.

Scope: three resources, list + columns only — see ``adapter.py``'s module
docstring for what was left out and why. Every resource is
``transport="proxy"`` (no typed create/delete/action dispatch — the adapter
exposes no such capability) and every ``item_path`` is ``None`` (see
``adapter.py``'s and ``routes.py``'s docstrings for why, including for
``provider`` and ``knowledge_document``, which DO have a real item route on
the product).

Column field names are WaddleAI's OWN raw JSON keys — read directly off
``services/management/app/api/v1/{providers,knowledge,quotas}.py`` on
``penguintechinc/waddleai`` — not the portal's normalised
:class:`~app.adapters.base.Resource` fields. Design §6.4: for a proxied read,
the manifest IS the type contract.
"""

from __future__ import annotations

from typing import Final

from ..manifest import (
    BooleanLabels,
    CellSpec,
    ColumnSpec,
    ConsoleManifest,
    EnvelopeSpec,
    ListSpec,
    NavItem,
    NavSpec,
    ResourceDescriptor,
    validate_manifest,
)
from .adapter import WaddleAIAdapter
from .mapping import (
    COLLECTION_ENVELOPE_KEYS,
    KIND_KNOWLEDGE_DOCUMENT,
    KIND_PROVIDER,
    KIND_QUOTA,
)
from .routes import PATH_KNOWLEDGE, PATH_PROVIDERS, PATH_QUOTAS

__all__ = ["WADDLEAI_MANIFEST"]

#: No verb any resource here declares an action for — this cut is read-only,
#: matching the empty table Tobogganing's own read-only manifest passes.
_ACTION_VERBS: Final[dict[str, frozenset[str]]] = {}

#: Per-kind :class:`~app.adapters.manifest.EnvelopeSpec` key path, handed to
#: :func:`~app.adapters.manifest.validate_manifest` as ``envelope_paths``.
#: Derived from :data:`~app.adapters.waddleai.mapping.COLLECTION_ENVELOPE_KEYS`
#: rather than hand-typed per resource, so the two tables cannot drift.
_ENVELOPE_PATHS: Final[dict[str, tuple[str, ...]]] = {
    kind: (key,) for kind, key in COLLECTION_ENVELOPE_KEYS.items()
}

# ---------------------------------------------------------------------------
# provider
# ---------------------------------------------------------------------------

#: Field set and order lifted from ``ProviderSummary``
#: (``services/management/app/api/v1/providers.py`` — also byte-equal to
#: ``openapi/v1.yaml``'s ``ProviderSummary`` schema, which IS fully
#: annotated). ``model_list`` and ``rate_limits`` are omitted: both are
#: arrays/objects, not scalar-renderable in a table cell, matching the
#: precedent set by Gough's own ``_NODES_COLUMNS`` (never fabricating a cell
#: kind for a field this schema version has no shape for).
_PROVIDER_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(field="provider_type", label="Type", cell=CellSpec(kind="text")),
    ColumnSpec(field="endpoint_url", label="Endpoint", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="enabled",
        label="Enabled",
        cell=CellSpec(kind="boolean", labels=BooleanLabels("Enabled", "Disabled")),
        absent_as="dash",
    ),
    ColumnSpec(field="priority", label="Priority", cell=CellSpec(kind="number"), absent_as="dash"),
    ColumnSpec(field="created_at", label="Created", cell=CellSpec(kind="text"), absent_as="dash"),
)

_PROVIDER: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_PROVIDER,
    label="Provider",
    plural_label="Providers",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=_PROVIDER_COLUMNS,
    empty_state="No AI providers configured yet.",
    error_state="Unable to load providers.",
    list=ListSpec(
        path_bytes=PATH_PROVIDERS,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_PROVIDER]),
        pagination="none",
    ),
    item_path=None,  # real item route exists; unreviewed extra fields -- see adapter.py
)

# ---------------------------------------------------------------------------
# knowledge_document
# ---------------------------------------------------------------------------

#: Field set lifted from ``knowledge.py``'s ``_serialize`` — the SAME
#: function backing both the list and the (unused, see ``adapter.py``) item
#: route, so list and detail rows are byte-identical. ``content`` (the full
#: chunked document text) is omitted: it is a large text blob, not a table
#: cell, matching Tobogganing's own ``markdown`` omission for ``block_page``.
_KNOWLEDGE_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="id", label="ID", cell=CellSpec(kind="number"), absent_as="dash"),
    ColumnSpec(field="source", label="Source file", cell=CellSpec(kind="text")),
    ColumnSpec(field="created_at", label="Uploaded", cell=CellSpec(kind="text"), absent_as="dash"),
)

_KNOWLEDGE_DOCUMENT: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_KNOWLEDGE_DOCUMENT,
    label="Document",
    plural_label="Knowledge Documents",
    id_field="id",
    name_field="source",
    transport="proxy",
    columns=_KNOWLEDGE_COLUMNS,
    empty_state="No knowledge documents uploaded yet.",
    error_state="Unable to load knowledge documents.",
    list=ListSpec(
        path_bytes=PATH_KNOWLEDGE,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_KNOWLEDGE_DOCUMENT]),
        pagination="none",
    ),
    item_path=None,  # real item route adds nothing the list row lacks -- see adapter.py
)

# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------

#: Heterogeneous rows: ``quotas.py``'s ``list_quotas`` mixes organization,
#: user and virtual-key rows in one response, discriminated by ``type``.
#: Every field below is real for AT LEAST one row type and genuinely absent
#: for the others (``token_quota_daily``/``token_quota_monthly`` for
#: organization/user rows, ``budget_limit_daily``/``budget_limit_monthly``
#: for key rows) — ``absent_as="dash"`` is not a defensive default here, it
#: is describing a fact about the response. See ``mapping.py``'s module
#: docstring for the full row-shape table.
_QUOTA_COLUMNS: Final[tuple[ColumnSpec, ...]] = (
    ColumnSpec(field="type", label="Type", cell=CellSpec(kind="text")),
    ColumnSpec(field="name", label="Name", cell=CellSpec(kind="text")),
    ColumnSpec(
        field="enabled",
        label="Enabled",
        cell=CellSpec(kind="boolean", labels=BooleanLabels("Enabled", "Disabled")),
        absent_as="dash",
    ),
    ColumnSpec(
        field="token_quota_daily",
        label="Daily tokens",
        cell=CellSpec(kind="number"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="token_quota_monthly",
        label="Monthly tokens",
        cell=CellSpec(kind="number"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="budget_limit_daily",
        label="Daily budget",
        cell=CellSpec(kind="number"),
        absent_as="dash",
    ),
    ColumnSpec(
        field="budget_limit_monthly",
        label="Monthly budget",
        cell=CellSpec(kind="number"),
        absent_as="dash",
    ),
)

_QUOTA: Final[ResourceDescriptor] = ResourceDescriptor(
    kind=KIND_QUOTA,
    label="Quota",
    plural_label="Quotas",
    id_field="id",
    name_field="name",
    transport="proxy",
    columns=_QUOTA_COLUMNS,
    empty_state="No quota configurations defined yet.",
    error_state="Unable to load quotas.",
    list=ListSpec(
        path_bytes=PATH_QUOTAS,
        envelope=EnvelopeSpec(keys=_ENVELOPE_PATHS[KIND_QUOTA]),
        pagination="none",
    ),
    # WaddleAI has no GET /api/v1/quotas/{id} at all, and quota ids are not
    # unique across row types -- see adapter.py's get_resource docstring.
    item_path=None,
)

# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

WADDLEAI_MANIFEST: Final[ConsoleManifest] = ConsoleManifest(
    manifest_version=2,
    product_type=WaddleAIAdapter.PRODUCT_TYPE,
    display_name=WaddleAIAdapter.DISPLAY_NAME,
    nav=NavSpec(
        items=(
            NavItem(kind=KIND_PROVIDER, label="Providers"),
            NavItem(kind=KIND_KNOWLEDGE_DOCUMENT, label="Knowledge"),
            NavItem(kind=KIND_QUOTA, label="Quotas"),
        )
    ),
    resources=(_PROVIDER, _KNOWLEDGE_DOCUMENT, _QUOTA),
    # No operations block: none of the three resources has an async
    # operation to poll (see adapter.py, "No operations").
    operations=None,
    # No metrics tile: "metrics_summary" is not among the capabilities
    # WaddleAIAdapter.capabilities() reports.
    metrics=None,
    extensions=(),
)

# Fail closed at import time -- Design §11.1. A manifest that does not pass
# this refuses to load; nothing downstream ever sees a partially-valid one.
validate_manifest(
    WADDLEAI_MANIFEST,
    WaddleAIAdapter,
    action_verbs=_ACTION_VERBS,
    sensitive_fields=frozenset(),  # WaddleAIAdapter declares no SENSITIVE_FIELDS
    envelope_paths=_ENVELOPE_PATHS,
    supports_cancel=False,
    supports_operation_logs=False,
)
