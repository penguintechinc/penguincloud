#!/usr/bin/env python3
"""Regenerate the vendored product-source fixtures under ``tests/api/fixtures``.

The route tables and collection-envelope keys the portal's strongest guards are
graded against are parsed out of Gough's and Nest's own source trees. Those
parsers used to skip wherever a checkout was absent, which was every machine but
one — so the guards aimed at the phantom-route and trailing-slash defect classes
never ran in CI.

The tables are therefore committed, and the suite falls back to them when no
checkout is present. This script produces them. Run it from a machine that has
the checkouts (or point ``$GOUGH_SOURCE_ROOT`` / ``$NEST_SOURCE_ROOT`` /
``$TOBOGGANING_SOURCE_ROOT`` at them) whenever a product's routes change:

    make refresh-product-source-fixtures

A fixture that drifts from the product is caught by
``test_gough_route_drift.py``, ``test_nest_source_fixture.py`` and
``test_tobogganing_source_fixture.py``, which compare the committed copy
against a live parse wherever a checkout exists.

Tobogganing is refreshed by BOOTING the product rather than parsing it — its
final paths are assembled at runtime by a module registry, so no static parse
is exact. See :mod:`tests.api.tobogganing_route_source`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_API = Path(__file__).resolve().parents[1] / "tests" / "api"
sys.path.insert(0, str(_TESTS_API))

import gough_route_source  # noqa: E402
import nest_route_source  # noqa: E402
import tobogganing_route_source  # noqa: E402


def _refresh(label: str, present: object, refresh: object) -> int:
    """Regenerate one product's fixture, reporting what happened.

    Returns the number of failures (0 or 1) rather than raising, so one
    missing checkout does not stop the other product being refreshed.
    """
    if present is None:
        print(f"[SKIP] {label}: no checkout found — fixture left unchanged")
        return 1
    path = refresh()  # type: ignore[operator]
    print(f"[OK]   {label}: wrote {path}")
    return 0


def main() -> int:
    """Refresh every vendored fixture, returning a shell exit code."""
    failures = _refresh(
        "gough",
        gough_route_source.gough_app_root(),
        gough_route_source.refresh_fixture,
    )
    failures += _refresh(
        "nest",
        nest_route_source.nest_api_module(),
        nest_route_source.refresh_fixture,
    )
    failures += _refresh(
        "tobogganing",
        tobogganing_route_source.tobogganing_app_module(),
        tobogganing_route_source.refresh_fixture,
    )
    if failures:
        print(
            "\nOne or more checkouts were missing. Set $GOUGH_SOURCE_ROOT / "
            "$NEST_SOURCE_ROOT / $TOBOGGANING_SOURCE_ROOT, or run this from a "
            "machine that has them.",
            file=sys.stderr,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
