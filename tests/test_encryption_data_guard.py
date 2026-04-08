"""Tests for integrations/encryption.py and integrations/data_guard.py — Module 4 S1."""

from __future__ import annotations

import pytest
from integrations.encryption import EncryptionError, EncryptionManager, get_encryption_manager
from integrations.data_guard import DataGuard, get_data_guard


# ---------------------------------------------------------------------------
# EncryptionManager
# ---------------------------------------------------------------------------

FAKE_SECRET = "test-encryption-secret-for-tests-only"


class TestEncryptionManager:
    def test_encrypt_returns_string(self):
        em = EncryptionManager(FAKE_SECRET)
        cipher = em.encrypt("hello-world")
        assert isinstance(cipher, str)
        assert cipher != "hello-world"

    def test_roundtrip(self):
        em = EncryptionManager(FAKE_SECRET)
        original = "sk-ant-my-secret-api-key-1234"
        assert em.decrypt(em.encrypt(original)) == original

    def test_is_encrypted_true(self):
        em = EncryptionManager(FAKE_SECRET)
        cipher = em.encrypt("some-value")
        assert em.is_encrypted(cipher) is True

    def test_is_encrypted_false_for_plain(self):
        em = EncryptionManager(FAKE_SECRET)
        assert em.is_encrypted("sk-ant-plain-value") is False

    def test_is_encrypted_false_for_short(self):
        em = EncryptionManager(FAKE_SECRET)
        assert em.is_encrypted("gAAA") is False

    def test_encrypt_dict(self):
        em = EncryptionManager(FAKE_SECRET)
        data = {"key_a": "value_a", "key_b": "value_b"}
        encrypted = em.encrypt_dict(data)
        assert set(encrypted.keys()) == {"key_a", "key_b"}
        assert encrypted["key_a"] != "value_a"
        assert em.decrypt(encrypted["key_a"]) == "value_a"

    def test_decrypt_wrong_key_raises(self):
        em1 = EncryptionManager(FAKE_SECRET)
        em2 = EncryptionManager("completely-different-secret")
        cipher = em1.encrypt("data")
        with pytest.raises(EncryptionError):
            em2.decrypt(cipher)

    def test_decrypt_garbage_raises(self):
        em = EncryptionManager(FAKE_SECRET)
        with pytest.raises(EncryptionError):
            em.decrypt("not-a-real-fernet-token")

    def test_encrypt_non_string_raises(self):
        em = EncryptionManager(FAKE_SECRET)
        with pytest.raises(EncryptionError):
            em.encrypt(12345)  # type: ignore

    def test_empty_secret_raises(self):
        with pytest.raises(EncryptionError):
            EncryptionManager("")

    def test_whitespace_secret_raises(self):
        with pytest.raises(EncryptionError):
            EncryptionManager("   ")

    def test_valid_fernet_key_used_directly(self):
        """A real 44-char Fernet key should be used as-is."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        em = EncryptionManager(key)
        assert em.decrypt(em.encrypt("check")) == "check"

    def test_different_ciphers_for_same_plaintext(self):
        """Fernet uses a random IV so each encrypt call produces a distinct token."""
        em = EncryptionManager(FAKE_SECRET)
        c1 = em.encrypt("same-value")
        c2 = em.encrypt("same-value")
        assert c1 != c2

    def test_encrypt_dict_non_string_values(self):
        em = EncryptionManager(FAKE_SECRET)
        data = {"num": 42, "flag": True}
        encrypted = em.encrypt_dict(data)
        assert em.decrypt(encrypted["num"]) == "42"
        assert em.decrypt(encrypted["flag"]) == "True"


class TestGetEncryptionManagerSingleton:
    def test_singleton_returns_same_instance(self):
        a = get_encryption_manager()
        b = get_encryption_manager()
        assert a is b


# ---------------------------------------------------------------------------
# DataGuard
# ---------------------------------------------------------------------------

class TestDataGuard:
    def test_redact_openai_key(self):
        guard = DataGuard()
        text = "My key is sk-abc123defghijklmnopqrstuvwxyz1234"
        result = guard.redact(text)
        assert "sk-abc" not in result
        assert "[REDACTED]" in result

    def test_redact_anthropic_key(self):
        guard = DataGuard()
        text = "Use sk-ant-api03-verylongkeyhere12345678901234567890"
        result = guard.redact(text)
        assert "sk-ant" not in result

    def test_redact_password_pattern(self):
        guard = DataGuard()
        text = "password=hunter2 and username=admin"
        result = guard.redact(text)
        assert "hunter2" not in result

    def test_redact_card_number(self):
        guard = DataGuard()
        text = "Card: 4111-1111-1111-1111"
        result = guard.redact(text)
        assert "4111" not in result

    def test_safe_to_log_clean_text(self):
        guard = DataGuard()
        assert guard.is_safe_to_log("Rex generated 5 leads today") is True

    def test_not_safe_to_log_with_key(self):
        guard = DataGuard()
        text = "key is sk-ant-api03-longkeyhere1234567890abcdefgh"
        assert guard.is_safe_to_log(text) is False

    def test_safe_for_log_clean_passthrough(self):
        guard = DataGuard()
        msg = "Briefing sent to owner at 7:00 AM"
        assert guard.safe_for_log(msg) == msg

    def test_safe_for_log_redacts_if_needed(self):
        guard = DataGuard()
        text = "secret=my-very-sensitive-value"
        result = guard.safe_for_log(text)
        assert "my-very-sensitive-value" not in result
        assert "[REDACTED]" in result

    def test_scan_finds_pattern(self):
        guard = DataGuard()
        text = "token=abcdefghij1234"
        findings = guard.scan_for_sensitive(text)
        assert isinstance(findings, list)

    def test_non_string_input_safe(self):
        guard = DataGuard()
        assert guard.is_safe_to_log(None) is True
        assert guard.redact(None) is None  # type: ignore

    def test_get_data_guard_singleton(self):
        a = get_data_guard()
        b = get_data_guard()
        assert a is b
