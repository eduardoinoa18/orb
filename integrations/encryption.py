"""ORB Encryption Layer — Module 4, Step S1.

All API keys and sensitive settings are encrypted at rest using
Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).  The key
is derived from ENCRYPTION_SECRET in .env — never stored in code.

Usage:
    from integrations.encryption import get_encryption_manager
    em = get_encryption_manager()
    cipher  = em.encrypt("sk-ant-my-key")
    plain   = em.decrypt(cipher)   # back to "sk-ant-my-key"
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("orb.encryption")


class EncryptionError(RuntimeError):
    """Raised when encryption or decryption fails."""


class EncryptionManager:
    """Fernet-based symmetric encryption for ORB sensitive settings.

    The encryption key is derived from ENCRYPTION_SECRET in .env.
    If the secret is already a valid Fernet key it is used directly;
    otherwise it is hashed to create a 32-byte key and then
    base64url-encoded to satisfy Fernet's format requirement.
    """

    def __init__(self, secret: str) -> None:
        if not secret or not secret.strip():
            raise EncryptionError(
                "ENCRYPTION_SECRET is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        self._fernet = self._build_fernet(secret.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext string.  Returns a URL-safe encoded cipher string."""
        if not isinstance(value, str):
            raise EncryptionError(f"encrypt() expects str, got {type(value).__name__}")
        try:
            token = self._fernet.encrypt(value.encode("utf-8"))
            return token.decode("utf-8")
        except Exception as exc:
            raise EncryptionError(f"Encryption failed: {exc}") from exc

    def decrypt(self, encrypted: str) -> str:
        """Decrypt an encrypted string back to plaintext.

        Never returns the raw encrypted bytes.
        Raises EncryptionError on tampered or wrong-key data.
        """
        if not isinstance(encrypted, str):
            raise EncryptionError(f"decrypt() expects str, got {type(encrypted).__name__}")
        try:
            plain = self._fernet.decrypt(encrypted.encode("utf-8"))
            return plain.decode("utf-8")
        except InvalidToken as exc:
            raise EncryptionError(
                "Decryption failed — wrong key or tampered data."
            ) from exc
        except Exception as exc:
            raise EncryptionError(f"Decryption failed: {exc}") from exc

    def encrypt_dict(self, data: dict[str, Any]) -> dict[str, str]:
        """Encrypt every value in a dict.  Keys are preserved as-is.

        Useful for bulk settings encryption before storage.
        Only string values are encrypted; others are JSON-stringified first.
        """
        result: dict[str, str] = {}
        for key, value in data.items():
            raw = value if isinstance(value, str) else str(value)
            result[key] = self.encrypt(raw)
        return result

    def is_encrypted(self, value: str) -> bool:
        """Return True if *value* looks like a Fernet token.

        Prevents accidental double-encryption when saving settings.
        """
        if not isinstance(value, str):
            return False
        # Fernet tokens are base64url strings that start with 'gAAA'
        return value.startswith("gAAA") and len(value) > 50

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fernet(secret: str) -> Fernet:
        """Accept either a raw Fernet key or any string secret."""
        # If the secret is already a valid 44-char base64url Fernet key,
        # use it directly.
        try:
            raw = base64.urlsafe_b64decode(secret + "==")
            if len(raw) == 32:
                return Fernet(secret.encode("utf-8"))
        except Exception:
            pass

        # Otherwise derive a 32-byte key from the secret via SHA-256.
        key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(fernet_key)


@lru_cache(maxsize=1)
def get_encryption_manager() -> EncryptionManager:
    """Return a cached singleton EncryptionManager.

    Reads ENCRYPTION_SECRET from settings on first call.
    Import-safe: does not crash if the secret is missing until first use.
    """
    from config.settings import get_settings
    settings = get_settings()
    secret = getattr(settings, "encryption_secret", "") or ""
    return EncryptionManager(secret)
