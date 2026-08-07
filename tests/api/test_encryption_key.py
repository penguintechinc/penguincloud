"""Tests for encryption key requirement and TESTING mode."""

import os
import sys
import pytest

# Add services/flask-backend to path so we can import app
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/flask-backend")
)


class TestEncryptionKeyRequirement:
    """Test encryption key handling."""

    def test_encryption_key_unset_raises_error(self) -> None:
        """Test unset ENCRYPTION_KEY raises RuntimeError."""
        saved_encryption_key = os.environ.pop("ENCRYPTION_KEY", None)
        saved_testing = os.environ.pop("TESTING", None)

        try:
            # Reset the fernet instance to force re-initialization
            from app import encryption

            encryption._fernet_instance = None

            # This should raise RuntimeError
            with pytest.raises(
                RuntimeError, match="ENCRYPTION_KEY environment variable is required"
            ):
                encryption._get_fernet()
        finally:
            # Restore environment
            if saved_encryption_key:
                os.environ["ENCRYPTION_KEY"] = saved_encryption_key
            if saved_testing:
                os.environ["TESTING"] = saved_testing
            # Reset fernet for other tests
            from app import encryption

            encryption._fernet_instance = None

    def test_encryption_key_testing_mode_works(self) -> None:
        """Test that TESTING=true allows encryption to work without ENCRYPTION_KEY."""
        # Save and clear ENCRYPTION_KEY
        saved_encryption_key = os.environ.pop("ENCRYPTION_KEY", None)
        os.environ["TESTING"] = "true"

        try:
            # Reset the fernet instance
            from app import encryption

            encryption._fernet_instance = None

            # This should not raise
            fernet = encryption._get_fernet()
            assert fernet is not None

            # Test encryption/decryption works
            plaintext = "test secret"
            encrypted = encryption.encrypt_value(plaintext)
            assert encrypted != plaintext
            decrypted = encryption.decrypt_value(encrypted)
            assert decrypted == plaintext
        finally:
            # Restore environment
            if saved_encryption_key:
                os.environ["ENCRYPTION_KEY"] = saved_encryption_key
            os.environ.pop("TESTING", None)
            # Reset fernet for other tests
            from app import encryption

            encryption._fernet_instance = None

    def test_encryption_key_set_works(self) -> None:
        """Test that encryption works when ENCRYPTION_KEY is set."""
        from cryptography.fernet import Fernet

        # Generate a valid key
        test_key = Fernet.generate_key().decode()
        saved_encryption_key = os.environ.get("ENCRYPTION_KEY")

        os.environ["ENCRYPTION_KEY"] = test_key

        try:
            # Reset the fernet instance
            from app import encryption

            encryption._fernet_instance = None

            # Should work
            fernet = encryption._get_fernet()
            assert fernet is not None

            # Test encryption/decryption
            plaintext = "secure data"
            encrypted = encryption.encrypt_value(plaintext)
            decrypted = encryption.decrypt_value(encrypted)
            assert decrypted == plaintext
        finally:
            # Restore environment
            if saved_encryption_key:
                os.environ["ENCRYPTION_KEY"] = saved_encryption_key
            else:
                os.environ.pop("ENCRYPTION_KEY", None)
            # Reset fernet for other tests
            from app import encryption

            encryption._fernet_instance = None
