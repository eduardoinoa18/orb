"""Tests for auth hardening utilities — Module 4 S2."""

from __future__ import annotations

import time

import pytest
from integrations.auth_utils import (
    ApiKey,
    clear_failed_logins,
    generate_api_key,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    is_locked_out,
    record_failed_login,
    verify_api_key,
    verify_password,
    verify_totp,
    _lockout_store,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_returns_string(self):
        h = hash_password("hunter2")
        assert isinstance(h, str)
        assert len(h) > 20

    def test_hash_is_not_plaintext(self):
        assert hash_password("hunter2") != "hunter2"

    def test_verify_correct_password(self):
        h = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", h) is False

    def test_verify_bad_hash_returns_false(self):
        assert verify_password("anything", "not-a-bcrypt-hash") is False

    def test_two_hashes_differ(self):
        """Bcrypt salts each hash — same password yields different hashes."""
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2


# ---------------------------------------------------------------------------
# TOTP / MFA
# ---------------------------------------------------------------------------

class TestTOTP:

    def test_generate_secret_length(self):
        secret = generate_totp_secret()
        assert len(secret) >= 16

    def test_totp_uri_contains_email(self):
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "test@example.com")
        assert "test%40example.com" in uri or "test@example.com" in uri
        assert "otpauth://" in uri

    def test_verify_valid_code(self):
        import pyotp
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_verify_wrong_code(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_verify_empty_inputs(self):
        assert verify_totp("", "123456") is False
        assert verify_totp("ABCDEFGH", "") is False


# ---------------------------------------------------------------------------
# Brute-force / lockout
# ---------------------------------------------------------------------------

class TestBruteForce:

    def setup_method(self):
        """Clear lockout store between tests."""
        _lockout_store.clear()

    def test_not_locked_initially(self):
        assert is_locked_out("test@example.com") is False

    def test_locked_after_max_attempts(self):
        identifier = "attacker@evil.com"
        for _ in range(5):
            record_failed_login(identifier)
        assert is_locked_out(identifier) is True

    def test_attempts_remaining_decrements(self):
        identifier = "user@test.com"
        result = record_failed_login(identifier)
        assert result["attempts_remaining"] == 4

    def test_clear_removes_lockout(self):
        identifier = "unlock@test.com"
        for _ in range(5):
            record_failed_login(identifier)
        clear_failed_logins(identifier)
        assert is_locked_out(identifier) is False

    def test_lockout_result_structure(self):
        result = record_failed_login("any@test.com")
        assert "locked" in result
        assert "attempts_remaining" in result
        assert "locked_until_ts" in result


# ---------------------------------------------------------------------------
# API key generation + verification
# ---------------------------------------------------------------------------

class TestApiKey:

    def test_generate_returns_api_key(self):
        key = generate_api_key()
        assert isinstance(key, ApiKey)
        assert key.raw_key.startswith("orb_")
        assert len(key.key_hash) == 64  # SHA-256 hex

    def test_verify_correct_key(self):
        key = generate_api_key()
        assert verify_api_key(key.raw_key, key.key_hash) is True

    def test_verify_wrong_key(self):
        key = generate_api_key()
        assert verify_api_key("orb_wrong-key-value", key.key_hash) is False

    def test_verify_empty_inputs(self):
        assert verify_api_key("", "abc") is False
        assert verify_api_key("orb_key", "") is False

    def test_prefix_matches_start_of_raw_key(self):
        key = generate_api_key()
        assert key.raw_key.startswith(key.prefix)

    def test_two_keys_are_unique(self):
        k1 = generate_api_key()
        k2 = generate_api_key()
        assert k1.raw_key != k2.raw_key
        assert k1.key_hash != k2.key_hash
