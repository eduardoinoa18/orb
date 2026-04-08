from app.api.main import app
from fastapi.testclient import TestClient
from unittest.mock import patch

client = TestClient(app)


def test_onboarding_register_and_status() -> None:
    response = client.post(
        "/onboarding/register",
        json={
            "email": "owner@example.com",
            "password": "very-strong-pass",
            "accept_terms": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner_id"]
    assert payload["next_step"] == "about_you"

    status = client.get(f"/onboarding/status/{payload['owner_id']}")
    assert status.status_code == 200
    status_payload = status.json()
    assert "register" in status_payload["steps"]


def test_onboarding_happy_path_trial_flow() -> None:
    register = client.post(
        "/onboarding/register",
        json={
            "email": "builder@example.com",
            "password": "very-strong-pass",
            "accept_terms": True,
        },
    )
    owner_id = register.json()["owner_id"]

    about = client.post(
        "/onboarding/about",
        json={
            "owner_id": owner_id,
            "first_name": "Eduar",
            "industry": "construction",
            "business_name": "Orb Builders",
        },
    )
    assert about.status_code == 200
    assert about.json()["next_step"] == "commander"

    commander = client.post(
        "/onboarding/commander",
        json={
            "owner_id": owner_id,
            "commander_name": "ORB Prime",
            "personality_style": "focused",
        },
    )
    assert commander.status_code == 200
    assert commander.json()["next_step"] == "plan"

    plan = client.post(
        "/onboarding/plan",
        json={
            "owner_id": owner_id,
            "plan": "starter",
            "billing": "monthly",
            "trial": True,
        },
    )
    assert plan.status_code == 200
    assert plan.json()["next_step"] == "first_agent"

    first_agent = client.post(
        "/onboarding/first-agent",
        json={
            "owner_id": owner_id,
            "agent_name": "Rex",
            "role": "sales",
        },
    )
    assert first_agent.status_code == 200
    assert first_agent.json()["next_step"] == "connect_tool"
    assert first_agent.json()["command_center_path"] == f"/dashboard?owner_id={owner_id}"

    connect = client.post(
        "/onboarding/connect-tool",
        json={
            "owner_id": owner_id,
            "tool_key": "none",
            "connection_mode": "skip",
        },
    )
    assert connect.status_code == 200
    assert connect.json()["next_step"] == "dashboard"
    assert connect.json()["completed"] is True

    status = client.get(f"/onboarding/status/{owner_id}")
    assert status.status_code == 200
    assert "connect_tool" in status.json()["steps"]


def test_onboarding_connect_tool_blocks_when_schema_not_ready() -> None:
    register = client.post(
        "/onboarding/register",
        json={
            "email": "schema-block@example.com",
            "password": "very-strong-pass",
            "accept_terms": True,
        },
    )
    owner_id = register.json()["owner_id"]

    with patch("app.api.routes.onboarding.schema_readiness_ready", return_value=False):
        blocked = client.post(
            "/onboarding/connect-tool",
            json={
                "owner_id": owner_id,
                "tool_key": "google",
                "connection_mode": "oauth",
            },
        )

    assert blocked.status_code == 503
    assert "Database schema is not ready" in blocked.json().get("detail", "")
