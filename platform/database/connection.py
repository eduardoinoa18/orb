"""Supabase connection helper for ORB Level 1.

This module provides one shared database client (singleton) and simple CRUD
helpers so route files and agent modules do not repeat low-level DB logic.
"""

from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from config.settings import get_settings


class SupabaseClient:
    """Singleton wrapper around the Supabase Python client."""

    _instance: "SupabaseClient | None" = None
    _client: Client | None = None

    def __new__(cls) -> "SupabaseClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self) -> Client:
        """Returns an active Supabase client, creating it once if needed."""
        if self._client is None:
            settings = get_settings()
            try:
                self._client = create_client(
                    settings.supabase_url,
                    settings.supabase_service_key,
                )
            except Exception as error:
                raise RuntimeError(f"Failed to connect to Supabase: {error}") from error
        return self._client

    def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """Inserts one row and returns the created record if available."""
        try:
            response = self.get_client().table(table).insert(data).execute()
            rows = response.data or []
            return rows[0] if rows else data
        except Exception as error:
            raise RuntimeError(f"Insert failed for table '{table}': {error}") from error

    def select(self, table: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Reads rows with optional equality filters."""
        try:
            query = self.get_client().table(table).select("*")
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            response = query.execute()
            return response.data or []
        except Exception as error:
            raise RuntimeError(f"Select failed for table '{table}': {error}") from error

    def update(self, table: str, row_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Updates one row by id and returns the updated record when possible."""
        try:
            response = self.get_client().table(table).update(data).eq("id", row_id).execute()
            rows = response.data or []
            return rows[0] if rows else {"id": row_id, **data}
        except Exception as error:
            raise RuntimeError(f"Update failed for table '{table}' id='{row_id}': {error}") from error

    def delete(self, table: str, row_id: str) -> bool:
        """Deletes one row by id and returns True when no exception occurs."""
        try:
            self.get_client().table(table).delete().eq("id", row_id).execute()
            return True
        except Exception as error:
            raise RuntimeError(f"Delete failed for table '{table}' id='{row_id}': {error}") from error

    def log_activity(
        self,
        agent_id: str | None,
        owner_id: str | None,
        action_type: str,
        description: str,
        cost_cents: int = 0,
    ) -> dict[str, Any]:
        """Writes a standard activity_log record for observability and auditing."""
        payload: dict[str, Any] = {
            "action_type": action_type,
            "description": description,
            "cost_cents": cost_cents,
        }
        if agent_id:
            payload["agent_id"] = agent_id
        if owner_id:
            payload["owner_id"] = owner_id
        return self.insert("activity_log", payload)
