"""Encryption utilities for secure storage of API keys and secrets."""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet_instance = None


def _get_fernet() -> Fernet:
    """Get or create Fernet encryption instance."""
    global _fernet_instance
    if _fernet_instance is None:
        key_str = os.getenv("ENCRYPTION_KEY", "")
        if not key_str:
            # Allow test-only key when TESTING=true
            if os.getenv("TESTING", "").lower() == "true":
                key_str = Fernet.generate_key().decode()
                logger.info("TESTING mode: using generated test key")
            else:
                msg = "ENCRYPTION_KEY environment variable is required"
                raise RuntimeError(msg)
        key_bytes: bytes
        if isinstance(key_str, str):
            key_bytes = key_str.encode()
        else:
            key_bytes = key_str
        _fernet_instance = Fernet(key_bytes)
    return _fernet_instance


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return base64-encoded ciphertext."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext string and return plaintext."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or key")
        msg = "Decryption failed: invalid token or wrong encryption key"
        raise ValueError(msg)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key for initial setup."""
    return Fernet.generate_key().decode()
