"""Tests for `pcli.auth.keyring_store.TokenStore`.

The headline case: no keyring backend AND no `PCLI_TOKEN` must refuse
outright, and must NEVER write anything to disk -- client.md's explicit
"NEVER use plaintext files for token storage" rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pcli.auth.keyring_store import TokenStore
from pcli.auth.tokens import TokenSet
from pcli.errors import KeyringUnavailableError


def _token() -> TokenSet:
    return TokenSet(
        access_token="at",  # noqa: S106
        refresh_token="rt",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        expires_at=9_999_999_999.0,
    )


def test_no_backend_no_env_token_refuses_on_load(
    no_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No backend no env token refuses on load."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    with pytest.raises(KeyringUnavailableError):
        store.load()


def test_no_backend_no_env_token_refuses_on_save(
    no_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No backend no env token refuses on save."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    with pytest.raises(KeyringUnavailableError):
        store.save(_token())


def test_no_backend_never_writes_a_plaintext_file(
    no_keyring_backend: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The falsification test: refusing must not be a "log and fall back to disk" path."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    store = TokenStore("portal.example.com")

    with pytest.raises(KeyringUnavailableError):
        store.save(_token())

    # Nothing pcli could plausibly have written landed anywhere under the
    # fake home directory -- no plaintext token file of any kind.
    written_files = list(tmp_path.rglob("*"))
    assert written_files == []


def test_pcli_token_env_bypasses_missing_backend(
    no_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PCLI_TOKEN` works even with zero keyring backend -- the headless/CI path."""
    monkeypatch.setenv("PCLI_TOKEN", "env-supplied-token")
    store = TokenStore("portal.example.com")
    loaded = store.load()
    assert loaded is not None
    assert loaded.access_token == "env-supplied-token"
    assert loaded.is_expired is False


def test_pcli_token_env_is_never_persisted(
    no_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`save()` is a no-op when PCLI_TOKEN is set -- never written to the keyring either."""
    monkeypatch.setenv("PCLI_TOKEN", "env-supplied-token")
    store = TokenStore("portal.example.com")
    store.save(_token())  # must not raise KeyringUnavailableError despite no backend


def test_save_and_load_round_trip_with_real_backend(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save and load round trip with real backend."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    assert store.load() is None

    store.save(_token())
    loaded = store.load()
    assert loaded is not None
    assert loaded.access_token == "at"


def test_clear_removes_stored_token(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clear removes stored token."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    store.save(_token())
    store.clear()
    assert store.load() is None


def test_clear_on_already_logged_out_host_is_a_noop(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clear on already logged out host is a noop."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store = TokenStore("portal.example.com")
    store.clear()  # nothing stored -- must not raise


def test_accounts_are_isolated_per_host(
    fake_keyring_backend: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accounts are isolated per host."""
    monkeypatch.delenv("PCLI_TOKEN", raising=False)
    store_a = TokenStore("a.example.com")
    store_b = TokenStore("b.example.com")
    store_a.save(_token())
    assert store_b.load() is None
