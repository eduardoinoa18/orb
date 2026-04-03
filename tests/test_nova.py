"""Tests for Nova content agent routes and workflows."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_nova_status_route() -> None:
    """Nova status route should be available."""
    response = client.get("/agents/nova/status")
    assert response.status_code == 200
    assert response.json()["status"] == "nova router ready"


def test_weekly_calendar_endpoint_returns_created_count() -> None:
    """Weekly calendar endpoint should return created rows."""
    payload = {"owner_id": "owner-1", "week_start": "2026-03-30"}
    with patch("app.api.routes.content.creator.generate_weekly_content_calendar") as mock_generate:
        mock_generate.return_value = {"created": 7, "content": [{"id": "c1"}]}
        response = client.post("/agents/nova/weekly-calendar", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 7


def test_listing_post_endpoint_calls_creator() -> None:
    """Listing endpoint should return creator response."""
    payload = {
        "owner_id": "owner-1",
        "property_data": {"address": "123 Main St", "price": "$350,000"},
        "platforms": ["instagram"],
    }
    with patch("app.api.routes.content.creator.create_listing_post") as mock_create:
        mock_create.return_value = {"created": 1, "content": [{"id": "x"}]}
        response = client.post("/agents/nova/listing-post", json=payload)

    assert response.status_code == 200
    assert response.json()["created"] == 1


def test_approve_content_route_returns_queued() -> None:
    """Approve route should mark content as queued."""
    with patch("app.api.routes.content.SupabaseService") as mock_db:
        mock_db.return_value.update_many.return_value = [{"id": "c1"}]
        response = client.post("/agents/nova/content/c1/approve", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_reject_content_route_returns_rejected() -> None:
    """Reject route should store reason and return rejected status."""
    with patch("app.api.routes.content.SupabaseService") as mock_db:
        mock_db.return_value.fetch_all.return_value = [{"id": "c1", "performance_data": {}}]
        mock_db.return_value.update_many.return_value = [{"id": "c1"}]
        response = client.post("/agents/nova/content/c1/reject", json={"reason": "too generic"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_nova_learn_outcomes_route() -> None:
    payload = {"owner_id": "owner-1"}
    with patch("app.api.routes.content.nova_brain.learn_from_outcomes") as mock_learn:
        mock_learn.return_value = {"status": "updated", "owner_id": "owner-1", "improvements_made": 1}
        response = client.post("/agents/nova/learn-outcomes", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "updated"


def test_nova_owner_needs_route() -> None:
    payload = {"owner_id": "owner-1"}
    with patch("app.api.routes.content.nova_brain.identify_owner_needs") as mock_needs:
        mock_needs.return_value = {
            "agent_id": "owner-1",
            "observation_period_days": 30,
            "suggestions": ["Ship weekly ops summary"],
        }
        response = client.post("/agents/nova/owner-needs", json=payload)

    assert response.status_code == 200
    assert response.json()["suggestions"]
