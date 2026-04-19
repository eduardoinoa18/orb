"""Tests for Zara automated at-risk check-ins."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from agents.zara.zara_brain import ZaraBrain
from app.api.main import app
from app.api.routes import zara as zara_routes

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def _mock_brain() -> MagicMock:
    brain = MagicMock()
    brain.send_at_risk_check_ins.return_value = {
        "scanned": 5,
        "at_risk": 2,
        "sent": 2,
        "dry_run": False,
        "details": [],
    }
    return brain


def test_checkins_endpoint_accepts_cron_key(monkeypatch) -> None:
    monkeypatch.setenv("ORB_CRON_SECRET", "orb-cron")
    brain = _mock_brain()
    monkeypatch.setattr(zara_routes, "_get_brain", lambda: brain)

    response = client.post("/zara/check-ins/send?cron_key=orb-cron&max_accounts=25")

    assert response.status_code == 200
    payload = response.json()
    assert payload["at_risk"] == 2
    brain.send_at_risk_check_ins.assert_called_once_with(dry_run=False, max_accounts=25)


def test_require_admin_or_cron_rejects_unauthenticated_when_no_cron(monkeypatch) -> None:
    monkeypatch.delenv("ORB_CRON_SECRET", raising=False)

    request = MagicMock()
    request.state.token_payload = {}

    try:
        zara_routes._require_admin_or_cron(request, cron_key=None)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_send_at_risk_checkins_dry_run_filters_non_risky_owners() -> None:
    brain = object.__new__(ZaraBrain)

    owners_query = MagicMock()
    owners_query.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "owner-risk", "email": "risk@example.com", "phone": "+15555550001"},
        {"id": "owner-healthy", "email": "ok@example.com", "phone": "+15555550002"},
    ]

    agent_messages_table = MagicMock()
    agent_messages_table.insert.return_value.execute.return_value = None

    db = MagicMock()

    def table_side_effect(table_name: str):
        if table_name == "owners":
            return owners_query
        if table_name == "agent_messages":
            return agent_messages_table
        raise AssertionError(f"Unexpected table {table_name}")

    db.client.table.side_effect = table_side_effect
    brain.db = db
    brain.tracker = MagicMock()
    brain.tracker.get_health_score.side_effect = [{"score": 40}, {"score": 75}]
    brain.generate_check_in_message = MagicMock(return_value="hello")
    brain._send_check_in_message = MagicMock(return_value={"sent": True, "channel": "whatsapp", "target": "+15555550001"})

    summary = ZaraBrain.send_at_risk_check_ins(brain, dry_run=True, max_accounts=10)

    assert summary["scanned"] == 2
    assert summary["at_risk"] == 1
    assert summary["sent"] == 0
    assert summary["dry_run"] is True
    assert len(summary["details"]) == 1
    assert summary["details"][0]["channel"] == "dry_run"
    brain._send_check_in_message.assert_not_called()


def test_send_at_risk_checkins_sends_messages_when_not_dry_run() -> None:
    brain = object.__new__(ZaraBrain)

    owners_query = MagicMock()
    owners_query.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "owner-risk", "email": "risk@example.com", "phone": "+15555550001"},
    ]

    agent_messages_table = MagicMock()
    agent_messages_table.insert.return_value.execute.return_value = None

    db = MagicMock()

    def table_side_effect(table_name: str):
        if table_name == "owners":
            return owners_query
        if table_name == "agent_messages":
            return agent_messages_table
        raise AssertionError(f"Unexpected table {table_name}")

    db.client.table.side_effect = table_side_effect
    brain.db = db
    brain.tracker = MagicMock()
    brain.tracker.get_health_score.return_value = {"score": 35}
    brain.generate_check_in_message = MagicMock(return_value="hello")
    brain._send_check_in_message = MagicMock(return_value={"sent": True, "channel": "whatsapp", "target": "+15555550001"})

    summary = ZaraBrain.send_at_risk_check_ins(brain, dry_run=False, max_accounts=10)

    assert summary["at_risk"] == 1
    assert summary["sent"] == 1
    brain._send_check_in_message.assert_called_once()
