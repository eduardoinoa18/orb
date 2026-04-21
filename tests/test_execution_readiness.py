from types import SimpleNamespace
from unittest.mock import patch

from app.runtime.execution_readiness import owner_execution_readiness


class _FakeDb:
    def __init__(self, owners, agents, integrations):
        self._owners = owners
        self._agents = agents
        self._integrations = integrations

    def fetch_all(self, table: str, where: dict):
        if table == "owners":
            return [r for r in self._owners if r.get("id") == where.get("id")]
        if table == "agents":
            return [r for r in self._agents if r.get("owner_id") == where.get("owner_id")]
        if table == "owner_integrations":
            return [r for r in self._integrations if r.get("owner_id") == where.get("owner_id")]
        return []


def test_owner_execution_readiness_flags_missing_identity_and_channels() -> None:
    fake_db = _FakeDb(
        owners=[{"id": "owner-1", "email": "", "phone": ""}],
        agents=[{"id": "a1", "owner_id": "owner-1", "is_active": True, "name": "Rex", "agent_type": "", "email_address": "", "phone_number": ""}],
        integrations=[],
    )
    fake_settings = SimpleNamespace(is_configured=lambda key: False)

    with patch("app.runtime.execution_readiness.SupabaseService", return_value=fake_db), patch(
        "app.runtime.execution_readiness.get_settings", return_value=fake_settings
    ):
        result = owner_execution_readiness("owner-1")

    assert result["ready"] is False
    assert result["score"] < 100
    codes = {item["code"] for item in result["blockers"]}
    assert "owner_email_missing" in codes
    assert "agent_identity_incomplete" in codes
    assert "no_execution_channels" in codes


def test_owner_execution_readiness_passes_when_identity_and_channels_exist() -> None:
    fake_db = _FakeDb(
        owners=[{"id": "owner-1", "email": "owner@example.com", "phone": "+15555550001"}],
        agents=[
            {
                "id": "a1",
                "owner_id": "owner-1",
                "is_active": True,
                "status": "active",
                "name": "Rex",
                "agent_type": "sales",
                "email_address": "rex@example.com",
                "phone_number": "+15555550002",
            }
        ],
        integrations=[{"owner_id": "owner-1", "provider_slug": "slack", "status": "connected"}],
    )
    configured_keys = {
        "twilio_account_sid",
        "twilio_auth_token",
        "twilio_from_number",
        "anthropic_api_key",
        "slack_bot_token",
    }
    fake_settings = SimpleNamespace(is_configured=lambda key: key in configured_keys)

    with patch("app.runtime.execution_readiness.SupabaseService", return_value=fake_db), patch(
        "app.runtime.execution_readiness.get_settings", return_value=fake_settings
    ):
        result = owner_execution_readiness("owner-1")

    assert result["ready"] is True
    assert result["identity"]["active_agents"] == 1
    assert result["identity"]["missing_agent_identity_fields"] == 0
    assert result["integrations"]["owner_connected_integrations"] == 1
