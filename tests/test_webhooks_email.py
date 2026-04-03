"""Tests for inbound email webhook command handling."""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_email_webhook_rejects_invalid_secret_when_configured() -> None:
    settings = SimpleNamespace(resolve=lambda key, default="": "expected-secret" if key == "email_webhook_secret" else default)

    with patch("app.api.routes.webhooks.get_settings", return_value=settings):
        response = client.post(
            "/webhooks/email/incoming",
            headers={"x-orb-email-secret": "wrong"},
            json={"from_email": "owner@example.com", "subject": "STATUS", "text": ""},
        )

    assert response.status_code == 401
    assert "Invalid email webhook secret" in response.json()["detail"]


def test_email_webhook_accepts_and_processes_with_valid_secret() -> None:
    settings = SimpleNamespace(resolve=lambda key, default="": "expected-secret" if key == "email_webhook_secret" else default)

    with patch("app.api.routes.webhooks.get_settings", return_value=settings), patch(
        "app.api.routes.webhooks.handle_incoming_email_message",
        return_value={"success": True, "kind": "status", "message": "Commander status: all systems go."},
    ) as mock_handler:
        response = client.post(
            "/webhooks/email/incoming",
            headers={"x-orb-email-secret": "expected-secret"},
            json={"from_email": "owner@example.com", "subject": "STATUS", "text": ""},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["received"] is True
    assert payload["processed"] is True
    assert "Commander status" in payload["result"]["message"]
    mock_handler.assert_called_once_with(from_email="owner@example.com", subject="STATUS", text_body="")


def test_email_webhook_allows_unsecured_mode_when_no_secret_is_set() -> None:
    settings = SimpleNamespace(resolve=lambda key, default="": "")

    with patch("app.api.routes.webhooks.get_settings", return_value=settings), patch(
        "app.api.routes.webhooks.handle_incoming_email_message",
        return_value={"success": True, "kind": "chat", "message": "Handled"},
    ):
        response = client.post(
            "/webhooks/email/incoming",
            json={"from_email": "owner@example.com", "subject": "", "text": "check pipeline"},
        )

    assert response.status_code == 200
    assert response.json()["processed"] is True


def test_email_webhook_returns_processed_false_when_no_owner_match() -> None:
    settings = SimpleNamespace(resolve=lambda key, default="": "")

    with patch("app.api.routes.webhooks.get_settings", return_value=settings), patch(
        "app.api.routes.webhooks.handle_incoming_email_message",
        return_value=None,
    ):
        response = client.post(
            "/webhooks/email/incoming",
            json={"from_email": "unknown@example.com", "subject": "STATUS", "text": ""},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed"] is False
    assert "No matching owner or command" in payload["detail"]
