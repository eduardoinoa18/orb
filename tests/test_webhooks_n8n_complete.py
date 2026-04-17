"""Tests for N8N workflow completion webhook."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_n8n_complete_webhook_processes_known_workflow():
    """POST /webhooks/n8n/complete should dispatch completion handler and log."""
    payload = {
        "event": "sequence_complete",
        "workflow_name": "30_day_nurture",
        "execution_id": "exec-456",
        "workflow_data": {"lead_email": "prospect@example.com", "sequence_count": 3},
    }

    with patch("app.api.routes.webhooks.handle_workflow_complete") as mock_handler, \
         patch("app.api.routes.webhooks.log_activity") as mock_log:
        mock_handler.return_value = {"success": True, "action": "updated_sequence_status"}
        response = client.post("/webhooks/n8n/complete", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["status"] == "processed"
    assert body["workflow_name"] == "30_day_nurture"
    assert body["execution_id"] == "exec-456"
    mock_handler.assert_called_once_with("sequence_complete", "30_day_nurture", payload["workflow_data"])
    assert mock_log.call_count == 1


def test_n8n_complete_webhook_handles_unknown_workflow():
    """POST /webhooks/n8n/complete should still return 200 for unknown workflows."""
    payload = {
        "event": "sequence_complete",
        "workflow_name": "unregistered_workflow",
        "workflow_data": {},
    }

    with patch("app.api.routes.webhooks.handle_workflow_complete") as mock_handler, \
         patch("app.api.routes.webhooks.log_activity"):
        mock_handler.return_value = {"success": False, "reason": "Unknown workflow type: unregistered_workflow"}
        response = client.post("/webhooks/n8n/complete", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["status"] == "no_handler"


def test_n8n_complete_webhook_returns_200_when_log_activity_fails():
    """POST /webhooks/n8n/complete should never 500 even if database logging fails."""
    payload = {
        "event": "sequence_complete",
        "workflow_name": "hot_lead_urgent",
        "workflow_data": {"lead_email": "x@example.com"},
    }

    with patch("app.api.routes.webhooks.handle_workflow_complete") as mock_handler, \
         patch("app.api.routes.webhooks.log_activity", side_effect=RuntimeError("db error")):
        mock_handler.return_value = {"success": True, "action": "updated_sequence_status"}
        response = client.post("/webhooks/n8n/complete", json=payload)

    assert response.status_code == 200
    assert response.json()["received"] is True


def test_n8n_complete_webhook_uses_defaults_for_optional_fields():
    """POST /webhooks/n8n/complete should work with only workflow_name in payload."""
    payload = {"workflow_name": "weekly_metrics_report"}

    with patch("app.api.routes.webhooks.handle_workflow_complete") as mock_handler, \
         patch("app.api.routes.webhooks.log_activity"):
        mock_handler.return_value = {"success": True, "action": "logged_report_send"}
        response = client.post("/webhooks/n8n/complete", json=payload)

    assert response.status_code == 200
    mock_handler.assert_called_once_with("sequence_complete", "weekly_metrics_report", {})
