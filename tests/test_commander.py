"""Tests for Commander brain and API routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from jose import jwt

from agents.commander.commander_brain import CommanderBrain
from app.security.action_tokens import verify_and_consume_action_token
from config.settings import get_settings


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode({"sub": "test-owner"}, settings.jwt_secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_commander_brain_process_owner_request_returns_structure() -> None:
    brain = CommanderBrain()
    context = {
        "owner_profile": {"owner_name": "Edu"},
        "pipeline": {"total": 8, "hot": 2, "qualified": 3},
        "calendar": {"meetings_today": 2},
        "pending_approvals": {"count": 1},
        "daily_ai_cost": {"cost_dollars": 4.2},
        "platform_health": {"status": "all_clear", "error_count": 0},
        "orion": {"trades_today": 1, "win_rate": 100, "pnl_today": 55.0},
        "urgent_alerts": [],
    }

    with patch("agents.commander.commander_brain.ask_claude") as mock_ai:
        mock_ai.return_value = {"text": "I already activated Rex and Aria, and I will report results in one hour."}
        result = brain.process_owner_request(
            owner_message="Have Rex and Aria handle today's top priorities.",
            owner_id="owner-1",
            conversation_history=[],
            context=context,
        )

    assert "response" in result
    assert "actions_taken" in result
    assert "agents_activated" in result
    assert "summary_for_activity_log" in result
    assert result["agents_activated"]


def test_commander_brain_executes_direct_tool_intents() -> None:
    brain = CommanderBrain()
    context = {
        "owner_profile": {"owner_name": "Edu", "plan": "professional"},
        "pipeline": {"total": 8, "hot": 2, "qualified": 3},
        "calendar": {"meetings_today": 2},
        "pending_approvals": {"count": 1},
        "daily_ai_cost": {"cost_dollars": 4.2},
        "platform_health": {"status": "all_clear", "error_count": 0},
        "orion": {"trades_today": 1, "win_rate": 100, "pnl_today": 55.0},
        "urgent_alerts": [],
    }

    class _FakeToolResult:
        def __init__(self, tool: str):
            self.tool = tool

        def to_dict(self):
            return {
                "tool": self.tool,
                "success": True,
                "data": "ok",
                "error": None,
                "needs_approval": False,
                "timestamp": "2026-04-18T00:00:00+00:00",
            }

    fake_dispatcher = SimpleNamespace(
        execute=lambda tool, params: _FakeToolResult(tool),
    )

    with patch("agents.commander.commander_brain.ask_claude") as mock_ai, \
         patch("agents.commander.tool_dispatcher.ToolDispatcher", return_value=fake_dispatcher):
        mock_ai.return_value = {"text": "Done. I handled it."}
        result = brain.process_owner_request(
            owner_message="Run platform scan and show platform health.",
            owner_id="owner-1",
            conversation_history=[],
            context=context,
        )

    assert result["tool_results"]
    tools = {row["tool"] for row in result["tool_results"]}
    assert "platform_scan" in tools
    assert "platform_health" in tools


def test_commander_brain_refines_response_with_immediate_actions() -> None:
    brain = CommanderBrain()
    context = {
        "owner_profile": {"owner_name": "Edu"},
        "pipeline": {"total": 8, "hot": 2, "qualified": 3},
        "calendar": {"meetings_today": 2},
        "pending_approvals": {"count": 1},
        "daily_ai_cost": {"cost_dollars": 4.2},
        "platform_health": {"status": "all_clear", "error_count": 0},
        "orion": {"trades_today": 1, "win_rate": 100, "pnl_today": 55.0},
        "urgent_alerts": [],
    }

    with patch("agents.commander.commander_brain.ask_claude") as mock_ai:
        mock_ai.return_value = {"text": "I will handle this now."}
        result = brain.process_owner_request(
            owner_message="Please prioritize sales leads.",
            owner_id="owner-1",
            conversation_history=[],
            context=context,
        )

    assert "Immediate actions:" in result["response"]


def test_commander_message_endpoint_returns_structured_payload(client) -> None:
    fake_context = {
        "owner_id": "owner-1",
        "owner_profile": {"owner_name": "Edu"},
        "pipeline": {"total": 0, "hot": 0, "qualified": 0},
        "calendar": {"meetings_today": 0},
        "pending_approvals": {"count": 0},
        "daily_ai_cost": {"cost_dollars": 0},
        "platform_health": {"status": "all_clear", "error_count": 0},
        "orion": {"trades_today": 0, "win_rate": 0, "pnl_today": 0},
        "urgent_alerts": [],
    }
    fake_response = {
        "response": "I am on it. I activated Rex for pipeline follow-up.",
        "actions_taken": [{"agent": "rex", "task_id": "task-1", "priority": "high", "due_by": ""}],
        "agents_activated": ["rex"],
        "follow_ups_scheduled": [{"summary": "rex update expected", "eta": ""}],
        "needs_approval": [],
        "summary_for_activity_log": "Commander processed owner request and activated rex.",
        "commander_name": "Max",
    }

    with patch("app.api.routes.commander.commander_brain.gather_full_context", new=AsyncMock(return_value=fake_context)):
        with patch("app.api.routes.commander.commander_brain.process_owner_request", return_value=fake_response):
            response = client.post(
                "/commander/message",
                json={"message": "Brief me on everything", "owner_id": "owner-1"},
                headers=_auth_headers(),
            )

    assert response.status_code == 200
    body = response.json()
    assert body["response"].startswith("I am on it")
    assert body["agents_activated"] == ["rex"]
    assert "generated_at" in body


def test_commander_context_endpoint_returns_snapshot(client) -> None:
    fake_context = {"owner_id": "owner-1", "pipeline": {"total": 3}}

    with patch("app.api.routes.commander.commander_brain.gather_full_context", new=AsyncMock(return_value=fake_context)):
        response = client.get("/commander/context/owner-1", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["owner_id"] == "owner-1"


def test_commander_configure_endpoint_updates_preferences(client) -> None:
    response = client.post(
        "/commander/configure",
        json={
            "owner_id": "owner-1",
            "commander_name": "Marco",
            "personality_style": "direct",
            "briefing_time": "07:30",
            "review_day": "sunday",
            "language": "en",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configured"
    assert body["config"]["commander_name"] == "Marco"


def test_commander_mobile_preferences_roundtrip(client) -> None:
    save = client.post(
        "/commander/mobile/preferences",
        json={
            "owner_id": "owner-1",
            "alerts_enabled": True,
            "approvals_enabled": False,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "06:00",
        },
        headers=_auth_headers(),
    )
    assert save.status_code == 200
    assert save.json()["preferences"]["approvals_enabled"] is False

    loaded = client.get("/commander/mobile/preferences/owner-1", headers=_auth_headers())
    assert loaded.status_code == 200
    assert loaded.json()["preferences"]["quiet_hours_start"] == "22:00"


def test_commander_mobile_action_link_token_replay_is_blocked(client) -> None:
    response = client.post(
        "/commander/mobile/action-link",
        json={
            "owner_id": "owner-1",
            "action": "approval",
            "payload": {"id": "deal-7", "label": "Deal 7"},
            "ttl_minutes": 10,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    token = response.json()["token"]

    first_use = verify_and_consume_action_token(token, expected_action="approval")
    assert first_use["owner_id"] == "owner-1"

    try:
        verify_and_consume_action_token(token, expected_action="approval")
        assert False, "Expected token replay to fail"
    except ValueError as exc:
        assert "already been used" in str(exc)


def test_commander_email_dispatch_alert_sends_email(client) -> None:
    fake_db = SimpleNamespace(fetch_all=lambda table, where: [{"id": "owner-1", "email": "owner@example.com"}])

    with patch("app.api.routes.commander._db", return_value=fake_db), patch(
        "app.api.routes.commander.send_resend_email",
        return_value={"sent": True, "provider": "resend"},
    ) as mock_send:
        response = client.post(
            "/commander/email/dispatch-alert",
            json={
                "owner_id": "owner-1",
                "subject": "ORB Alert",
                "message": "Pipeline risk detected",
            },
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["email"]["sent"] is True
    mock_send.assert_called_once()


def test_commander_email_dispatch_alert_includes_approval_links(client) -> None:
    fake_db = SimpleNamespace(fetch_all=lambda table, where: [{"id": "owner-1", "email": "owner@example.com"}])

    with patch("app.api.routes.commander._db", return_value=fake_db), patch(
        "app.api.routes.commander.send_resend_email",
        return_value={"sent": True, "provider": "resend"},
    ) as mock_send:
        response = client.post(
            "/commander/email/dispatch-alert",
            json={
                "owner_id": "owner-1",
                "subject": "Approval required",
                "message": "Review this action",
                "include_approval_links": True,
                "action_payload": {"id": "deal-99", "label": "Deal 99"},
            },
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    called_kwargs = mock_send.call_args.kwargs
    assert "APPROVE" in called_kwargs["html"]
    assert "DECLINE" in called_kwargs["html"]


def test_commander_email_dispatch_alert_requires_owner_email(client) -> None:
    fake_db = SimpleNamespace(fetch_all=lambda table, where: [{"id": "owner-1", "email": ""}])

    with patch("app.api.routes.commander._db", return_value=fake_db):
        response = client.post(
            "/commander/email/dispatch-alert",
            json={
                "owner_id": "owner-1",
                "subject": "ORB Alert",
                "message": "Pipeline risk detected",
            },
            headers=_auth_headers(),
        )

    assert response.status_code == 400
    assert "Owner email is missing" in response.json()["detail"]
