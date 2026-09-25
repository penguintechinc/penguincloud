"""Prove the layer-boundary guard actually detects a violation.

Phase 8, §11.2's last acceptance criterion, and Verification Integrity's
"a gate that cannot fail is not a gate": ``test_layer_boundaries.py`` was
only manually injection-proven during development (its own module
docstring, Section C: "a deliberately introduced sideways import was run
through this exact assertion and produced a red failure naming it, before
being reverted"). That proof was never captured as a standing test — if
someone later breaks :func:`test_layer_boundaries._real_violations` into a
no-op (e.g. drops the ``_RANK`` comparison, or the ``violations.add(...)``
call), every test in that file keeps passing, because passing is exactly
what "found nothing" looks like whether or not anything was there to find.

This module closes that gap **without reimplementing the guard's
detection logic** — it imports and calls the guard's own
:func:`test_layer_boundaries._real_violations`, :data:`LAYER_OF`, and
:data:`test_layer_boundaries._APP_ROOT` directly, the same functions
:func:`test_layer_boundaries.test_no_illegal_layer_imports` gates on. Only
the *input* is synthetic (a throwaway ``app/`` tree under ``tmp_path``,
substituted in for the real ``services/portal-api/app`` via
``monkeypatch.setattr``) — the algorithm under test is the real one. If
someone neuters the real detector, these two tests go red exactly like the
real gate would, because they call the same code path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import test_layer_boundaries as _guard
from test_layer_boundaries import LAYER_OF, _real_violations


def _write_module(root: Path, dotted_leaf: str, body: str) -> None:
    """Write ``root/{dotted_leaf}.py`` with ``body``, creating ``root`` first."""
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{dotted_leaf}.py").write_text(body, encoding="utf-8")


def test_guard_flags_synthetic_illegal_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Feeding the real detector a synthetic upward edge must report it.

    A fake ``floor``-layer module imports a fake ``routes``-layer module
    (rank 0 importing rank 4, the steepest possible violation) via a
    deferred import inside a function body -- the same shape
    :func:`test_layer_boundaries._imports_in` was built to catch (see that
    module's docstring, point 2) rather than a module-scope import, which
    would exercise less of the real AST walk. This calls
    :func:`test_layer_boundaries._real_violations` itself, not a
    reimplementation -- a no-op detector fails this assertion.
    """
    app_root = tmp_path / "app"
    _write_module(
        app_root,
        "fake_floor_leaf",
        "def do_thing() -> None:\n"
        "    from app.fake_routes_leaf import MARK  # deferred, upward -- illegal\n"
        "    return MARK\n",
    )
    _write_module(app_root, "fake_routes_leaf", "MARK = 1\n")

    monkeypatch.setattr(_guard, "_APP_ROOT", app_root)
    monkeypatch.setitem(LAYER_OF, "fake_floor_leaf", "floor")
    monkeypatch.setitem(LAYER_OF, "fake_routes_leaf", "routes")

    found = _real_violations()

    assert ("app.fake_floor_leaf", "app.fake_routes_leaf", "floor", "routes") in found, (
        "the real guard failed to flag a deliberately injected floor->routes "
        f"edge in a synthetic tree; found={found!r}"
    )


def test_guard_is_clean_on_synthetic_legal_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same real detector must NOT flag a downward, legal edge.

    A fake ``routes``-layer module importing a fake ``floor``-layer module
    (rank 4 -> rank 0, strictly downward, healthy) at module scope. Proves
    the other direction: a detector that flags everything indiscriminately
    (or was neutered into "always violation") is exactly as broken as one
    that never flags anything, and this test alone would catch the
    false-positive failure mode that :func:`test_guard_flags_synthetic_illegal_edge`
    cannot.
    """
    app_root = tmp_path / "app"
    _write_module(app_root, "fake_floor_ok", "VALUE = 1\n")
    _write_module(app_root, "fake_routes_ok", "from app.fake_floor_ok import VALUE\n")

    monkeypatch.setattr(_guard, "_APP_ROOT", app_root)
    monkeypatch.setitem(LAYER_OF, "fake_floor_ok", "floor")
    monkeypatch.setitem(LAYER_OF, "fake_routes_ok", "routes")

    found = _real_violations()

    assert found == set(), (
        f"the real guard flagged a legal, strictly-downward synthetic edge as a "
        f"violation (false positive): {found!r}"
    )
