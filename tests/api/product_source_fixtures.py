"""Vendored copies of what the portal reads out of a product's source tree.

Why this exists
===============
``gough_route_source`` and ``nest_route_source`` parse a product's real route
registrations off disk, which is what lets the strongest guards in this suite
— "does this allowlist rule point at a route the product actually serves?",
"does the product register any trailing-slash route?" — be graded by the
product rather than by the portal's own assumptions.

They defaulted to ``/home/penguin/code/{gough,nest}`` and skipped when that
path was absent. No workflow, Makefile target or script ever set
``$GOUGH_SOURCE_ROOT`` / ``$NEST_SOURCE_ROOT``, so on every machine except one
developer's laptop those guards skipped — including the two aimed squarely at
the phantom-route and trailing-slash defect classes that Phase 4G shipped. A
guard that only fires on one machine is how a rule aimed at a non-existent
route ships.

What this changes
=================
The parsed table is **vendored** into ``tests/api/fixtures/`` and committed.
Callers ask for the *effective* table:

* checkout present  → parse it live, and a separate test asserts the vendored
  copy still matches (so the fixture cannot rot silently);
* checkout absent   → use the vendored copy, so the guard still runs.

``make refresh-product-source-fixtures`` regenerates them. The freshness test
is what makes stale fixtures a red build rather than a quiet lie, and it runs
wherever a checkout exists — which is where a refresh is possible anyway.

Provenance and staleness
========================
A vendored table cannot detect its own rot: with no checkout there is nothing
to compare against, and the plausibility floors catch a TRUNCATED fixture, not
a stale one. So each fixture records where and when it came from — the product
checkout's commit sha and the generation date — and
:func:`fixture_age_days` lets a test fail once that exceeds a budget. That
turns "nobody has refreshed this since Nest rewrote its routes" from invisible
into a red build with the refresh command in the message.

It is a smoke alarm, not a proof: a fixture regenerated yesterday against a
checkout that was itself six months behind `main` looks fresh. The commit sha
is recorded so that case is at least diagnosable.

Expecting a checkout
====================
Some checks cannot be vendored at all: ``TestAgainstLiveNest`` executes Nest's
own Quart app, which needs Nest's dependencies installed, not just its source.
Those still skip — but setting ``REQUIRE_PRODUCT_SOURCE=1`` turns every such
skip into a failure, so a job that is *supposed* to have the checkouts reports
a missing one instead of quietly covering less than it claims.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

__all__ = [
    "FIXTURE_DIR",
    "MAX_FIXTURE_AGE_DAYS",
    "REQUIRE_SOURCE_ENV_VAR",
    "describe_mapping_drift",
    "describe_route_drift",
    "fixture_age_days",
    "fixture_path",
    "load_fixture",
    "method_map",
    "provenance",
    "source_required",
    "write_fixture",
]

#: Where the vendored copies live, resolved from this file so cwd is
#: irrelevant.
FIXTURE_DIR: Final[Path] = Path(__file__).resolve().parent / "fixtures"

#: Set to ``1`` in a job that is expected to have product checkouts. Turns a
#: "no checkout, skipping" into a failure.
REQUIRE_SOURCE_ENV_VAR: Final[str] = "REQUIRE_PRODUCT_SOURCE"

#: How long a vendored table may go unrefreshed before the suite says so.
#:
#: Six months is chosen to be a signal rather than a chore: it is long enough
#: that a normal quarter of work never trips it, and short enough that a table
#: nobody has looked at across two product release cycles stops being quietly
#: trusted. Raising it to silence a failure defeats the purpose — refresh the
#: fixture instead, which is one make target.
MAX_FIXTURE_AGE_DAYS: Final[int] = 180


def source_required() -> bool:
    """Whether a missing product checkout should fail rather than skip."""
    return os.environ.get(REQUIRE_SOURCE_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def fixture_path(name: str) -> Path:
    """Path of one vendored fixture by its stem."""
    return FIXTURE_DIR / f"{name}.json"


def load_fixture(name: str) -> dict[str, Any]:
    """Read a vendored fixture, failing loudly if it was never generated.

    An absent fixture is a repo-state error, not a reason to degrade to a
    skip: the whole point is that these checks run without a checkout.
    """
    path = fixture_path(name)
    if not path.is_file():
        raise FileNotFoundError(
            f"vendored source fixture {path} is missing. Regenerate it with "
            f"`make refresh-product-source-fixtures` from a machine that has "
            f"the product checkouts."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def write_fixture(name: str, payload: dict[str, Any]) -> Path:
    """Write one vendored fixture, sorted and newline-terminated.

    Sorted so a regeneration produces a reviewable diff rather than a
    reshuffle — a fixture whose diff is unreadable is one nobody checks.
    """
    path = fixture_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def provenance(root: Path) -> dict[str, str]:
    """Record where and when a fixture was generated from.

    The commit sha makes a stale-but-recently-regenerated fixture diagnosable
    rather than merely suspicious; the date is what :func:`fixture_age_days`
    reads. A checkout whose sha cannot be read (a tarball, a shallow export)
    still records the date — a partial provenance beats none, and the caller
    must not fail to generate a fixture over it.

    ``source_branch`` is recorded alongside the sha because the sha alone does
    not say whether a fixture was taken from a release line or from somebody's
    feature branch. Tobogganing's fixture was generated from
    ``feature/squawk-merger``, 17 commits ahead of ``release/v1.2.X``; a
    reviewer had to check out the product and diff the backing files to
    establish that those 17 commits touched none of them. Recording the branch
    turns that from re-derivation into reading one field.
    """
    generated = {
        "generated_on": date.today().isoformat(),
        "source_root": str(root),
    }
    for field, args in (
        ("source_commit", ["rev-parse", "HEAD"]),
        ("source_branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
    ):
        try:
            # S603/S607: argv is entirely literal (`git`, a fixed `-C`, and
            # one of two hardcoded rev-parse forms) plus a filesystem path
            # this function's own caller already resolved — no untrusted
            # input reaches it, and `check=False` means a missing `git`
            # binary is handled below rather than raising.
            result = subprocess.run(  # noqa: S603
                ["git", "-C", str(root), *args],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and result.stdout.strip():
            generated[field] = result.stdout.strip()
    return generated


def fixture_age_days(name: str) -> int | None:
    """Days since a fixture was generated, or ``None`` if it does not say.

    ``None`` is distinct from "fresh": a fixture predating provenance cannot
    be dated, and the caller decides whether that is a failure. It must not
    silently read as age zero.
    """
    raw = load_fixture(name).get("generated_on")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        generated = datetime.fromisoformat(raw).date()
    except ValueError:
        return None
    return (datetime.now(UTC).date() - generated).days


def method_map(raw: Any) -> dict[str, frozenset[str]]:
    """Rehydrate a ``{path: [methods]}`` mapping into frozensets.

    JSON has no set type, so the on-disk form is a sorted list; comparing a
    list against a ``frozenset`` would be false for every entry, which would
    look like total drift rather than a decoding bug.
    """
    if not isinstance(raw, dict):
        raise ValueError("route table fixture is not an object")
    return {
        str(path): frozenset(str(method) for method in methods) for path, methods in raw.items()
    }


def unmethod_map(table: dict[str, frozenset[str]]) -> dict[str, list[str]]:
    """Serialise a ``{path: frozenset}`` table for JSON."""
    return {path: sorted(methods) for path, methods in table.items()}


def describe_route_drift(
    vendored: Mapping[str, frozenset[str]], live: Mapping[str, frozenset[str]]
) -> str:
    """Render exactly what changed between a vendored route table and a live one.

    A bare ``assert vendored == live`` still fails loudly — pytest's own
    assertion rewriting diffs two dicts — but for a 100+-route table that diff
    is a wall of every shared key, not a short list of what moved. This
    computes the three ways a route table can drift (added, removed, method
    set changed) directly from the two tables being compared, so a failure
    message names the drifted paths instead of making the reader find them in
    a large dict repr. Nothing here is hand-maintained: the categories are
    derived from set/dict operations on whatever the two callers pass in, so
    it says the same thing for any future route regardless of what it is.

    Returns a description assuming the two tables already differ; callers
    should only reach for this after the equality check has failed.
    """
    vendored_paths, live_paths = set(vendored), set(live)
    added = sorted(live_paths - vendored_paths)
    removed = sorted(vendored_paths - live_paths)
    changed = sorted(path for path in vendored_paths & live_paths if vendored[path] != live[path])

    lines: list[str] = []
    if added:
        lines.append(f"  added ({len(added)}): {', '.join(added)}")
    if removed:
        lines.append(f"  removed ({len(removed)}): {', '.join(removed)}")
    for path in changed:
        lines.append(
            f"  methods changed on {path}: "
            f"vendored={sorted(vendored[path])} live={sorted(live[path])}"
        )
    if not lines:
        # The two tables compared unequal but no path-level difference was
        # found — this would only happen from a type mismatch on the values
        # (e.g. a caller passing lists instead of frozensets), which is a bug
        # in the caller, not in the product. Say so rather than emitting an
        # empty, contradictory "no differences" report.
        return (
            "  the tables compare unequal but no added/removed/changed path "
            "was found — check for a type mismatch between the two mappings "
            "passed to describe_route_drift (e.g. list vs frozenset methods)"
        )
    return "\n".join(lines)


def describe_mapping_drift(label: str, vendored: Mapping[str, str], live: Mapping[str, str]) -> str:
    """Same purpose as :func:`describe_route_drift`, for ``{key: str}`` tables.

    Nest's envelope keys (``{handler: key}``) and Tobogganing's auth/envelope
    tables (``{"METHOD /path": class}``) are string-valued rather than
    method-set-valued, so they need their own formatter rather than forcing a
    frozenset shape on data that was never one. ``label`` names what kind of
    key is being compared (``"handler"``, ``"route"``) so the report reads
    correctly for either table without the caller reformatting it.
    """
    vendored_keys, live_keys = set(vendored), set(live)
    added = sorted(live_keys - vendored_keys)
    removed = sorted(vendored_keys - live_keys)
    changed = sorted(key for key in vendored_keys & live_keys if vendored[key] != live[key])

    lines: list[str] = []
    if added:
        lines.append(f"  added {label}s ({len(added)}): {', '.join(added)}")
    if removed:
        lines.append(f"  removed {label}s ({len(removed)}): {', '.join(removed)}")
    for key in changed:
        lines.append(f"  {key} changed: vendored={vendored[key]!r} live={live[key]!r}")
    if not lines:
        return (
            f"  the {label} tables compare unequal but no added/removed/"
            f"changed {label} was found — check for a type mismatch"
        )
    return "\n".join(lines)
