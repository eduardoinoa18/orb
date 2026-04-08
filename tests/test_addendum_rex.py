"""Tests for Addendum Rex routes and learning flow."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_rex_status_route() -> None:
    response = client.get("/agents/rex/status")
    assert response.status_code == 200
    assert response.json()["status"] == "rex addendum routes ready"


def test_rex_learn_owner_route() -> None:
    payload = {
        "owner_id": "owner-1",
        "product_description": "We provide AI sales assistants for local businesses.",
        "ideal_customer_profile": "Owners of service businesses with inbound lead flow.",
        "common_objections": ["Too expensive"],
        "successful_close_examples": ["Owner booked demo after ROI breakdown"],
    }
    with patch("app.api.routes.rex.rex_brain.learn_from_owner") as mock_learn:
        mock_learn.return_value = {"status": "learned", "owner_id": "owner-1", "profile": {}}
        response = client.post("/agents/rex/learn-owner", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "learned"


def test_rex_learn_outcomes_route() -> None:
    payload = {"owner_id": "owner-1"}
    with patch("app.api.routes.rex.rex_brain.learn_from_outcomes") as mock_learn:
        mock_learn.return_value = {"status": "updated", "owner_id": "owner-1", "improvements_made": 2}
        response = client.post("/agents/rex/learn-outcomes", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
