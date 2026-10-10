"""Output formatting: `table` (TTY default) / `json` / `yaml`, plus `--query`.

`-o json` always emits the PORTAL's own response shape (after an optional
`--query` narrows it) -- never a CLI-invented projection. Table mode is the
one place pcli reshapes data at all, and only for display.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any

import jmespath
import yaml

from .api.manifest_types import ColumnSpec
from .render.cells import render_cell


def detect_default_format() -> str:
    """`table` on a TTY, `json` when piped -- checked once, at CLI startup."""
    return "table" if sys.stdout.isatty() else "json"


def apply_query(data: Any, query: str | None) -> Any:
    """Narrow `data` with a jmespath expression, or return it unchanged."""
    if not query:
        return data
    result: Any = jmespath.search(query, data)
    return result


def format_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A minimal, dependency-free fixed-width table -- no colour, no unicode box-drawing.

    Deliberately stdlib-only: a heavier table library is a pinned/audited
    dependency for a feature (box-drawing) a shell pipeline never looks at
    anyway (`-o json`/`-o yaml` are the scripting path; `table` is for a
    human at a TTY).
    """
    if not headers:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def _generic_dict_table(rows: Sequence[dict[str, Any]]) -> str:
    """Table rendering for rows with no `ColumnSpec` (e.g. `products list`, `tenants list`).

    Headers are the union of keys across every row, in first-seen order --
    a raw portal dict, not a manifest, so there is no declared column set
    to render against.
    """
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    table_rows = [[_scalar(row.get(h)) for h in headers] for row in rows]
    return format_table(headers, table_rows)


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value)
    return str(value)


def render_generic(data: Any, *, output: str, query: str | None) -> str:
    """Render an arbitrary JSON-like value (`whoami`, `products list`, `tenants list`, ...)."""
    queried = apply_query(data, query)
    if output == "json":
        return json.dumps(queried, indent=2, default=str)
    if output == "yaml":
        return yaml.safe_dump(queried, sort_keys=False, default_flow_style=False)
    # table
    if isinstance(queried, list) and (not queried or isinstance(queried[0], dict)):
        return _generic_dict_table(queried)
    # A query narrowed the shape below "list of dict" (a scalar, a bare
    # list of strings, ...) -- table mode has nothing tabular left to draw,
    # so fall back to the same JSON rendering json/yaml would give rather
    # than fabricating a one-column table.
    return json.dumps(queried, indent=2, default=str)


def render_resource_rows(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[ColumnSpec],
    *,
    output: str,
    query: str | None,
) -> str:
    """Render a manifest-discovered resource's rows.

    `-o json`/`-o yaml` emit `rows` (after `--query`) UNCHANGED -- the
    portal's own wire shape, never cell-rendered strings. `table` mode is
    the only path that runs each cell through `render_cell`, and only when
    `--query` has not already reshaped the rows away from "list of dict".
    """
    queried = apply_query(list(rows), query)
    if output == "json":
        return json.dumps(queried, indent=2, default=str)
    if output == "yaml":
        return yaml.safe_dump(queried, sort_keys=False, default_flow_style=False)
    if not (isinstance(queried, list) and (not queried or isinstance(queried[0], dict))):
        return json.dumps(queried, indent=2, default=str)
    if query:
        # Shape may no longer match `columns` (a query can drop/rename
        # fields) -- degrade to the generic dict table rather than risk
        # `render_cell` reading a field that is no longer present.
        return _generic_dict_table(queried)
    headers = [c.label for c in columns]
    table_rows = [[render_cell(c, row) for c in columns] for row in queried]
    return format_table(headers, table_rows)
