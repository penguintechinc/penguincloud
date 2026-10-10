"""Render one `ColumnSpec` + one row into a display string, for `table` output.

Python analogue of `services/webui/src/client/components/kit/manifestCells.tsx`
-- same `CELL_KINDS` union, same `absent_as` semantics, same "unknown kind
degrades to text" posture (Design SS3.4). Text-only, unlike the TS renderer
(no colour/badge styling), since a terminal table has no equivalent of a
Tailwind class -- `EnumStyle.style` is read and ignored here, not
reproduced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..api.manifest_types import CellSpec, ColumnSpec

#: Mirrors `app.adapters.manifest.CELL_KINDS` -- the closed set a manifest
#: may declare. A kind outside this set (a manifest served by a newer
#: schema version than this build) degrades to `text` rather than raising,
#: matching Design SS3.4's "never render blank, never crash" rule.
_KNOWN_CELL_KINDS: frozenset[str] = frozenset(
    {
        "text",
        "enum_badge",
        "tags",
        "number",
        "bytes",
        "money",
        "timestamp",
        "boolean",
        "link",
        "count",
    }
)

_ABSENT_DASH: str = "—"  # em dash, matches the webui's own AbsentMarker default


def render_absent(absent_as: str | None) -> str:
    """The display text for a column whose value is missing.

    `absent_as` is required on every non-`text` column by
    `app.adapters.manifest._require_absent_as`, so a well-formed manifest
    always hands this `"dash"` / `"zero"` / `"literal:<text>"` for anything
    that reaches here; `None` or an unrecognised spelling both degrade to
    the dash, same "never crash on a value this module did not itself
    validate" posture as the TS renderer.
    """
    if absent_as == "zero":
        return "0"
    if absent_as and absent_as.startswith("literal:"):
        return absent_as[len("literal:") :]
    return _ABSENT_DASH


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = abs(value)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    sign = "-" if value < 0 else ""
    precision = 1 if size < 10 and unit_index > 0 else 0
    return f"{sign}{size:.{precision}f} {units[unit_index]}"


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        # `datetime.fromisoformat` (3.11+) accepts a trailing "Z" directly;
        # kept explicit for clarity and for interpreters where it does not.
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_relative_timestamp(raw: str) -> str:
    parsed = _parse_timestamp(raw)
    if parsed is None:
        return raw
    now = datetime.now(parsed.tzinfo or UTC)
    delta_seconds = round((now - parsed).total_seconds())
    suffix = "ago" if delta_seconds >= 0 else "from now"
    abs_seconds = abs(delta_seconds)
    if abs_seconds < 60:
        return f"{abs_seconds}s {suffix}"
    if abs_seconds < 3600:
        return f"{round(abs_seconds / 60)}m {suffix}"
    if abs_seconds < 86400:
        return f"{round(abs_seconds / 3600)}h {suffix}"
    return f"{round(abs_seconds / 86400)}d {suffix}"


def _format_absolute_timestamp(raw: str) -> str:
    parsed = _parse_timestamp(raw)
    return raw if parsed is None else parsed.isoformat(sep=" ", timespec="seconds")


def _render_present(cell: CellSpec, column: ColumnSpec, value: Any, row: dict[str, Any]) -> str:
    kind = cell.kind if cell.kind in _KNOWN_CELL_KINDS else "text"

    if kind == "text":
        return str(value)

    if kind == "enum_badge":
        return str(value)

    if kind == "tags":
        tags = [str(t) for t in value] if isinstance(value, list) else []
        if not tags:
            return render_absent(column.absent_as)
        return ", ".join(tags)

    if kind == "number":
        return f"{value} {cell.unit}" if cell.unit else str(value)

    if kind == "bytes":
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        return _format_bytes(numeric)

    if kind == "money":
        try:
            numeric = float(value)
            amount = f"{numeric:.2f}"
        except (TypeError, ValueError):
            amount = str(value)
        currency = row.get(cell.currency_field) if cell.currency_field else None
        return f"{amount} {currency}" if currency else amount

    if kind == "timestamp":
        raw = str(value)
        return _format_relative_timestamp(raw) if cell.relative else _format_absolute_timestamp(raw)

    if kind == "boolean":
        if value is True:
            return cell.labels.true_label if cell.labels else "True"
        if value is False:
            return cell.labels.false_label if cell.labels else "False"
        return str(value)

    if kind == "link":
        target = row.get(cell.id_field) if cell.id_field else value
        return str(target if target is not None else value)

    if kind == "count":
        if isinstance(value, list):
            return str(len(value))
        if isinstance(value, int | float):
            return str(value)
        return "0"

    # Unreachable: every branch of _KNOWN_CELL_KINDS is handled above, and
    # an unknown kind was already remapped to "text" before this point.
    return str(value)  # pragma: no cover


def render_cell(column: ColumnSpec, row: dict[str, Any]) -> str:
    """Render `row[column.field]` through `column.cell.kind`, honouring `absent_as`.

    Absence is `None` only -- a real `0`, `False`, or `[]` is a fact to
    render, not a missing value (Design SS3.3's own example: "a missing
    billing summary rendered as 0.00"). `tags` additionally treats an empty
    list as absent, inside its own branch above, matching the TS renderer.
    """
    value = row.get(column.field)
    if value is None:
        return render_absent(column.absent_as)
    return _render_present(column.cell, column, value, row)
