"""Tests for N8N error webhook handling."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_n8n_error_webhook_returns_200_and_logs_alert() -> None:
    """Webhook should acknowledge failures and attempt logging + owner alert."""
    payload = {
        "workflow_name": "daily-briefing",
        "execution_id": "exec-123",
        "error_message": "Node timeout",
    }

    with patch("app.api.routes.webhooks.log_activity") as mock_log, patch(
        "app.api.routes.webhooks.get_settings"
    ) as mock_settings, patch("app.api.routes.webhooks.send_sms") as mock_sms:
        mock_settings.return_value.my_phone_number = "+15555550123"

        response = client.post("/webhooks/n8n/error", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["status"] == "accepted"
    assert body["workflow_name"] == "daily-briefing"
    assert body["alert_sent"] is True
    assert mock_log.call_count == 2
    mock_sms.assert_called_once()


def test_n8n_error_webhook_still_returns_200_when_sms_fails() -> None:
    """Webhook must return 200 to avoid infinite N8N retries even when SMS fails."""
    payload = {
        "workflow_name": "weekly-report",
        "execution_id": "exec-987",
        "error_message": "Webhook delivery failed",
    }

    with patch("app.api.routes.webhooks.log_activity") as mock_log, patch(
        "app.api.routes.webhooks.get_settings"
    ) as mock_settings, patch(
        "app.api.routes.webhooks.send_sms", side_effect=RuntimeError("twilio down")
    ):
        mock_settings.return_value.my_phone_number = "+15555550123"

        response = client.post("/webhooks/n8n/error", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["alert_sent"] is False
    assert "sms_failure" in str(body.get("error") or "")
    assert mock_log.call_count == 2
