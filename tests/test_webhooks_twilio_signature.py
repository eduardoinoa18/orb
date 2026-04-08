"""Tests for Twilio SMS webhook signature validation."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_twilio_sms_webhook_rejects_missing_signature() -> None:
    """Webhook must reject unsigned inbound requests."""
    response = client.post(
        "/webhooks/twilio/sms",
        headers={"content-type": "application/x-www-form-urlencoded"},
        data="From=%2B15555550123&To=%2B18889619713&Body=YES",
    )

    assert response.status_code == 401
    assert "Invalid Twilio signature" in response.json()["detail"]


def test_twilio_sms_webhook_rejects_invalid_signature() -> None:
    """Webhook must reject requests when signature validation fails."""
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=False):
        response = client.post(
            "/webhooks/twilio/sms",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "bad-signature",
            },
            data="From=%2B15555550123&To=%2B18889619713&Body=YES",
        )

    assert response.status_code == 401


def test_twilio_sms_webhook_accepts_valid_signature() -> None:
    """Webhook should process inbound messages when signature check passes."""
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=True), patch(
        "app.api.routes.webhooks.process_mobile_command", return_value=None
    ), patch("app.api.routes.webhooks.handle_trade_reply", return_value={"success": True, "decision": "YES"}):
        response = client.post(
            "/webhooks/twilio/sms",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "valid-signature",
            },
            data="From=%2B15555550123&To=%2B18889619713&Body=YES",
        )

    assert response.status_code == 200
    assert "Reply processed: YES" in response.text


def test_twilio_sms_webhook_mobile_command_takes_priority() -> None:
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=True), patch(
        "app.api.routes.webhooks.process_mobile_command",
        return_value={"success": True, "message": "Commander status: all systems go."},
    ), patch("app.api.routes.webhooks.handle_trade_reply") as mock_trade:
        response = client.post(
            "/webhooks/twilio/sms",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "valid-signature",
            },
            data="From=%2B15555550123&To=%2B18889619713&Body=STATUS",
        )

    assert response.status_code == 200
    assert "Commander status" in response.text
    mock_trade.assert_not_called()
