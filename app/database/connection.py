"""Supabase connection helpers for ORB.

The functions in this file provide a small wrapper around the Supabase client
so the rest of the codebase can perform common operations in one place.
"""

from typing import Any

from supabase import Client, create_client

from config.settings import get_settings
from integrations.ws_broadcaster import dispatch_agent_action


class DatabaseConnectionError(RuntimeError):
    """Raised when the Supabase client cannot be created or used."""


def get_supabase_client() -> Client:
    """Creates and returns a Supabase client using environment variables."""
    settings = get_settings()
    try:
        return create_client(settings.supabase_url, settings.supabase_service_key)
    except Exception as error:
        raise DatabaseConnectionError("Failed to create Supabase client.") from error


class SupabaseService:
    """Small helper class for common database operations."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def fetch_all(self, table_name: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Reads rows from a table and optionally applies equality filters."""
        try:
            query = self.client.table(table_name).select("*")
            if filters:
                for field_name, value in filters.items():
                    query = query.eq(field_name, value)
            response = query.execute()
            return response.data or []
        except Exception as error:
            raise DatabaseConnectionError(
                f"Failed to fetch rows from '{table_name}': {error}"
            ) from error

    def select(self, table_name: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Compatibility wrapper matching the planned Level 1 API."""
        return self.fetch_all(table_name, filters)

    def insert_one(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Inserts a single row and returns the inserted record when available."""
        try:
            response = self.client.table(table_name).insert(payload).execute()
            rows = response.data or []
            return rows[0] if rows else payload
        except Exception as error:
            raise DatabaseConnectionError(
                f"Failed to insert row into '{table_name}': {error}"
            ) from error

    def insert(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Compatibility wrapper matching the planned Level 1 API."""
        return self.insert_one(table_name, payload)

    def update_many(
        self,
        table_name: str,
        filters: dict[str, Any],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Updates matching rows and returns the updated records."""
        try:
            query = self.client.table(table_name).update(payload)
            for field_name, value in filters.items():
                query = query.eq(field_name, value)
            response = query.execute()
            return response.data or []
        except Exception as error:
            raise DatabaseConnectionError(
                f"Failed to update rows in '{table_name}': {error}"
            ) from error

    def update(self, table_name: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Updates one row by id and returns the updated record when available."""
        rows = self.update_many(table_name, {"id": row_id}, payload)
        return rows[0] if rows else {"id": row_id, **payload}

    def delete_many(self, table_name: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Deletes matching rows and returns the deleted records when available."""
        try:
            query = self.client.table(table_name).delete()
            for field_name, value in filters.items():
                query = query.eq(field_name, value)
            response = query.execute()
            return response.data or []
        except Exception as error:
            raise DatabaseConnectionError(
                f"Failed to delete rows from '{table_name}': {error}"
            ) from error

    def delete(self, table_name: str, row_id: str) -> bool:
        """Deletes one row by id and reports whether anything was removed."""
        rows = self.delete_many(table_name, {"id": row_id})
        return bool(rows) or True

    def log_activity(
        self,
        agent_id: str | None,
        owner_id: str | None,
        action_type: str,
        description: str,
        cost_cents: int = 0,
        outcome: str | None = None,
        needs_approval: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Writes an activity_log row directly through the shared database helper."""
        payload: dict[str, Any] = {
            "action_type": action_type,
            "description": description,
            "cost_cents": cost_cents,
            "needs_approval": needs_approval,
        }
        if agent_id:
            payload["agent_id"] = agent_id
        if owner_id:
            payload["owner_id"] = owner_id
        if outcome is not None:
            payload["outcome"] = outcome
        if metadata is not None:
            payload["metadata"] = metadata

        try:
            row = self.insert_one("activity_log", payload)
        except DatabaseConnectionError as error:
            message = str(error).lower()
            if "metadata" in message and "activity_log" in message and "metadata" in payload:
                # Backward-compatible fallback for environments where activity_log has no metadata column yet.
                payload_without_metadata = dict(payload)
                payload_without_metadata.pop("metadata", None)
                row = self.insert_one("activity_log", payload_without_metadata)
            else:
                raise

        # Push a live dashboard event for the animated office scene.
        agent_name = ""
        if isinstance(metadata, dict):
            agent_name = str(metadata.get("agent_name") or "")
        if not agent_name and agent_id:
            agent_name = str(agent_id)

        dispatch_agent_action(
            agent_id=str(agent_id or "system"),
            agent_name=agent_name,
            action_type=action_type,
            message=description,
            outcome=outcome,
        )

        return row
