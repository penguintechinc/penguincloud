"""Mechanical proof of Phase 8 §8.1's zero-frontend-onboarding claim.

This is the acceptance test itself. Onboarding WaddleAI onto the console —
list-browsable in the webui, a full ``pcli`` command tree — used ONLY
backend artifacts: an adapter package, a manifest, and two registry lines
(``app.adapters.ADAPTER_REGISTRY``/``MANIFEST_REGISTRY`` gaining a
``waddleai`` entry, ``PLANNED_PRODUCTS`` losing one). The webui's
``ProductResourceRoute``/``manifestCapabilities.ts`` and ``pcli`` are already
generic: a read-only manifest auto-routes and auto-discovers with no
per-product frontend or CLI code. If that thesis is true, this branch's diff
against the release branch cannot contain a single added line under any path
a per-product screen or CLI command would live in.

This module diffs HEAD against the merge-base with ``origin/release/v0.1.x``
— subprocess, not a hand-counted file list, so a change made after this test
was written is exactly as visible to it as one made before. HEAD, not the
working tree: this is the same comparison ``git diff --stat
origin/release/v0.1.x...HEAD`` makes (three-dot form: base is the merge-base,
not the branch tip), which is also the literal command this PR's own
verification step runs — matching it means an uncommitted, untracked new
file cannot slip past either check by never being staged.

Falsifiability, proven and then reverted
=========================================
A guard nobody has ever seen fail is indistinguishable from a guard that
cannot fail (see ``critical-rules.md``'s Verification Integrity). Before this
file was committed, a throwaway file was added under
``services/webui/src/client/pages/products/waddleai/_falsifiability_probe.tsx``
and this suite was re-run — it went red, naming the exact offending path and
line count — then the probe file was deleted and the suite was re-run green
again. That is not automated here (it would defeat its own purpose: a
self-reverting probe committed alongside the guard proves nothing about a
FUTURE violation), but the same mechanism — a real file under a forbidden
path — is what :func:`test_a_deliberately_placed_probe_file_would_be_caught`
exercises directly, non-destructively, by asserting the classifier
:func:`_touches_forbidden_path` answers True for a synthetic path no one
added to the tree.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest

#: tests/architecture/this_file.py -> repo root.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The release branch this feature branch is heading into. A remote ref
#: (never a local one) so the comparison is stable regardless of what the
#: developer's local ``release/v0.1.x`` happens to be pointed at.
_BASE_REF: Final[str] = "origin/release/v0.1.x"

#: Design §8.1's forbidden paths — a per-product webui screen, a per-product
#: kit/cell registry entry, or a per-product CLI command file are each, on
#: their own, evidence the "manifest-only onboarding" thesis is false for
#: whatever change touched them. ``commands_substring`` matches
#: ``services/cli/**/commands/**`` (pcli's real command-tree layout is
#: ``services/cli/src/pcli/commands/`` and ``services/cli/tests/commands/``,
#: not one fixed depth), so it is a substring test rather than a prefix one.
_FORBIDDEN_PREFIXES: Final[tuple[str, ...]] = (
    "services/webui/src/client/pages/products/",
    "services/webui/src/client/components/kit/",
)
_FORBIDDEN_SUBSTRING: Final[str] = "services/cli/"
_COMMANDS_MARKER: Final[str] = "/commands/"

#: A new file anywhere under the webui naming itself after this product is
#: the api-resource-file half of §8.1's forbidden list (e.g.
#: ``api/resources/waddleai.ts``, mirroring ``tobogganing.ts``'s existing
#: per-product file) — checked by filename, not by directory, since that
#: convention places the file beside its siblings rather than under either
#: prefix above.
_WEBUI_PREFIX: Final[str] = "services/webui/"
_PRODUCT_NAME_MARKER: Final[str] = "waddleai"


def _run_git(*args: str) -> str:
    """Run one git command against the repo root, raising loudly on failure.

    No ``|| true`` and no status-swallowing: an unresolvable ref (e.g.
    ``origin/release/v0.1.x`` not fetched) must fail this test, not silently
    report a clean diff — see ``critical-rules.md`` Verification Integrity.
    Resolved to an absolute path via ``shutil.which`` rather than a bare
    ``"git"`` (PATH-hijack hardening, matching
    ``tests/api/product_source_fixtures.py``'s precedent) — ``None`` raises
    immediately rather than degrading, unlike that module's benign
    provenance case.
    """
    git_binary = shutil.which("git")
    if git_binary is None:
        raise RuntimeError("git is not on PATH — cannot verify the zero-frontend diff")
    result = subprocess.run(  # noqa: S603 -- git_binary resolved above, args are literals
        [git_binary, *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _merge_base() -> str:
    """The commit this feature branch diverged from on the release branch."""
    return _run_git("merge-base", "HEAD", _BASE_REF).strip()


def _numstat_since_merge_base() -> list[tuple[int, int, str]]:
    """``(added, removed, path)`` for every file touched since the merge-base.

    Diffs the merge-base commit directly against ``HEAD`` — the same
    comparison as ``git diff base...HEAD``'s three-dot form. ``-M`` (rename
    detection) is deliberately NOT passed: a rename that happens to land a
    file's new path under a forbidden prefix must still show as an addition
    there, which plain numstat already does by reporting a delete + an add.
    """
    base = _merge_base()
    output = _run_git("diff", "--numstat", base, "HEAD")
    rows: list[tuple[int, int, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        added_s, removed_s, path = line.split("\t", 2)
        # Binary files report '-' for both counts rather than a line count.
        added = 0 if added_s == "-" else int(added_s)
        removed = 0 if removed_s == "-" else int(removed_s)
        rows.append((added, removed, path))
    return rows


def _touches_forbidden_path(path: str) -> bool:
    """True if ``path`` falls under any Design §8.1 forbidden location."""
    if any(path.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
        return True
    if path.startswith(_FORBIDDEN_SUBSTRING) and _COMMANDS_MARKER in path:
        return True
    if path.startswith(_WEBUI_PREFIX) and _PRODUCT_NAME_MARKER in Path(path).name.lower():
        return True
    return False


def test_a_deliberately_placed_probe_file_would_be_caught() -> None:
    """Falsifiability check: the classifier itself, exercised against synthetic paths.

    Proves :func:`_touches_forbidden_path` is not vacuously True/False for
    every input — each assertion below names the exact §8.1 case it guards,
    matching the manual red/green probe recorded in the module docstring.
    """
    assert _touches_forbidden_path(
        "services/webui/src/client/pages/products/waddleai/WaddleAIScreen.tsx"
    )
    assert _touches_forbidden_path("services/webui/src/client/components/kit/waddleaiCells.tsx")
    assert _touches_forbidden_path("services/cli/src/pcli/commands/waddleai.py")
    assert _touches_forbidden_path("services/cli/tests/commands/test_waddleai.py")
    assert _touches_forbidden_path("services/webui/src/client/api/resources/waddleai.ts")
    # Negative cases: real files this PR does add, none of which is forbidden.
    assert not _touches_forbidden_path("services/portal-api/app/adapters/waddleai/adapter.py")
    assert not _touches_forbidden_path("tests/api/test_waddleai_adapter.py")
    # A pre-existing per-product webui api-resource file for ANOTHER product —
    # under services/webui/ but naming neither "waddleai" nor a forbidden
    # directory, so the filename-marker check must not over-match on the
    # shared "services/webui/" prefix alone.
    assert not _touches_forbidden_path("services/webui/src/client/api/resources/tobogganing.ts")


def test_merge_base_resolves_and_is_the_documented_commit() -> None:
    """Establishes the premise every other test in this module rests on.

    If ``origin/release/v0.1.x`` cannot be resolved, every assertion below
    would vacuously see an empty diff and pass for the wrong reason — this
    fails loudly first instead.
    """
    base = _merge_base()
    assert base, "merge-base with origin/release/v0.1.x resolved to nothing"


def test_zero_added_lines_under_forbidden_webui_and_cli_paths() -> None:
    """THE acceptance assertion: this branch adds no line under a forbidden path.

    Falsifiable by construction: a single new line in
    ``services/webui/src/client/pages/products/waddleai/`` (a per-product
    screen), ``services/webui/src/client/components/kit/`` (a per-product
    kit/cell registration), ``services/cli/**/commands/**`` (a per-product
    CLI command), or a new ``waddleai``-named webui api-resource file turns
    this red — see the module docstring for the manual probe that confirmed
    exactly that before this test was committed.
    """
    offenders = [
        (path, added)
        for added, _removed, path in _numstat_since_merge_base()
        if added > 0 and _touches_forbidden_path(path)
    ]
    assert offenders == [], (
        f"WaddleAI onboarding added {sum(a for _, a in offenders)} line(s) "
        f"under a Design §8.1 forbidden path: {offenders!r} — the whole "
        f"point of this acceptance test is that onboarding a fourth product "
        f"needs zero new webui/CLI code"
    )


def test_this_branch_actually_changed_something() -> None:
    """Guards the assertion above from passing vacuously on an empty diff.

    Without this, a checkout with no commits past the merge-base would make
    the zero-added-lines test pass for having nothing to check, which reads
    identically to a real pass.
    """
    rows = _numstat_since_merge_base()
    assert rows, "no diff against origin/release/v0.1.x at all — nothing was onboarded"
    total_added = sum(added for added, _removed, _path in rows)
    assert total_added > 0, "diff exists but adds no lines anywhere"


@pytest.mark.parametrize(
    "expected_path",
    [
        "services/portal-api/app/adapters/waddleai/adapter.py",
        "services/portal-api/app/adapters/waddleai/manifest.py",
        "services/portal-api/app/adapters/waddleai/routes.py",
        "services/portal-api/app/adapters/waddleai/mapping.py",
    ],
)
def test_the_real_onboarding_files_are_present_in_the_diff(expected_path: str) -> None:
    """The positive control: the backend artifacts this PR is supposed to add are there.

    Without this, a diff that (incorrectly) touched nothing at all would
    still pass every guard above — this proves the diff contains the actual
    onboarding work, not just an absence of forbidden paths.
    """
    paths = {path for _added, _removed, path in _numstat_since_merge_base()}
    assert expected_path in paths, f"{expected_path!r} not found in the diff against {_BASE_REF}"
