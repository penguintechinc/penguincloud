"""Tests for `pcli.output` -- table/json/yaml rendering + `--query`."""

from __future__ import annotations

import json

import yaml

from pcli.api.manifest_types import CellSpec, ColumnSpec
from pcli.output import (
    apply_query,
    format_table,
    render_generic,
    render_resource_rows,
)


def test_apply_query_none_returns_data_unchanged() -> None:
    """Apply query none returns data unchanged."""
    data = {"a": 1}
    assert apply_query(data, None) is data


def test_apply_query_narrows_with_jmespath() -> None:
    """Apply query narrows with jmespath."""
    data = {"products": [{"id": 1}, {"id": 2}]}
    assert apply_query(data, "products[].id") == [1, 2]


def test_format_table_basic() -> None:
    """Format table basic."""
    table = format_table(["ID", "Name"], [["1", "alice"], ["2", "bob"]])
    lines = table.splitlines()
    assert lines[0].startswith("ID")
    assert "alice" in lines[2]


def test_format_table_empty_headers_returns_empty_string() -> None:
    """Format table empty headers returns empty string."""
    assert format_table([], []) == ""


def test_generic_dict_table_renders_none_as_blank_and_nested_as_json() -> None:
    """`_scalar`'s two special cases: `None` -> blank cell, dict/list -> inline JSON."""
    result = render_generic(
        [{"id": 1, "note": None, "tags": ["a", "b"]}], output="table", query=None
    )
    lines = result.splitlines()
    assert '["a", "b"]' in lines[2]
    # The "note" column for row 1 is blank, not the string "None".
    assert "None" not in lines[2]


class TestRenderGeneric:
    """Render generic."""

    def test_json_emits_exact_shape(self) -> None:
        """Json emits exact shape."""
        data = {"id": 1, "name": "gough"}
        result = render_generic(data, output="json", query=None)
        assert json.loads(result) == data

    def test_yaml_round_trips(self) -> None:
        """Yaml round trips."""
        data = [{"id": 1}, {"id": 2}]
        result = render_generic(data, output="yaml", query=None)
        assert yaml.safe_load(result) == data

    def test_table_of_dict_rows(self) -> None:
        """Table of dict rows."""
        data = [{"id": 1, "name": "gough"}, {"id": 2, "name": "nest"}]
        result = render_generic(data, output="table", query=None)
        assert "gough" in result
        assert "nest" in result

    def test_table_falls_back_to_json_when_query_narrows_below_list_of_dict(self) -> None:
        """Table falls back to json when query narrows below list of dict."""
        data = {"products": [{"id": 1}, {"id": 2}]}
        result = render_generic(data, output="table", query="products[].id")
        assert json.loads(result) == [1, 2]

    def test_json_with_query_emits_narrowed_shape_verbatim(self) -> None:
        """Json with query emits narrowed shape verbatim."""
        data = {"a": {"b": [1, 2, 3]}}
        result = render_generic(data, output="json", query="a.b")
        assert json.loads(result) == [1, 2, 3]


class TestRenderResourceRows:
    """Render resource rows."""

    def _columns(self) -> list[ColumnSpec]:
        return [
            ColumnSpec(field="id", label="ID", cell=CellSpec(kind="text")),
            ColumnSpec(
                field="scope_id",
                label="Scope",
                cell=CellSpec(kind="text"),
                absent_as="literal:Everyone",
            ),
        ]

    def test_json_emits_raw_portal_shape_not_cell_rendered_strings(self) -> None:
        """The task's own proof requirement: `-o json` emits the portal shape."""
        rows = [{"id": "1", "scope_id": None}]
        result = render_resource_rows(rows, self._columns(), output="json", query=None)
        parsed = json.loads(result)
        # Raw None survives -- NOT rendered through absent_as ("Everyone").
        assert parsed == [{"id": "1", "scope_id": None}]

    def test_table_applies_absent_as(self) -> None:
        """Table applies absent as."""
        rows = [{"id": "1", "scope_id": None}]
        result = render_resource_rows(rows, self._columns(), output="table", query=None)
        assert "Everyone" in result
        assert "None" not in result

    def test_table_with_real_value_shows_it(self) -> None:
        """Table with real value shows it."""
        rows = [{"id": "1", "scope_id": "team-42"}]
        result = render_resource_rows(rows, self._columns(), output="table", query=None)
        assert "team-42" in result

    def test_query_narrowing_to_scalars_falls_back_to_json(self) -> None:
        """Query narrowing falls back to generic table."""
        rows = [{"id": "1", "scope_id": "x"}, {"id": "2", "scope_id": "y"}]
        result = render_resource_rows(rows, self._columns(), output="table", query="[].id")
        # Query reshapes to a bare list of strings -- not list-of-dict, so
        # this degrades to the JSON fallback rather than a fabricated table.
        assert json.loads(result) == ["1", "2"]

    def test_query_narrowing_that_stays_list_of_dict_uses_generic_table(self) -> None:
        """A query that reshapes fields (but stays list-of-dict) uses the generic table.

        NOT the `ColumnSpec`-driven one -- `render_cell` would read a
        `scope_id` field a projection like this one may have dropped.
        """
        rows = [{"id": "1", "scope_id": "x"}, {"id": "2", "scope_id": "y"}]
        result = render_resource_rows(
            rows, self._columns(), output="table", query="[].{identifier: id}"
        )
        assert "identifier" in result
        assert "1" in result and "2" in result

    def test_yaml_output(self) -> None:
        """Yaml output."""
        rows = [{"id": "1", "scope_id": "x"}]
        result = render_resource_rows(rows, self._columns(), output="yaml", query=None)
        assert yaml.safe_load(result) == rows

    def test_empty_rows_table(self) -> None:
        """Empty rows table."""
        result = render_resource_rows([], self._columns(), output="table", query=None)
        assert "ID" in result
        assert "Scope" in result
