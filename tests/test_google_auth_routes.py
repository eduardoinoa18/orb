"""Tests for production Google OAuth start/callback routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_google_start_redirects_to_google_auth_url() -> None:
    with patch("app.api.routes.auth_google.google_client.get_auth_url", return_value="https://accounts.google.com/o/oauth2/auth?state=x"):
        response = client.get("/auth/google/start", params={"owner_id": "owner-123"}, follow_redirects=False)

    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]


def test_google_start_requires_owner_id() -> None:
    response = client.get("/auth/google/start", params={"owner_id": "   "}, follow_redirects=False)
    assert response.status_code == 400


def test_google_callback_redirects_to_dashboard_integrations() -> None:
    with patch(
        "app.api.routes.auth_google.google_client.handle_callback",
        return_value={"success": True, "owner_id": "owner-123", "email": "owner@example.com"},
    ):
        response = client.get(
            "/auth/google/callback",
            params={"code": "code123", "state": "state123"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("/dashboard/integrations?")
    assert "google_connected=true" in response.headers["location"]
    assert "owner_id=owner-123" in response.headers["location"]


def test_google_callback_returns_400_on_invalid_state() -> None:
    with patch("app.api.routes.auth_google.google_client.handle_callback", side_effect=ValueError("Invalid Google OAuth state token.")):
        response = client.get(
            "/auth/google/callback",
            params={"code": "code123", "state": "bad-state"},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert "Invalid Google OAuth state token" in response.json()["detail"]
