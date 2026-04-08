"""Tests for dashboard live metric aggregation."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import DatabaseConnectionError, _build_dashboard_metrics, app

client = TestClient(app)



def test_build_dashboard_metrics_connected() -> None:
    """Builds expected counts and cost when Supabase data is available."""
    agents = [
        {"id": "a1", "name": "Rex", "role": "trading", "status": "active"},
        {"status": "paused"},
        {"status": "active"},
    ]
    trades = [
        {"status": "pending_approval"},
        {"status": "closed"},
    ]
    activity = [
        {
            "action_type": "sms",
            "description": "Sent approval SMS",
            "cost_cents": 1,
            "needs_approval": False,
            "created_at": "2026-03-27T10:00:00+00:00",
        },
        {
            "action_type": "trade",
            "description": "Pending review",
            "cost_cents": 0,
            "needs_approval": True,
            "created_at": "2026-03-27T11:00:00+00:00",
            "agent_id": "a1",
        },
    ]

    with patch("app.api.main.SupabaseService") as mock_db:
        mock_instance = mock_db.return_value

        def fake_fetch(table_name: str):
            if table_name == "agents":
                return agents
            if table_name == "trades":
                return trades
            if table_name == "activity_log":
                return activity
            return []

        mock_instance.fetch_all.side_effect = fake_fetch
        result = _build_dashboard_metrics()

    assert result["db_status"] == "connected"
    assert result["active_agents"] == 2
    assert result["pending_approvals"] == 2
    assert isinstance(result["daily_cost_dollars"], float)
    assert len(result["recent_activity"]) >= 1
    assert len(result["agents"]) >= 1
    assert result["agents"][0]["name"] == "Rex"
    assert "quick_actions" in result



def test_build_dashboard_metrics_offline() -> None:
    """Returns safe fallback values when database cannot be reached."""
    with patch("app.api.main.SupabaseService", side_effect=DatabaseConnectionError("db down")):
        result = _build_dashboard_metrics()

    assert result["db_status"] == "offline"
    assert result["active_agents"] == 0
    assert result["pending_approvals"] == 0


def test_dashboard_data_endpoint_is_public_and_returns_json() -> None:
    """Ensures /dashboard/data can be called without JWT and returns expected keys."""
    with patch("app.api.main._build_dashboard_metrics", return_value={
        "active_agents": 1,
        "pending_approvals": 0,
        "daily_cost_dollars": 0.01,
        "recent_activity": ["sms: sent"],
        "agents": [{"name": "Rex", "role": "trading", "status": "active", "last_action": "sms sent"}],
        "quick_actions": ["POST /test/database"],
        "db_status": "connected",
    }):
        response = client.get("/dashboard/data")

    assert response.status_code == 200
    body = response.json()
    assert body["active_agents"] == 1
    assert body["db_status"] == "connected"
    assert len(body["agents"]) == 1
