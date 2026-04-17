"""Tests for Twilio WhatsApp inbound webhook handling."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_whatsapp_webhook_rejects_missing_signature() -> None:
    response = client.post(
        "/webhooks/whatsapp/incoming",
        headers={"content-type": "application/x-www-form-urlencoded"},
        data="From=whatsapp%3A%2B15555550123&To=whatsapp%3A%2B18889619713&Body=YES",
    )

    assert response.status_code == 401
    assert "Invalid Twilio signature" in response.json()["detail"]


def test_whatsapp_webhook_rejects_invalid_signature() -> None:
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=False):
        response = client.post(
            "/webhooks/whatsapp/incoming",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "bad-signature",
            },
            data="From=whatsapp%3A%2B15555550123&To=whatsapp%3A%2B18889619713&Body=STATUS",
        )

    assert response.status_code == 401


def test_whatsapp_webhook_commander_takes_priority() -> None:
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=True), patch(
        "app.api.routes.webhooks.handle_incoming_whatsapp_message",
        return_value={"handled": True, "message": "Commander status: all systems go."},
    ), patch("app.api.routes.webhooks.handle_trade_reply") as mock_trade:
        response = client.post(
            "/webhooks/whatsapp/incoming",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "valid-signature",
            },
            data="From=whatsapp%3A%2B15555550123&To=whatsapp%3A%2B18889619713&Body=STATUS",
        )

    assert response.status_code == 200
    assert "Commander status" in response.text
    mock_trade.assert_not_called()


def test_whatsapp_webhook_trade_reply_uses_normalized_numbers() -> None:
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=True), patch(
        "app.api.routes.webhooks.handle_incoming_whatsapp_message",
        return_value=None,
    ), patch("app.api.routes.webhooks.handle_trade_reply", return_value={"success": True, "decision": "YES"}) as mock_trade:
        response = client.post(
            "/webhooks/whatsapp/incoming",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "valid-signature",
            },
            data="From=whatsapp%3A%2B15555550123&To=whatsapp%3A%2B18889619713&Body=YES",
        )

    assert response.status_code == 200
    assert "Reply processed: YES" in response.text
    mock_trade.assert_called_once_with(
        message_body="YES",
        to_number="+18889619713",
        from_number="+15555550123",
    )
