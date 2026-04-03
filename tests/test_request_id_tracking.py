"""Tests for request ID tracking in responses and activity logs."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_endpoint_returns_request_id_header() -> None:
    """Every response should include X-Request-ID header."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) > 0


def test_request_id_is_consistent_in_header() -> None:
    """Multiple hits to same endpoint should have different request IDs."""
    response1 = client.get("/health")
    response2 = client.get("/health")

    id1 = response1.headers.get("X-Request-ID", "")
    id2 = response2.headers.get("X-Request-ID", "")
    assert id1 != id2
    assert id1
    assert id2


def test_request_id_propagates_to_activity_log() -> None:
    """Request ID should be logged when log_activity is called."""
    from app.database.activity_log import log_activity

    with patch("app.database.activity_log.SupabaseService") as mock_db_cls:
        mock_db = MagicMock()
        mock_db.insert_one.return_value = {"id": "log-123", "request_id": "req-abc-123"}
        mock_db_cls.return_value = mock_db

        log_activity(
            agent_id="agent-1",
            action_type="test",
            description="Test with request ID",
            request_id="req-abc-123",
        )

        call_args = mock_db.insert_one.call_args
        assert call_args is not None
        payload = call_args[0][1]
        assert payload.get("request_id") == "req-abc-123"


def test_request_id_is_optional_in_log_activity() -> None:
    """Logging should work even when request_id is not provided."""
    from app.database.activity_log import log_activity

    with patch("app.database.activity_log.SupabaseService") as mock_db_cls:
        mock_db = MagicMock()
        mock_db.insert_one.return_value = {"id": "log-456"}
        mock_db_cls.return_value = mock_db

        log_activity(
            agent_id="agent-2",
            action_type="test",
            description="Test without request ID",
        )

        call_args = mock_db.insert_one.call_args
        assert call_args is not None
        payload = call_args[0][1]
        assert "request_id" not in payload or payload.get("request_id") is None
