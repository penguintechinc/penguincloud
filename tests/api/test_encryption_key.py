"""Tests for encryption key requirement and TESTING mode.

Environment mutation goes through pytest's monkeypatch fixture rather than
hand-rolled save/restore: the previous `finally: os.environ.pop("TESTING")`
removed the variable unconditionally instead of restoring its prior value,
leaking a broken environment into every subsequently-collected module (any
later test touching encrypt_value got "ENCRYPTION_KEY environment variable
is required"). monkeypatch restores the exact prior state, including absence.
"""

import os
import sys
from collections.abc import Iterator

import pytest

# Add services/portal-api to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/portal-api"))


@pytest.fixture(autouse=True)
def reset_fernet() -> Iterator[None]:
    """Clear the cached Fernet instance either side of every test.

    _get_fernet() memoises, so a test that changes the key material must
    invalidate the cache going in and coming out, or it either reads a
    stale instance or leaves one behind for the next test.
    """
    from app import encryption

    encryption._fernet_instance = None
    yield
    encryption._fernet_instance = None


class TestEncryptionKeyRequirement:
    """Test encryption key handling."""

    def test_encryption_key_unset_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test unset ENCRYPTION_KEY raises RuntimeError."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        from app import encryption

        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY environment variable is required"):
            encryption._get_fernet()

    def test_encryption_key_testing_mode_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that TESTING=true allows encryption to work without ENCRYPTION_KEY."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("TESTING", "true")

        from app import encryption

        fernet = encryption._get_fernet()
        assert fernet is not None

        plaintext = "test secret"
        encrypted = encryption.encrypt_value(plaintext)
        assert encrypted != plaintext
        assert encryption.decrypt_value(encrypted) == plaintext

    def test_encryption_key_testing_mode_is_deterministic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test TESTING=true derives the same key across module reloads.

        Regression coverage for the brief's requirement that the TESTING-mode
        key be a fixed derived constant, not Fernet.generate_key() (which is
        random per call and would make ciphertext undecryptable across
        separate _get_fernet() re-initializations within the same process).
        """
        import importlib

        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("TESTING", "true")

        from app import encryption

        key_bytes_first = encryption._derive_testing_key()
        fernet_first = encryption._get_fernet()
        ciphertext = fernet_first.encrypt(b"deterministic-check")

        # Simulate a fresh module load (a new process would re-run the
        # module body from scratch) and re-initialize the instance.
        importlib.reload(encryption)
        encryption._fernet_instance = None
        key_bytes_second = encryption._derive_testing_key()
        fernet_second = encryption._get_fernet()

        assert key_bytes_first == key_bytes_second
        # A Fernet instance derived from the same key can decrypt ciphertext
        # produced by the "prior" instantiation.
        assert fernet_second.decrypt(ciphertext) == b"deterministic-check"

    def test_encryption_key_set_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that encryption works when ENCRYPTION_KEY is set."""
        from cryptography.fernet import Fernet

        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

        from app import encryption

        fernet = encryption._get_fernet()
        assert fernet is not None

        plaintext = "secure data"
        encrypted = encryption.encrypt_value(plaintext)
        assert encryption.decrypt_value(encrypted) == plaintext
