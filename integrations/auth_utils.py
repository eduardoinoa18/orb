"""ORB Auth Hardening — Module 4, Step S2.

Provides:
- bcrypt password hashing via passlib
- TOTP/MFA via pyotp (RFC 6238)
- Brute-force / account-lockout protection (in-memory, stateless)
- API key generation and verification (hashed storage, prefix display)

All functions are pure utilities — no HTTP dependencies — so they can be
imported by routes, tests, or CLI scripts with no side effects.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import pyotp

logger = logging.getLogger("orb.auth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_ATTEMPTS = 5          # login failures before lockout
_LOCKOUT_SECONDS = 900     # 15-minute lockout window
_API_KEY_PREFIX_LENGTH = 8  # chars shown to user (e.g. "orb_k1ab")
_PBKDF2_ITERATIONS = 600_000
_PBKDF2_PREFIX = "pbkdf2_sha256"


# ---------------------------------------------------------------------------
# Password hashing (bcrypt via passlib)
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash *plain* with bcrypt using a cost factor of 12.

    Returns a 60-char string safe to store in the database.
    Never store the plaintext password.
    """
    try:
        ctx = _get_crypt_context()
        return ctx.hash(plain)
    except Exception as exc:
        logger.warning("Falling back to PBKDF2 password hashing: %s", exc)
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* value.

    Uses a constant-time comparison internally to prevent timing attacks.
    """
    try:
        if hashed.startswith(f"{_PBKDF2_PREFIX}$"):
            return _verify_pbkdf2_password(plain, hashed)
        ctx = _get_crypt_context()
        return ctx.verify(plain, hashed)
    except Exception as exc:
        logger.warning("verify_password error: %s", exc)
        return False


@lru_cache(maxsize=1)
def _get_crypt_context():
    """Cached CryptContext — building the bcrypt context is expensive."""
    from passlib.context import CryptContext
    return CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def _verify_pbkdf2_password(plain: str, hashed: str) -> bool:
    """Verify stdlib PBKDF2 fallback hashes."""
    try:
        _, iterations_str, salt_b64, digest_b64 = hashed.split("$", 3)
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        computed = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(computed, expected)
    except Exception as exc:
        logger.warning("verify_pbkdf2_password error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# TOTP / MFA (RFC 6238 via pyotp)
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a new 32-char base32 TOTP secret for a user.

    Store this in the database (encrypted) and show the QR once to the user.
    """
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "ORB Platform") -> str:
    """Return an otpauth:// URI for QR code display in the setup wizard."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP *code* against the stored *secret*.

    Accepts codes valid within +/- 30 seconds (1 window) to allow for
    slight clock drift.  Returns False on any error.
    """
    if not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except Exception as exc:
        logger.warning("verify_totp error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Brute-force / account lockout
# ---------------------------------------------------------------------------

@dataclass
class _LockoutRecord:
    attempts: int = 0
    first_attempt_ts: float = field(default_factory=time.time)
    locked_until: float = 0.0


# In-memory store.  For multi-process deployments replace with Redis.
_lockout_store: dict[str, _LockoutRecord] = defaultdict(_LockoutRecord)


def record_failed_login(identifier: str) -> dict[str, Any]:
    """Record a failed auth attempt for *identifier* (email or IP).

    Returns a dict with: locked (bool), attempts_remaining (int),
    locked_until_ts (float | None).
    """
    record = _lockout_store[identifier]
    now = time.time()

    # Reset the window if the oldest attempt is older than the lockout period
    if now - record.first_attempt_ts > _LOCKOUT_SECONDS:
        record.attempts = 0
        record.first_attempt_ts = now
        record.locked_until = 0.0

    record.attempts += 1

    if record.attempts >= _MAX_ATTEMPTS:
        record.locked_until = now + _LOCKOUT_SECONDS
        return {
            "locked": True,
            "attempts_remaining": 0,
            "locked_until_ts": record.locked_until,
        }

    return {
        "locked": False,
        "attempts_remaining": max(0, _MAX_ATTEMPTS - record.attempts),
        "locked_until_ts": None,
    }


def is_locked_out(identifier: str) -> bool:
    """Return True if *identifier* is currently locked out."""
    record = _lockout_store.get(identifier)
    if not record:
        return False
    return time.time() < record.locked_until


def clear_failed_logins(identifier: str) -> None:
    """Clear lockout on successful authentication."""
    _lockout_store.pop(identifier, None)


# ---------------------------------------------------------------------------
# API key generation + verification
# ---------------------------------------------------------------------------

@dataclass
class ApiKey:
    """Represents a newly created API key.

    raw_key    — the full key, shown ONCE to the owner (never stored)
    prefix     — first N chars, stored and shown for identification
    key_hash   — SHA-256 hex digest, stored in DB for verification
    """
    raw_key: str
    prefix: str
    key_hash: str


def generate_api_key() -> ApiKey:
    """Generate a cryptographically secure API key.

    Format: ``orb_`` + 40 random hex chars = e.g. ``orb_a3f7c...``
    Store only (prefix, key_hash) in the database.
    Show raw_key once to the user, then discard.
    """
    token = secrets.token_hex(20)
    raw = f"orb_{token}"
    prefix = raw[:_API_KEY_PREFIX_LENGTH]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return ApiKey(raw_key=raw, prefix=prefix, key_hash=key_hash)


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Return True if *raw_key* hashes to *stored_hash*.

    Uses hmac.compare_digest for constant-time comparison.
    """
    if not raw_key or not stored_hash:
        return False
    computed = hashlib.sha256(raw_key.encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)
