"""Regression coverage for the public-default SECRET_KEY defect.

The bug, precisely
===================
``app/config.py`` defaulted ``SECRET_KEY`` to the literal string
``"dev-secret-key-change-in-production"`` -- committed to this
repository's own source -- with nothing at startup checking whether an
operator had actually overridden it. Quart signs the session cookie
(itsdangerous) with ``SECRET_KEY``, and ``app/oauth.py``'s ``oauth_state``
CSRF check (``validate_state_token``) lives entirely inside that signed
session. A deployment left on the public default signs cookies with a key
anyone can read on GitHub, so an attacker can forge ``session["oauth_state"]``
client-side and defeat the CSRF check the OAuth callback relies on --
account-linking CSRF.

Same shape, same fix, as the ENCRYPTION_KEY defect
====================================================
``app/encryption.py``'s ``_get_fernet`` already refuses (``RuntimeError``)
to build a Fernet instance from an unset ``ENCRYPTION_KEY`` outside
``TESTING`` -- see ``test_encryption_key.py``. This module is the same
fix applied to ``SECRET_KEY``, checked eagerly in ``create_app()`` rather
than lazily on first use: every request touches the Quart session, so
there is no narrower "first real use" moment to defer the check to the
way ``_get_fernet`` defers to the first ``encrypt_value``/``decrypt_value``
call.
"""

from __future__ import annotations

import pytest
from app import create_app
from app.config import INSECURE_DEFAULT_SECRET_KEY, Config, TestingConfig


def _config_class(*, secret_key: str, testing: bool) -> type[TestingConfig]:
    """Build a fresh TestingConfig subclass with SECRET_KEY/TESTING overridden.

    Base is TestingConfig (not Config directly) purely for its SQLite
    DB_NAME wiring -- these tests never touch the database (the check runs
    before init_dal), but create_app() calls Config.get_db_uri()
    unconditionally, so a real, unique-per-process path is still needed.
    """

    class _Cfg(TestingConfig):
        SECRET_KEY = secret_key
        TESTING = testing

    return _Cfg


class TestSecretKeyStartupCheck:
    """The actual regression coverage: refuse to start, don't sign anyway."""

    def test_public_default_outside_testing_refuses_to_start(self) -> None:
        """The public placeholder SECRET_KEY refuses app creation outside TESTING."""
        cfg = _config_class(secret_key=INSECURE_DEFAULT_SECRET_KEY, testing=False)

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_error_message_names_the_oauth_csrf_consequence(self) -> None:
        """The refusal explains WHY, not just that it refused."""
        cfg = _config_class(secret_key=INSECURE_DEFAULT_SECRET_KEY, testing=False)

        with pytest.raises(RuntimeError) as exc_info:
            create_app(config_class=cfg)

        message = str(exc_info.value)
        assert "OAuth" in message
        assert "forgeable" in message

    def test_testing_mode_allows_the_public_default(self) -> None:
        """TESTING is the one carve-out -- mirrors ENCRYPTION_KEY's own."""
        cfg = _config_class(secret_key=INSECURE_DEFAULT_SECRET_KEY, testing=True)

        app = create_app(config_class=cfg)

        assert app.config["SECRET_KEY"] == INSECURE_DEFAULT_SECRET_KEY

    def test_real_secret_outside_testing_starts_fine(self) -> None:
        """A genuinely configured secret never trips the check."""
        # Test fixture value, not a real credential -- ruff's S106 pattern-
        # matches the PARAMETER NAME ("secret_key"), not the string's
        # content; tests/** already carries the identical S105/S107 carve-
        # out in pyproject.toml's per-file-ignores for this exact reason,
        # but that list does not include S106, so this call site gets its
        # own inline suppression rather than an edit to pyproject.toml
        # (owned by a sibling task right now).
        cfg = _config_class(secret_key="a-real-unpredictable-value-42", testing=False)  # noqa: S106

        app = create_app(config_class=cfg)

        assert app.config["SECRET_KEY"] == "a-real-unpredictable-value-42"


def test_sentinel_matches_the_documented_placeholder() -> None:
    """Pins the literal the startup check compares against.

    If app/config.py's os.getenv fallback ever changes without updating
    this constant in lockstep, the check silently stops firing for a
    freshly installed, unconfigured deployment -- exactly the case it
    exists to catch.
    """
    assert INSECURE_DEFAULT_SECRET_KEY == "dev-secret-key-change-in-production"


def test_jwt_secret_key_attribute_removed() -> None:
    """JWT_SECRET_KEY was dead config (HS256 scheme it backed no longer exists).

    Tokens are RS256, signed via penguin-aaa's keystore (see
    test_jwt_keystore.py) -- nothing in this codebase ever read
    JWT_SECRET_KEY. Left in place, it invited an operator to configure it
    believing it did something. Regression guard against it quietly
    coming back.
    """
    assert not hasattr(Config, "JWT_SECRET_KEY")
