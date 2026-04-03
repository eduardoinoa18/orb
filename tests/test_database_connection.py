from unittest.mock import patch

import pytest

from app.database.connection import DatabaseConnectionError, SupabaseService


class _InsertSequence:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, table_name: str, payload: dict) -> dict:
        self.calls.append(payload)
        if len(self.calls) == 1:
            raise DatabaseConnectionError(
                "Failed to insert row into 'activity_log': Could not find the 'metadata' column of 'activity_log'"
            )
        return {"id": "act-1", **payload}


def test_log_activity_retries_without_metadata_column() -> None:
    service = SupabaseService.__new__(SupabaseService)
    insert = _InsertSequence()
    service.insert_one = insert  # type: ignore[method-assign]

    with patch("app.database.connection.dispatch_agent_action"):
        row = service.log_activity(
            agent_id="sage",
            owner_id="owner-1",
            action_type="health_check",
            description="Sage monitor pass",
            metadata={"agent_name": "Sage"},
        )

    assert row["id"] == "act-1"
    assert len(insert.calls) == 2
    assert "metadata" in insert.calls[0]
    assert "metadata" not in insert.calls[1]


def test_log_activity_raises_non_metadata_errors() -> None:
    service = SupabaseService.__new__(SupabaseService)

    def always_fail(_table_name: str, _payload: dict) -> dict:
        raise DatabaseConnectionError("Failed to insert row into 'activity_log': network unavailable")

    service.insert_one = always_fail  # type: ignore[method-assign]

    with patch("app.database.connection.dispatch_agent_action"):
        with pytest.raises(DatabaseConnectionError):
            service.log_activity(
                agent_id="sage",
                owner_id="owner-1",
                action_type="health_check",
                description="Sage monitor pass",
                metadata={"agent_name": "Sage"},
            )
