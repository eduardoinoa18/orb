"""ORB Secure Settings Store — Module 2, Step Z1.

All platform settings (API keys, credentials, preferences) are stored in
the ``platform_settings`` Supabase table with values encrypted at rest
using the EncryptionManager.

The ``platform_settings`` table schema (run in Supabase SQL editor):

    CREATE TABLE IF NOT EXISTS platform_settings (
        id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        key         text NOT NULL UNIQUE,
        value       text NOT NULL,           -- Fernet-encrypted
        description text DEFAULT '',
        category    text DEFAULT 'general',
        owner_id    text DEFAULT '',
        created_at  timestamptz DEFAULT now(),
        updated_at  timestamptz DEFAULT now()
    );

Usage:
    from app.database.settings_store import SettingsStore
    store = SettingsStore()
    store.save("anthropic_api_key", "sk-ant-xxx", category="ai")
    key = store.get("anthropic_api_key")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.encryption import get_encryption_manager

logger = logging.getLogger("orb.settings_store")

_TABLE = "platform_settings"


class SettingsStore:
    """Encrypted key-value store backed by Supabase ``platform_settings``."""

    def __init__(self) -> None:
        self._db = SupabaseService()
        self._em = get_encryption_manager()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        key: str,
        value: str,
        description: str = "",
        category: str = "general",
        owner_id: str = "",
    ) -> dict[str, Any]:
        """Encrypt and upsert a setting.

        If *key* already exists, the value is updated; otherwise a new row
        is inserted.  Returns the stored record (without the raw value).
        """
        if not self._em.is_encrypted(value):
            encrypted_value = self._em.encrypt(value)
        else:
            encrypted_value = value

        now = datetime.now(timezone.utc).isoformat()
        try:
            # Try update first
            existing = self._get_row(key)
            if existing:
                result = (
                    self._db.client.table(_TABLE)
                    .update({"value": encrypted_value, "updated_at": now})
                    .eq("key", key)
                    .execute()
                )
                row = (result.data or [existing])[0]
            else:
                result = (
                    self._db.client.table(_TABLE)
                    .insert({
                        "key": key,
                        "value": encrypted_value,
                        "description": description,
                        "category": category,
                        "owner_id": owner_id,
                        "created_at": now,
                        "updated_at": now,
                    })
                    .execute()
                )
                row = (result.data or [{}])[0]

            return {
                "key_name": key,
                "category": category,
                "saved": True,
                "id": row.get("id", ""),
            }
        except Exception as exc:
            logger.error("SettingsStore.save failed for key=%s: %s", key, exc)
            raise DatabaseConnectionError(f"Failed to save setting '{key}': {exc}") from exc

    def get(self, key: str, default: str = "") -> str:
        """Return the decrypted value for *key*, or *default* if not found."""
        row = self._get_row(key)
        if not row:
            return default
        try:
            return self._em.decrypt(row["value"])
        except Exception as exc:
            logger.error("SettingsStore.get decrypt failed for key=%s: %s", key, exc)
            return default

    def delete(self, key: str) -> bool:
        """Delete a setting by key.  Returns True if deleted, False if not found."""
        try:
            result = (
                self._db.client.table(_TABLE)
                .delete()
                .eq("key", key)
                .execute()
            )
            return bool(result.data)
        except Exception as exc:
            logger.error("SettingsStore.delete failed for key=%s: %s", key, exc)
            return False

    def list_settings(self, category: str = "") -> list[dict[str, Any]]:
        """Return all settings metadata (key, category, description — NOT values)."""
        try:
            query = self._db.client.table(_TABLE).select("id, key, category, description, owner_id, updated_at")
            if category:
                query = query.eq("category", category)
            result = query.order("category").order("key").execute()
            return result.data or []
        except Exception as exc:
            logger.warning("SettingsStore.list_settings failed: %s", exc)
            return []

    def test_connection_to_ai(self, key: str) -> dict[str, Any]:
        """Test that a stored API key can reach the target service.

        Only validates Anthropic keys for now; extension points for others.
        Returns: dict with keys: valid (bool), service (str), error (str|None)
        """
        value = self.get(key)
        if not value:
            return {"valid": False, "service": key, "error": "Key not found"}

        if "anthropic" in key.lower() or value.startswith("sk-ant"):
            return self._test_anthropic(value)

        # For unknown services, just confirm the key is present
        return {"valid": True, "service": key, "error": None, "note": "Presence verified only"}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_row(self, key: str) -> dict[str, Any] | None:
        """Return the raw DB row for *key*, or None."""
        try:
            result = (
                self._db.client.table(_TABLE)
                .select("*")
                .eq("key", key)
                .limit(1)
                .execute()
            )
            data = result.data or []
            return data[0] if data else None
        except Exception:
            return None

    @staticmethod
    def _test_anthropic(api_key: str) -> dict[str, Any]:
        """Ping the Anthropic API with a minimal request."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {
                "valid": True,
                "service": "anthropic",
                "model": "claude-3-haiku-20240307",
                "error": None,
            }
        except Exception as exc:
            return {"valid": False, "service": "anthropic", "error": str(exc)[:200]}
