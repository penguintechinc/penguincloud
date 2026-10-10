"""Unit tests for the vendored-fixture drift-reporting helpers.

``describe_route_drift`` and ``describe_mapping_drift`` are what turns a bare
``assert vendored == live`` into a failure message naming the exact routes
that drifted (see :mod:`tests.api.product_source_fixtures`). They are pure
functions over plain dicts, so they are tested directly here rather than only
indirectly through a real product boot/parse — this is what proves the
"name the fixture and the drifted routes" behaviour without needing a Gough,
Nest or Tobogganing checkout on the machine running the suite.
"""

from __future__ import annotations

from product_source_fixtures import describe_mapping_drift, describe_route_drift


class TestDescribeRouteDrift:
    """Route tables are ``{path: frozenset[str] of methods}``."""

    def test_reports_added_removed_and_changed_separately(self) -> None:
        """Each category is named on its own line, and unchanged paths are silent."""
        vendored = {
            "/a": frozenset({"GET"}),
            "/b": frozenset({"GET"}),
            "/c": frozenset({"GET"}),
        }
        live = {
            "/a": frozenset({"GET", "POST"}),  # changed
            "/c": frozenset({"GET"}),  # unchanged
            "/d": frozenset({"GET"}),  # added
        }
        # "/b" removed

        report = describe_route_drift(vendored, live)

        assert "added (1): /d" in report
        assert "removed (1): /b" in report
        assert "methods changed on /a" in report
        assert "vendored=['GET']" in report
        assert "live=['GET', 'POST']" in report
        # Unchanged paths must not be mentioned at all.
        assert "/c" not in report

    def test_only_additions_omits_the_other_two_sections(self) -> None:
        """No 'removed'/'changed' text at all when nothing was removed or changed."""
        vendored: dict[str, frozenset[str]] = {}
        live = {"/new": frozenset({"GET"})}

        report = describe_route_drift(vendored, live)

        assert "added (1): /new" in report
        assert "removed" not in report
        assert "changed" not in report

    def test_equal_tables_report_a_type_mismatch_rather_than_lying_empty(self) -> None:
        """Callers only reach for this after `==` already failed.

        If the tables are nonetheless path-for-path identical here, the
        original inequality must have come from something `set`/`dict`
        operations over these tables cannot see (e.g. one side using a plain
        ``list`` of methods instead of a ``frozenset``) — say that plainly
        instead of reporting "no differences", which would read as the
        assertion itself being wrong rather than the caller's data shape.
        """
        same = {"/a": frozenset({"GET"})}

        report = describe_route_drift(same, same)

        assert "type mismatch" in report


class TestDescribeMappingDrift:
    """String-valued tables: Nest's envelope keys, Tobogganing's auth map."""

    def test_reports_added_removed_and_changed_with_the_given_label(self) -> None:
        """The ``label`` argument names the key kind in every line, not just one."""
        vendored = {"list_a": "items", "list_b": "policies"}
        live = {"list_a": "resources", "list_c": "pools"}

        report = describe_mapping_drift("handler", vendored, live)

        assert "added handlers (1): list_c" in report
        assert "removed handlers (1): list_b" in report
        assert "list_a changed: vendored='items' live='resources'" in report

    def test_equal_tables_report_a_type_mismatch_rather_than_lying_empty(self) -> None:
        """Same contract as the route-table version, for string-valued tables."""
        same = {"GET /a": "user"}

        report = describe_mapping_drift("route", same, same)

        assert "type mismatch" in report
