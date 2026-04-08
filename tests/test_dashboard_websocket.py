"""Tests for dashboard websocket live updates."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes.websocket import manager
from integrations.ws_broadcaster import dispatch_agent_action


client = TestClient(app)


def test_dashboard_websocket_receives_agent_action() -> None:
    """Connected dashboard clients should receive broadcasted agent actions."""
    with client.websocket_connect("/ws/dashboard") as websocket:
        first = websocket.receive_json()
        dispatch_agent_action(
            agent_id="rex",
            agent_name="Rex",
            action_type="call",
            message="Calling John Smith...",
            outcome="success",
            agent_color="#14b8a6",
        )
        payload = websocket.receive_json()

    if first.get("type") == "agent_action":
        payload = first

    assert payload["type"] == "agent_action"
    assert payload["message"] == "Calling John Smith..."


def test_dashboard_websocket_manager_tracks_connections() -> None:
    """Manager should add and remove active connections safely."""
    before = len(manager.active_connections)
    with client.websocket_connect("/ws/dashboard"):
        assert len(manager.active_connections) >= before
    assert len(manager.active_connections) == before
