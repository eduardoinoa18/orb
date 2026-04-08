"""Tests for computer-use safety guard and routes."""

from fastapi.testclient import TestClient

from agents.computer_use.safety_guard import SafetyGuard
from app.api.main import app

client = TestClient(app)


def test_safety_guard_blocks_never_allowed_action() -> None:
    decision = SafetyGuard.evaluate(action="delete_files", description="delete old files")
    assert decision.allowed is False


def test_computer_use_status_route() -> None:
    response = client.get("/agents/computer-use/status")
    assert response.status_code == 200
    assert response.json()["status"] == "computer-use routes ready"


def test_computer_use_safety_check_route() -> None:
    payload = {"action": "click_button", "description": "send payment now"}
    response = client.post("/agents/computer-use/safety-check", json=payload)

    assert response.status_code == 200
    assert response.json()["allowed"] is True
    assert response.json()["requires_approval"] is True
