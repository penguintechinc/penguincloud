"""The one projection every audit surface serves.

Why this module exists
======================
All three routes that served audit rows returned ``dict(row)`` — the raw
database record, every column, whatever the table happens to hold today and
whatever is added to it tomorrow. ``security.md`` names this exact failure:

    a bug meant an endpoint that was only supposed to return a single string
    ended up returning the entire database object it came from ... Nothing
    crashed, no error, no signal anything was wrong.

The audit table is the worst place for it. Its rows describe who did what to
which resource, and its schema carries three columns no caller has any
business receiving:

* ``request_body`` — the submitted payload. Credentials, tokens, PII. It is
  unpopulated today (nothing passes it to ``models.create_audit_log``), which
  is exactly why excluding it now is cheap: the first writer that starts
  filling it would otherwise publish it through three endpoints at once,
  silently, with no code change anywhere near them.
* ``user_agent`` — actor device/browser fingerprint. Written only by the dead
  ``auth_features.audit_log`` path. Nothing renders it.
* ``response_status`` — internal proxy detail, never rendered.

``metadata`` (the schema's ``metadata_json``) is also excluded. It is a
free-form Text column into which ``create_audit_log`` writes a change
summary; free-form plus caller-influenced content is the same hazard as
``request_body`` in a smaller shape. See the report — if compliance export
needs the change summary, it is added HERE, once, deliberately, and after
reviewing what writers put in it.

One field set, not three
========================
Every surface projects through :class:`AuditRecord`: the dashboard activity
feed, ``/api/v1/audit/logs``, ``/api/v1/audit/export`` (JSON *and* the CSV
column order), and ``auth_features.get_audit_logs``. Three hand-written
projections is how one of them ends up with a column the others dropped —
and the CSV path derived its own headers from ``records[0].keys()``, so it
exported whatever the row happened to carry.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Final


# NOTE: this class's docstring is EXPORTED into openapi/v1.yaml as the
# AuditRecord schema description, so it is written for the API's readers.
# The reasoning behind the field choices — and the columns deliberately
# left out — is in this module's own docstring above, which is not
# published.
@dataclass(slots=True, frozen=True)
class AuditRecord:
    """One entry in a tenant's audit trail.

    Attributes:
        id: Identifier of this audit entry.
        user_id: Identifier of the user who performed the action, if the
            action had an authenticated actor.
        action: The event that was recorded, e.g. ``product.register``.
        resource_type: The kind of resource acted on, e.g. ``tenant``.
        resource_id: Identifier of the resource acted on.
        tenant_id: The tenant this entry belongs to.
        product_connection_id: The product connection involved, when the
            action was performed against a connected product.
        ip_address: Source address the action came from.
        created_at: When the action occurred, ISO-8601.
    """

    id: int
    user_id: int | None
    action: str
    resource_type: str | None
    resource_id: str | None
    tenant_id: int | None
    product_connection_id: int | None
    ip_address: str | None
    created_at: str | None


#: The published field names, in order. The CSV export takes its columns
#: from here rather than from whatever keys the first row happens to have.
AUDIT_RECORD_FIELDS: Final[tuple[str, ...]] = tuple(field.name for field in fields(AuditRecord))


def _isoformat(value: Any) -> str | None:
    """Render a timestamp for the wire, or None."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def to_audit_record(row: Any) -> AuditRecord:
    """Project one audit row onto the published field set.

    Reads by key rather than by attribute so it accepts a penguin-dal Row
    and a plain dict identically — the three call sites have both.
    """
    data = dict(row)
    return AuditRecord(
        id=int(data["id"]),
        user_id=data.get("user_id"),
        # The column is action_type; the wire name is action. Renaming here
        # rather than at each call site is the point of having one
        # projection: the dashboard feed was serving the raw row, so its
        # badge read `log.action` off a record that only had `action_type`
        # and rendered undefined.
        action=str(data.get("action_type") or ""),
        resource_type=data.get("resource_type"),
        resource_id=data.get("resource_id"),
        tenant_id=data.get("tenant_id"),
        product_connection_id=data.get("product_connection_id"),
        ip_address=data.get("ip_address"),
        created_at=_isoformat(data.get("created_at")),
    )


def to_audit_records(rows: Any) -> list[AuditRecord]:
    """Project a result set onto the published field set."""
    return [to_audit_record(row) for row in rows]
