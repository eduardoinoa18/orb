"""Tests for Level 5 identity provisioning."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.identity.email_manager import create_agent_email
from agents.identity.phone_manager import route_incoming_call, route_incoming_sms
from app.api.main import app

client = TestClient(app)


def test_create_agent_email_builds_alias_address() -> None:
    """Email identity should be deterministic and domain-safe."""
    result = create_agent_email("Rex Prime", "orb.local")

    assert result["provisioned"] is True
    assert result["email_address"] == "rex.prime@orb.local"
    assert result["provider"] == "alias"


def test_route_incoming_sms_returns_unmatched_when_agent_missing() -> None:
    """SMS routing should fail safely when no agent owns the number."""
    with patch("agents.identity.phone_manager.SupabaseService") as mock_db:
        mock_db.return_value.fetch_all.return_value = []
        result = route_incoming_sms("+15550000001", "+15550000002", "hello")

    assert result["matched"] is False
    assert result["route"] == "unmatched"


def test_route_incoming_call_returns_matched_agent() -> None:
    """Call routing should identify the assigned agent."""
    with patch("agents.identity.phone_manager.SupabaseService") as mock_db:
        mock_db.return_value.fetch_all.return_value = [
            {"id": "agent-1", "name": "Rex", "phone_number": "+15550000002"}
        ]
        result = route_incoming_call("+15550000001", "+15550000002")

    assert result["matched"] is True
    assert result["agent_id"] == "agent-1"
    assert result["route"] == "agent_call_handler"


def test_provision_agent_route_returns_identity_package() -> None:
    """Provision endpoint should return the packaged identity details."""
    payload = {
        "owner_id": "owner-1",
        "agent_name": "Rex",
        "role": "wholesale_sales",
        "brain_provider": "claude",
        "owner_phone_number": "+15550000001",
    }

    mocked_result = {
        "agent_id": "agent-1",
        "name": "Rex",
        "phone": "+15550000002",
        "email": "rex@localhost",
        "role": "wholesale_sales",
        "status": "active",
        "provisioned_at": "2026-03-27T12:00:00+00:00",
    }

    with patch("app.api.routes.agents.provision_agent", return_value=mocked_result):
        response = client.post("/agents/provision", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "agent-1"
    assert body["phone"] == "+15550000002"
    assert body["status"] == "active"


def test_provision_agent_route_returns_400_for_validation_error() -> None:
    """Provision endpoint should return 400 when business validation fails."""
    payload = {
        "owner_id": "missing-owner",
        "agent_name": "Rex",
        "role": "wholesale_sales",
        "brain_provider": "claude",
    }

    with patch("app.api.routes.agents.provision_agent", side_effect=ValueError("Owner not found.")):
        response = client.post("/agents/provision", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Owner not found."
