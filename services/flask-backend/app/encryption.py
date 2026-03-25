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
        key = os.getenv("ENCRYPTION_KEY", "")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning(
                "ENCRYPTION_KEY not set — generated ephemeral key. "
                "Set ENCRYPTION_KEY env var for persistent encryption."
            )
        if isinstance(key, str):
            key = key.encode()
        _fernet_instance = Fernet(key)
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
        logger.error("Failed to decrypt value — invalid token or wrong key")
        raise ValueError("Decryption failed: invalid token or wrong encryption key")


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key for initial setup."""
    return Fernet.generate_key().decode()
