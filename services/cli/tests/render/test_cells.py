"""Tests for `pcli.render.cells` -- `absent_as` semantics + every `CELL_KINDS` renderer."""

from __future__ import annotations

import pytest

from pcli.api.manifest_types import BooleanLabels, CellSpec, ColumnSpec, EnumStyle
from pcli.render.cells import render_absent, render_cell


def _column(
    field: str = "f", cell: CellSpec | None = None, absent_as: str | None = None
) -> ColumnSpec:
    return ColumnSpec(
        field=field, label="F", cell=cell or CellSpec(kind="text"), absent_as=absent_as
    )


class TestAbsentAs:
    """Absent as."""

    def test_dash_renders_em_dash(self) -> None:
        """Dash renders em dash."""
        assert render_absent("dash") == "—"

    def test_zero_renders_real_zero(self) -> None:
        """Zero renders real zero."""
        assert render_absent("zero") == "0"

    def test_literal_renders_its_own_text(self) -> None:
        """The exact `literal:Everyone` case named in the task brief."""
        assert render_absent("literal:Everyone") == "Everyone"

    def test_none_degrades_to_dash(self) -> None:
        """None degrades to dash."""
        assert render_absent(None) == "—"

    def test_unrecognised_spelling_degrades_to_dash(self) -> None:
        """Unrecognised spelling degrades to dash."""
        assert render_absent("not-a-real-mode") == "—"

    @pytest.mark.parametrize(
        ("absent_as", "expected"),
        [("dash", "—"), ("zero", "0"), ("literal:Everyone", "Everyone"), (None, "—")],
    )
    def test_render_cell_on_null_value(self, absent_as: str, expected: str) -> None:
        """Render cell on null value."""
        column = _column(cell=CellSpec(kind="number"), absent_as=absent_as)
        assert render_cell(column, {"f": None}) == expected

    def test_real_zero_is_not_treated_as_absent(self) -> None:
        """Design SS3.3's own example: a real 0 must render as 0, not the dash."""
        column = _column(cell=CellSpec(kind="number"), absent_as="dash")
        assert render_cell(column, {"f": 0}) == "0"

    def test_real_false_is_not_treated_as_absent(self) -> None:
        """Real false is not treated as absent."""
        column = _column(cell=CellSpec(kind="boolean"), absent_as="dash")
        assert render_cell(column, {"f": False}) == "False"

    def test_empty_list_is_absent_for_text_kind_but_not_number(self) -> None:
        """Empty list is absent for text kind but not number."""
        # `[]` for a plain `number`/`text` cell isn't a recognised "absent"
        # shape (it's just an odd value) -- render it verbatim.
        column = _column(cell=CellSpec(kind="text"))
        assert render_cell(column, {"f": []}) == "[]"

    def test_tags_empty_list_is_treated_as_absent(self) -> None:
        """Tags empty list is treated as absent."""
        column = _column(cell=CellSpec(kind="tags"), absent_as="literal:None")
        assert render_cell(column, {"f": []}) == "None"

    def test_tags_nonempty_joins_with_comma(self) -> None:
        """Tags nonempty joins with comma."""
        column = _column(cell=CellSpec(kind="tags"))
        assert render_cell(column, {"f": ["a", "b"]}) == "a, b"


