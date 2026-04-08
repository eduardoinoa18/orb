"""Tests for Sage starter addendum routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_sage_status_route() -> None:
    response = client.get("/agents/sage/status")
    assert response.status_code == 200
    assert response.json()["status"] == "sage routes ready"


def test_sage_platform_monitor_route() -> None:
    with patch("app.api.routes.sage.sage_brain.run_platform_monitor") as mock_monitor:
        mock_monitor.return_value = {
            "status": "healthy",
            "severity": "normal",
            "metrics": {"api_response_ms": 220},
            "unhealthy_signals": [],
            "diagnosis": {"priority": "normal"},
        }
        response = client.post("/agents/sage/platform-monitor")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_sage_learn_outcomes_route() -> None:
    with patch("app.api.routes.sage.sage_brain.learn_from_outcomes") as mock_learn:
        mock_learn.return_value = {
            "status": "updated",
            "owner_id": "owner-1",
            "improvements_made": 2,
            "plan": {},
        }
        response = client.post("/agents/sage/learn-outcomes", json={"owner_id": "owner-1"})

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
