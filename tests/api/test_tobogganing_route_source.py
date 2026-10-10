"""Unit tests for ``tobogganing_route_source._boot``'s module-failure handling.

2026-08-20: a live Tobogganing boot with an incomplete dependency set (the
portal's isolated venv missing ``markdown``/``bleach``, which
``hub_api/requirements.txt`` declares but nothing installs into that venv)
still exited 0 and produced a route table short by exactly the
``sase`` module's nine routes — because ``hub_api/app.py`` wraps its
per-module import in a bare ``try/except (ImportError, AttributeError):
logger.error(...)`` and carries on. That is indistinguishable, from the
route table alone, from Tobogganing genuinely dropping those routes; see
``tests/api/README-tobogganing-fixtures.md`` for the full account.

``_boot`` now derives the registered module set from the live
``app.registry`` and raises :class:`tobogganing_route_source.
ModuleRegistrationError` when it disagrees with ``hub_api.modules.__all__``,
instead of returning a route table that looks like ordinary drift. These
tests prove that path fires — entirely via a monkeypatched subprocess, so
they run without a Tobogganing checkout and without depending on Tobogganing
ever actually breaking again.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import tobogganing_route_source as t


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A directory that satisfies ``tobogganing_app_module``'s existence check.

    ``_boot`` only inspects this path to decide "checkout present or not" —
    the actual boot is stubbed via ``subprocess.run``, so the file's content
    is never read.
    """
    (tmp_path / "hub_api").mkdir()
    (tmp_path / "hub_api" / "app.py").write_text("# stub for tobogganing_app_module()\n")
    return tmp_path


def _fake_completed(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["stub"], returncode=0, stdout=json.dumps(payload), stderr=""
    )


_ONE_RULE = [
    {
        "rule": "/api/v1/ping",
        "methods": ["GET"],
        "endpoint": "ping",
        "auth": "none",
        "decorators": [],
        "strict_slashes": True,
        "envelope": None,
    }
]


class TestBootModuleFailures:
    """A boot that exits 0 can still be an incomplete environment."""

    def test_a_reported_module_failure_raises_module_registration_error(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-empty ``module_failures`` must not read as a route diff."""
        payload = {
            "rules": _ONE_RULE,
            "module_failures": {
                "sase": "import failed: ModuleNotFoundError: No module named 'bleach'"
            },
        }
        monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_completed(payload))

        with pytest.raises(t.ModuleRegistrationError) as excinfo:
            t._boot(fake_root)

        message = str(excinfo.value)
        assert "sase" in message
        assert "bleach" in message
        assert "INCOMPLETE" in message
        # A ModuleRegistrationError must still satisfy every existing
        # `except BootError` fallback (effective_route_table() and friends).
        assert isinstance(excinfo.value, t.BootError)

    def test_no_module_failures_returns_the_rules_unwrapped(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ordinary, everything-registered case is unaffected."""
        payload = {"rules": _ONE_RULE, "module_failures": {}}
        monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_completed(payload))

        assert t._boot(fake_root) == _ONE_RULE

    def test_a_payload_with_no_module_failures_key_is_treated_as_none_failed(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Older-shaped payloads (pre-dating this field) must not crash.

        Absence, not an empty object, is what a boot program that has not
        been regenerated yet would produce.
        """
        payload = {"rules": _ONE_RULE}
        monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_completed(payload))

        assert t._boot(fake_root) == _ONE_RULE

    def test_boot_failure_reports_the_module_registration_message(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``boot_failure()`` must surface this failure mode too.

        It is what the pytest freshness tests call to decide skip-vs-fail —
        if it only recognised a hard boot crash, a partial environment would
        go back to silently skipping instead of failing under
        ``REQUIRE_PRODUCT_SOURCE=1``.
        """
        payload = {
            "rules": [],
            "module_failures": {"sase": "import failed: X"},
        }
        monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_completed(payload))

        reason = t.boot_failure(fake_root)

        assert reason is not None
        assert "sase" in reason

    def test_a_non_dict_module_failures_value_is_rejected(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed boot program change must fail loudly.

        Not silently pass an unusable value through to a caller expecting a
        mapping.
        """
        payload = {"rules": _ONE_RULE, "module_failures": ["not", "a", "dict"]}
        monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_completed(payload))

        with pytest.raises(t.BootError, match="module_failures"):
            t._boot(fake_root)

    def test_a_bare_list_payload_shape_is_rejected(
        self, fake_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller still running the older bare-list boot program must fail clearly.

        Not raise a silent ``TypeError`` from indexing a list with a string
        key.
        """
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=["stub"], returncode=0, stdout=json.dumps(_ONE_RULE), stderr=""
            ),
        )

        with pytest.raises(t.BootError, match="did not return the expected"):
            t._boot(fake_root)