class TestCellKinds:
    """Cell kinds."""

    def test_text(self) -> None:
        """Text."""
        column = _column(cell=CellSpec(kind="text"))
        assert render_cell(column, {"f": "hello"}) == "hello"

    def test_enum_badge_renders_plain_value(self) -> None:
        """Enum badge renders plain value."""
        cell = CellSpec(kind="enum_badge", styles=(EnumStyle(value="healthy", style="success"),))
        column = _column(cell=cell)
        assert render_cell(column, {"f": "healthy"}) == "healthy"

    def test_number_with_unit(self) -> None:
        """Number with unit."""
        column = _column(cell=CellSpec(kind="number", unit="GB"))
        assert render_cell(column, {"f": 4}) == "4 GB"

    def test_number_without_unit(self) -> None:
        """Number without unit."""
        column = _column(cell=CellSpec(kind="number"))
        assert render_cell(column, {"f": 4}) == "4"

    def test_bytes_formats_base_1024(self) -> None:
        """Bytes formats base 1024."""
        column = _column(cell=CellSpec(kind="bytes"))
        assert render_cell(column, {"f": 1024}) == "1.0 KB"
        assert render_cell(column, {"f": 500}) == "500 B"
        assert render_cell(column, {"f": 1024 * 1024 * 3}) == "3.0 MB"

    def test_bytes_non_numeric_falls_back_to_string(self) -> None:
        """Bytes non numeric falls back to string."""
        column = _column(cell=CellSpec(kind="bytes"))
        assert render_cell(column, {"f": "not-a-number"}) == "not-a-number"

    def test_money_with_currency_field(self) -> None:
        """Money with currency field."""
        cell = CellSpec(kind="money", currency_field="ccy")
        column = _column(cell=cell)
        assert render_cell(column, {"f": 9.5, "ccy": "USD"}) == "9.50 USD"

    def test_money_without_currency_field(self) -> None:
        """Money without currency field."""
        column = _column(cell=CellSpec(kind="money"))
        assert render_cell(column, {"f": 9.5}) == "9.50"

    def test_money_non_numeric_falls_back_to_string(self) -> None:
        """A non-numeric `money` value renders as-is rather than raising."""
        column = _column(cell=CellSpec(kind="money"))
        assert render_cell(column, {"f": "not-a-number"}) == "not-a-number"

    def test_timestamp_absolute(self) -> None:
        """Timestamp absolute."""
        column = _column(cell=CellSpec(kind="timestamp", relative=False))
        result = render_cell(column, {"f": "2026-01-01T00:00:00+00:00"})
        assert "2026-01-01" in result

    def test_timestamp_relative_falls_back_to_raw_on_unparseable(self) -> None:
        """Timestamp relative falls back to raw on unparseable."""
        column = _column(cell=CellSpec(kind="timestamp", relative=True))
        assert render_cell(column, {"f": "not-a-date"}) == "not-a-date"

    def test_timestamp_relative_parseable_renders_ago(self) -> None:
        """A real, parseable timestamp in the past renders as `"<n><unit> ago"`."""
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        column = _column(cell=CellSpec(kind="timestamp", relative=True))
        result = render_cell(column, {"f": past})
        assert result.endswith("ago")

    def test_timestamp_relative_parseable_z_suffix(self) -> None:
        """A trailing `Z` (UTC shorthand) is accepted, not just `+00:00`."""
        column = _column(cell=CellSpec(kind="timestamp", relative=True))
        result = render_cell(column, {"f": "2020-01-01T00:00:00Z"})
        assert result.endswith("ago")

    def test_timestamp_relative_future_renders_from_now(self) -> None:
        """A timestamp in the future renders `"from now"`, not `"ago"`."""
        from datetime import UTC, datetime, timedelta

        future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        column = _column(cell=CellSpec(kind="timestamp", relative=True))
        result = render_cell(column, {"f": future})
        assert result.endswith("from now")

    def test_boolean_true_with_labels(self) -> None:
        """Boolean true with labels."""
        cell = CellSpec(kind="boolean", labels=BooleanLabels(true_label="Yes", false_label="No"))
        column = _column(cell=cell)
        assert render_cell(column, {"f": True}) == "Yes"

    def test_boolean_false_without_labels_defaults(self) -> None:
        """Boolean false without labels defaults."""
        column = _column(cell=CellSpec(kind="boolean"))
        assert render_cell(column, {"f": False}) == "False"

    def test_boolean_non_boolean_value_renders_verbatim(self) -> None:
        """A `boolean` cell whose upstream value is neither True nor False renders as-is."""
        column = _column(cell=CellSpec(kind="boolean"))
        assert render_cell(column, {"f": "maybe"}) == "maybe"

    def test_link_uses_id_field(self) -> None:
        """Link uses id field."""
        cell = CellSpec(kind="link", id_field="node_id")
        column = _column(cell=cell)
        assert render_cell(column, {"f": "Node One", "node_id": "n-1"}) == "n-1"

    def test_link_falls_back_to_value_when_no_id_field(self) -> None:
        """Link falls back to value when no id field."""
        column = _column(cell=CellSpec(kind="link"))
        assert render_cell(column, {"f": "Node One"}) == "Node One"

    def test_count_on_list(self) -> None:
        """Count on list."""
        column = _column(cell=CellSpec(kind="count"))
        assert render_cell(column, {"f": ["a", "b", "c"]}) == "3"

    def test_count_on_int(self) -> None:
        """Count on int."""
        column = _column(cell=CellSpec(kind="count"))
        assert render_cell(column, {"f": 5}) == "5"

    def test_count_on_neither_defaults_to_zero(self) -> None:
        """Count on neither defaults to zero."""
        column = _column(cell=CellSpec(kind="count"))
        assert render_cell(column, {"f": "weird"}) == "0"

    def test_unknown_kind_degrades_to_text(self) -> None:
        """Design SS3.4: a manifest served by a newer schema version than this build.

        Degrades to `text`, never blank, never a crash.
        """
        column = _column(cell=CellSpec(kind="totally_unknown_future_kind"))
        assert render_cell(column, {"f": "raw-value"}) == "raw-value"
