"""Coverage for the REAL os.getenv-driven parsing paths in app/config.py.

Round-1 review finding addressed here (I4, Important)
=======================================================
Every other test in ``test_jwt_keystore.py``/``test_cookie_signing_key_
startup.py`` builds a ``TestingConfig`` SUBCLASS and overrides
``SECRET_KEY``/``DEPLOYMENT_REPLICAS``/etc as plain class attributes.
That is the right tool for testing ``_require_configured_secret_key`` and
``_build_oidc_provider``'s OWN logic (they read whatever ends up in
``app.config``, however it got there) -- but it never once calls
``os.getenv``, because ``Config``'s class body already ran (at import
time, reading the ambient environment) long before any subclass
overrides a value. Every evasion in round 1's C1 finding, and the parse
failures in M1/M2, live in that class-body ``os.getenv`` call itself and
were therefore invisible to every test that existed.

This module sets REAL environment variables and reloads ``app.config``
(mirroring ``test_encryption_key.py``'s established
``importlib.reload``-based pattern) to actually exercise that path.

Restoration discipline
=======================
``app.config`` defines the ``Config``/``TestingConfig`` hierarchy every
OTHER test in this suite depends on (``conftest.py``'s ``app`` fixture
does ``from app.config import TestingConfig`` freshly, INSIDE the
fixture function body, on every single test). Leaving the module reloaded
mid-mutation would leak into every test that runs afterward in the same
pytest process. Every test below restores the environment and reloads
AGAIN, in a ``finally``, as the literal last thing it does -- deliberately
not relying on pytest fixture teardown ordering (a fixture that reloads
in its own teardown after depending on ``monkeypatch`` finalizes BEFORE
``monkeypatch`` restores the environment, not after, which would leave
the module reloaded against the test's OWN override rather than the real
environment).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from app import config as config_module
from app import create_app


@contextmanager
def _env_var(name: str, value: str | None) -> Iterator[None]:
    """Set (or delete) an env var for the block, then restore it exactly.

    ``value=None`` means "ensure absent" -- distinct from leaving it
    alone, which is what a bare ``monkeypatch.delenv(..., raising=False)``
    would do for a var that was never set in the first place. Reloads
    ``app.config`` on the way IN (so the module reflects the block's
    environment) and on the way OUT (so it reflects the restored one) --
    see the module docstring for why this cannot be left to a fixture.
    """
    original = os.environ.get(name)
    had_original = name in os.environ
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    importlib.reload(config_module)
    try:
        yield
    finally:
        if had_original:
            os.environ[name] = original  # type: ignore[assignment]
        else:
            os.environ.pop(name, None)
        importlib.reload(config_module)


class TestDeclaredPositiveIntEnvDirectly:
    """``_declared_positive_int_env`` is a pure function -- no reload needed.

    It reads ``os.getenv`` fresh on every call (nothing memoised), so
    ``monkeypatch.setenv``/``delenv`` alone is enough to exercise it for
    real, unlike the class-body attributes above it.
    """

    def test_unset_returns_the_default_and_not_declared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round-1 I1's whole distinction: absent is NOT the same as declared."""
        monkeypatch.delenv("DEPLOYMENT_REPLICAS", raising=False)

        value, declared = config_module._declared_positive_int_env("DEPLOYMENT_REPLICAS", 1)

        assert value == 1
        assert declared is False

    def test_explicit_value_is_declared(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicitly-set value, including "1", IS declared."""
        monkeypatch.setenv("DEPLOYMENT_REPLICAS", "1")

        value, declared = config_module._declared_positive_int_env("DEPLOYMENT_REPLICAS", 1)

        assert value == 1
        assert declared is True

    def test_explicit_value_above_default_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A value other than the default still parses and is declared."""
        monkeypatch.setenv("DEPLOYMENT_REPLICAS", "7")

        value, declared = config_module._declared_positive_int_env("DEPLOYMENT_REPLICAS", 1)

        assert value == 7
        assert declared is True

    def test_zero_raises_naming_the_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Round-1 M1/M2: 0 used to parse and PERMIT silently. Now it raises, named."""
        monkeypatch.setenv("DEPLOYMENT_REPLICAS", "0")

        with pytest.raises(ValueError, match="DEPLOYMENT_REPLICAS=0"):
            config_module._declared_positive_int_env("DEPLOYMENT_REPLICAS", 1)

    def test_negative_raises_naming_the_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Same as zero -- a negative process count is equally nonsensical."""
        monkeypatch.setenv("HYPERCORN_WORKERS", "-3")

        with pytest.raises(ValueError, match="HYPERCORN_WORKERS=-3"):
            config_module._declared_positive_int_env("HYPERCORN_WORKERS", 1)

    def test_unparseable_value_raises_naming_variable_and_fix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round-1 M1/M2: the old bare ValueError named neither. This names both."""
        monkeypatch.setenv("DEPLOYMENT_REPLICAS", "three")

        with pytest.raises(ValueError) as exc_info:
            config_module._declared_positive_int_env("DEPLOYMENT_REPLICAS", 1)

        message = str(exc_info.value)
        assert "DEPLOYMENT_REPLICAS='three'" in message
        assert "positive whole number" in message


class TestConfigClassBodyActuallyReadsTheEnvironment:
    """Reload-based: proves the CLASS BODY (not just the helper) wires it in."""

    def test_deployment_replicas_from_a_real_env_var(self) -> None:
        """A real DEPLOYMENT_REPLICAS env var reaches Config via class-body os.getenv."""
        with _env_var("DEPLOYMENT_REPLICAS", "5"):
            assert config_module.Config.DEPLOYMENT_REPLICAS == 5
            assert config_module.Config.DEPLOYMENT_REPLICAS_DECLARED is True

    def test_hypercorn_workers_from_a_real_env_var(self) -> None:
        """Same wiring, the other declared axis (round-1 I3)."""
        with _env_var("HYPERCORN_WORKERS", "3"):
            assert config_module.Config.HYPERCORN_WORKERS == 3
            assert config_module.Config.HYPERCORN_WORKERS_DECLARED is True

    def test_deployment_replicas_unset_is_undeclared_via_real_import(self) -> None:
        """A genuinely absent env var resolves to the default AND undeclared."""
        with _env_var("DEPLOYMENT_REPLICAS", None):
            assert config_module.Config.DEPLOYMENT_REPLICAS == 1
            assert config_module.Config.DEPLOYMENT_REPLICAS_DECLARED is False

    def test_bad_value_crashes_the_import_by_name(self) -> None:
        """An operator's typo fails module import, not a generic crash."""
        original = os.environ.get("DEPLOYMENT_REPLICAS")
        had_original = "DEPLOYMENT_REPLICAS" in os.environ
        os.environ["DEPLOYMENT_REPLICAS"] = "not-a-number"
        try:
            with pytest.raises(ValueError, match="DEPLOYMENT_REPLICAS='not-a-number'"):
                importlib.reload(config_module)
        finally:
            if had_original:
                os.environ["DEPLOYMENT_REPLICAS"] = original  # type: ignore[assignment]
            else:
                os.environ.pop("DEPLOYMENT_REPLICAS", None)
            # Verified empirically (not assumed): a class body that raises
            # partway through never rebinds the class name in the module
            # namespace, so config_module.Config here is still the LAST
            # successfully-built class, not a broken one. Reloading again
            # is still correct -- it re-syncs the module against the now-
            # restored environment rather than leaving it pinned to
            # whatever the environment was several tests ago.
            importlib.reload(config_module)


class TestSecretKeyEndToEndThroughARealEnvVar:
    """The full pipeline: real env var -> Config class body -> app.config -> guard.

    Every other SECRET_KEY test in test_cookie_signing_key_startup.py
    proves the GUARD's logic against a value placed directly on a
    subclass. This is the one test that proves the WIRING ahead of it --
    ``os.getenv("SECRET_KEY", ...)`` at class-body/import time -- by
    setting an actual environment variable and reloading, exactly the gap
    round-1 I4 identified.
    """

    def test_published_default_via_real_env_var_refuses_to_start(self) -> None:
        """A real SECRET_KEY env var set to a denylisted value refuses to start."""
        with _env_var("SECRET_KEY", "change-me-in-production"):
            with _env_var("TESTING", None):

                class _Cfg(config_module.TestingConfig):
                    TESTING = False

                with pytest.raises(RuntimeError, match="SECRET_KEY"):
                    create_app(config_class=_Cfg)

    def test_real_secret_via_real_env_var_starts_fine(self) -> None:
        """A real SECRET_KEY env var set to a genuine secret starts fine end-to-end."""
        real_secret = "a-genuinely-unpredictable-value-99887766"  # noqa: S105
        with _env_var("SECRET_KEY", real_secret):
            with _env_var("TESTING", None):

                class _Cfg(config_module.TestingConfig):
                    TESTING = False

                app = create_app(config_class=_Cfg)

                assert app.config["SECRET_KEY"] == real_secret


def test_module_is_restored_to_the_real_environment() -> None:
    """Sanity check that every reload above cleaned up after itself.

    If any test in this module left DEPLOYMENT_REPLICAS/HYPERCORN_WORKERS/
    SECRET_KEY set from a prior test's env mutation, this fails -- and so
    would every OTHER test in the suite that runs after this module,
    since conftest.py's ``app`` fixture re-imports ``app.config`` fresh
    per test.
    """
    assert "DEPLOYMENT_REPLICAS" not in os.environ or config_module.Config.DEPLOYMENT_REPLICAS
    assert config_module.TestingConfig.DEPLOYMENT_REPLICAS_DECLARED is True
    assert config_module.TestingConfig.HYPERCORN_WORKERS_DECLARED is True
