#!/usr/bin/env python3
"""Gate line/statement and branch coverage as two independent dimensions.

coverage.py blends lines and branches into a single "Cover%" once branch
measurement is enabled (``--cov-branch``), so a bare ``--cov-fail-under``
would silently redefine what a threshold means instead of adding a second,
honest dimension -- see the "Backend coverage gate" step in
``.github/workflows/ci.yml`` for the measured numbers behind the two
floors below. Statement coverage IS line coverage in coverage.py; there is
no native "function" dimension (that is a jest/istanbul concept -- see
``services/webui/jest.config.js``'s ``coverageThreshold`` for the webui
side of that same four-dimension standard).

Run via CI only today; no ``make`` target yet (first use -- see
``general.md`` Repeatable Task Migration: a second call site is the trigger
to add one).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    """Parse a pytest-cov JSON report and gate two coverage dimensions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="pytest-cov --cov-report=json output")
    parser.add_argument("--min-lines", type=float, required=True)
    parser.add_argument("--min-branches", type=float, required=True)
    args = parser.parse_args()

    totals = json.loads(args.report.read_text())["totals"]

    line_pct = 100 * totals["covered_lines"] / totals["num_statements"]
    branch_pct = (
        100 * totals["covered_branches"] / totals["num_branches"]
        if totals["num_branches"]
        else 100.0
    )

    print(
        f"Line/statement coverage: {totals['covered_lines']}/"
        f"{totals['num_statements']} = {line_pct:.2f}%"
    )
    print(
        f"Branch coverage:         {totals['covered_branches']}/"
        f"{totals['num_branches']} = {branch_pct:.2f}%"
    )

    ok = True
    if line_pct < args.min_lines:
        print(f"FAIL: line coverage {line_pct:.2f}% below the {args.min_lines}% floor")
        ok = False
    if branch_pct < args.min_branches:
        print(f"FAIL: branch coverage {branch_pct:.2f}% below the {args.min_branches}% floor")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
