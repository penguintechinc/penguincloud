"""Shared pytest fixtures for the pcli test suite.

Every test in this tree mocks HTTP (`httpx.MockTransport`, no real portal)
and keyring (`fake_keyring_backend`, no real OS credential store) -- see
client.md / this PR's own instructions: "Tests must mock the HTTP +
keyring (no live portal, no real keyring in CI)."
"""

from __future__ import annotations

from collections.abc import Iterator

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as FailKeyring


class InMemoryKeyring(KeyringBackend):
    """A real (non-`fail`) keyring backend backed by a plain dict, for tests.

    `priority` makes it `keyring`'s highest-priority backend once
    installed, so `keyring.get_keyring()` returns THIS instance rather than
    whatever the real OS backend chain would otherwise resolve to (which
    varies by CI runner / sandbox, and is exactly what
    `tests/auth/test_keyring_store.py` needs to NOT depend on).
    """

    priority = 999  # keyring types this as a class-level float; the base class is Any here anyway

    def __init__(self) -> None:
        """Start with no stored credentials."""
        super().__init__()  # type: ignore[no-untyped-call]  # KeyringBackend.__init__ is unstubbed
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        """Return the stored password, or None if nothing is stored."""
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a password."""
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        """Delete a stored password, raising like the real API on a miss."""
        try:
            del self._store[(service, username)]
        except KeyError as exc:
            raise keyring.errors.PasswordDeleteError from exc


@pytest.fixture
def fake_keyring_backend() -> Iterator[InMemoryKeyring]:
    """Install an in-memory keyring backend for the duration of one test."""
    backend = InMemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


@pytest.fixture
def no_keyring_backend() -> Iterator[FailKeyring]:
    """Install `keyring`'s own real no-op "fail" backend for one test.

    This is the ACTUAL class `pcli.auth.keyring_store.backend_available`
    pattern-matches on (`keyring.backends.fail`) -- a look-alike test
    double in a different module would silently defeat that check, so this
    installs the real thing rather than mimicking it.
    """
    backend = FailKeyring()  # type: ignore[no-untyped-call]  # keyring ships no py.typed marker
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)
