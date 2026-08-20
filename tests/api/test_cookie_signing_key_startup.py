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

Round-1 review finding addressed here (C1, Critical)
=====================================================
The original check was a single ``!=`` against ONE literal.
:class:`TestPublishedDefaultEvasions` reproduces every evasion the
reviewer demonstrated live against that code -- each one STARTED, signing
ACTIVE, with the app reporting nothing wrong:

* ``"dev-secret-key-change-in-production "`` (one trailing space)
* ``"change-me-in-production"`` (docker-compose.yml's OWN former
  fallback for this same variable -- this fix's docker-compose.yml edit,
  in the very same commit, would otherwise have stranded every developer
  who already had that value in their ``.env``/shell on a still-published
  key while the guard reported green)
* ``"   "`` (whitespace-only)
* ``""`` (empty)

Run any of these tests against the round-1 checkout and they fail red --
the app starts without raising.
"""

from __future__ import annotations

import pytest
from app import create_app
from app.config import (
    INSECURE_DEFAULT_SECRET_KEY,
    MIN_SECRET_KEY_LENGTH,
    Config,
    TestingConfig,
)

#: A fixture value clearly over MIN_SECRET_KEY_LENGTH and not a real
#: credential -- see the noqa: S106 note at its call sites for why ruff
#: flags the PARAMETER NAME here, not the string's content.
_REAL_SECRET = "a-real-unpredictable-secret-value-1234567890"


def _config_class(*, secret_key: str, testing: bool = False) -> type[TestingConfig]:
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
        cfg = _config_class(secret_key=INSECURE_DEFAULT_SECRET_KEY)

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_error_message_names_the_oauth_csrf_consequence(self) -> None:
        """The refusal explains WHY, not just that it refused."""
        cfg = _config_class(secret_key=INSECURE_DEFAULT_SECRET_KEY)

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
        cfg = _config_class(secret_key=_REAL_SECRET)  # noqa: S106

        app = create_app(config_class=cfg)

        assert app.config["SECRET_KEY"] == _REAL_SECRET


class TestPublishedDefaultEvasions:
    """Round-1 C1: every evasion the reviewer proved lets signing start ACTIVE.

    Each ``test_*`` here is independently red against the round-1 checkout
    (single ``!=`` against one literal) -- ``pytest.raises`` fails with
    "DID NOT RAISE RuntimeError" for every one of them, because that
    checkout's ``create_app()`` returns a live app instead.
    """

    def test_trailing_space_around_the_published_default_refuses(self) -> None:
        """A single trailing space -- what a .env line/YAML scalar produces routinely."""
        cfg = _config_class(secret_key=f"{INSECURE_DEFAULT_SECRET_KEY} ")

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_leading_and_trailing_whitespace_refuses(self) -> None:
        """Whitespace on both sides, including a tab/newline mix."""
        cfg = _config_class(secret_key=f"\t {INSECURE_DEFAULT_SECRET_KEY}\n ")

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_docker_composes_former_fallback_value_refuses(self) -> None:
        """The value "change-me-in-production" -- docker-compose.yml's OWN former default.

        This fix's own docker-compose.yml edit removes that fallback in
        the SAME commit that added the (originally single-literal) guard
        -- without denylisting this value too, every developer who
        already had it set would have been stranded on a published key
        while the guard reported green.
        """
        cfg = _config_class(secret_key="change-me-in-production")  # noqa: S106

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_whitespace_only_refuses(self) -> None:
        """Whitespace-only -- not equal to the denylisted literal, but not a secret either."""
        cfg = _config_class(secret_key="   ")  # noqa: S106

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_empty_string_refuses(self) -> None:
        """Empty string -- Quart would otherwise silently disable session signing."""
        cfg = _config_class(secret_key="")  # noqa: S106

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_trivially_short_value_refuses(self) -> None:
        """A short value that was never published anywhere still isn't a secret."""
        cfg = _config_class(secret_key="admin")  # noqa: S106

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_value_one_char_under_the_floor_refuses(self) -> None:
        """Exactly MIN_SECRET_KEY_LENGTH - 1 characters -- the floor's own boundary."""
        cfg = _config_class(secret_key="x" * (MIN_SECRET_KEY_LENGTH - 1))  # noqa: S106

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(config_class=cfg)

    def test_value_exactly_at_the_floor_is_accepted(self) -> None:
        """Exactly MIN_SECRET_KEY_LENGTH characters -- the floor's other boundary."""
        cfg = _config_class(secret_key="x" * MIN_SECRET_KEY_LENGTH)  # noqa: S106

        app = create_app(config_class=cfg)

        assert app.config["SECRET_KEY"] == "x" * MIN_SECRET_KEY_LENGTH


def test_sentinel_matches_the_documented_placeholder() -> None:
    """Pins the literal the startup check denylists.

    If app/config.py's os.getenv fallback ever changes without updating
    this constant in lockstep, the check silently stops firing for a
    freshly installed, unconfigured deployment -- exactly the case it
    exists to catch.
    """
    assert INSECURE_DEFAULT_SECRET_KEY == "dev-secret-key-change-in-production"


def test_denylist_covers_both_published_defaults() -> None:
    """Round-1 C1: the denylist is a SET, not a single sentinel.

    Regression guard against re-narrowing this back to one value --
    docker-compose.yml's former fallback ("change-me-in-production") must
    stay covered even though it is not app/config.py's own default.
    """
    from app.config import PUBLISHED_INSECURE_SECRET_KEY_VALUES

    assert INSECURE_DEFAULT_SECRET_KEY in PUBLISHED_INSECURE_SECRET_KEY_VALUES
    assert "change-me-in-production" in PUBLISHED_INSECURE_SECRET_KEY_VALUES


def test_jwt_secret_key_attribute_removed() -> None:
    """JWT_SECRET_KEY was dead config (HS256 scheme it backed no longer exists).

    Tokens are RS256, signed via penguin-aaa's keystore (see
    test_jwt_keystore.py) -- nothing in this codebase ever read
    JWT_SECRET_KEY. Left in place, it invited an operator to configure it
    believing it did something. Regression guard against it quietly
    coming back.
    """
    assert not hasattr(Config, "JWT_SECRET_KEY")
