"""Tests for Level 2 integration routes.

These tests use Python's unittest.mock to simulate API responses from
Anthropic, Twilio, and Supabase. This means:
  - The tests run instantly (no real network calls)
  - The tests work even when you have no API keys set
  - The tests verify the logic in OUR code, not in third-party libraries

When you see `patch("integrations.anthropic_client._get_client")`, that means
"replace the real Anthropic client with a fake one that returns what we tell it."
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from integrations.token_optimizer import OptimizationResult

client = TestClient(app)


# ── Claude tests ───────────────────────────────────────────────────────────────

class TestClaudeEndpoint:
    """Tests for POST /test/claude"""

    def test_claude_returns_response_text(self) -> None:
        """Should return Claude's answer when the API key is present."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ORB is an AI agent identity platform.")]
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 15

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        optimization = OptimizationResult(
            optimized_prompt="What is ORB?",
            selected_model="haiku",
            max_tokens=1024,
            used_cache=False,
            cache_key="test-key",
            needs_ai=True,
        )

        with patch("integrations.anthropic_client.TokenOptimizer") as mock_optimizer_cls:
            mock_optimizer = MagicMock()
            mock_optimizer.optimize_prompt.return_value = optimization
            mock_optimizer_cls.return_value = mock_optimizer
            with patch("integrations.anthropic_client._get_client", return_value=mock_client):
                response = client.post("/test/claude", json={"prompt": "What is ORB?"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "ORB" in body["response"]
        assert body["model"] == "claude-haiku-4-5-20251001"
        assert body["cost_cents"] >= 1

    def test_claude_returns_503_when_api_key_missing(self) -> None:
        """Should return HTTP 503 with a helpful message when key is not set."""
        with patch(
            "integrations.anthropic_client._get_client",
            side_effect=RuntimeError("ANTHROPIC_API_KEY is not set"),
        ):
            response = client.post("/test/claude", json={"prompt": "Hello"})

        assert response.status_code == 503
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]


# ── SMS tests ──────────────────────────────────────────────────────────────────

class TestSmsEndpoint:
    """Tests for POST /test/sms"""

    def test_sms_returns_success_with_sid(self) -> None:
        """Should return the Twilio message SID when SMS sends successfully."""
        mock_message = MagicMock()
        mock_message.sid = "SM_test_1234567890"
        mock_message.status = "queued"

        mock_messages = MagicMock()
        mock_messages.create.return_value = mock_message

        mock_twilio = MagicMock()
        mock_twilio.messages = mock_messages

        with patch("integrations.twilio_client._get_client", return_value=mock_twilio):
            with patch(
                "integrations.twilio_client.get_settings",
                return_value=MagicMock(
                    require=MagicMock(return_value="+15005550006"),
                ),
            ):
                response = client.post(
                    "/test/sms",
                    json={"to": "+12125550123", "message": "ORB test"},
                )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["sid"] == "SM_test_1234567890"
        assert body["status"] == "queued"

    def test_sms_returns_503_when_credentials_missing(self) -> None:
        """Should return HTTP 503 when Twilio credentials are not configured."""
        with patch(
            "integrations.twilio_client._get_client",
            side_effect=RuntimeError("TWILIO_ACCOUNT_SID is not set"),
        ):
            response = client.post(
                "/test/sms",
                json={"to": "+12125550123"},
            )

        assert response.status_code == 503


# ── Database tests ─────────────────────────────────────────────────────────────

class TestDatabaseEndpoint:
    """Tests for POST /test/database"""

    def test_database_returns_success_when_connected(self) -> None:
        """Should write and read a row when Supabase is working."""
        mock_written_row = {
            "id": "test-uuid-1234",
            "action_type": "test",
            "description": "Level 2 database connectivity test",
            "outcome": "test_write",
            "cost_cents": 0,
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_read_rows = [mock_written_row]

        with patch(
            "app.database.activity_log.log_activity",
            return_value=mock_written_row,
        ):
            with patch(
                "app.database.activity_log.get_recent_activity",
                return_value=mock_read_rows,
            ):
                response = client.post("/test/database")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["write_result"]["id"] == "test-uuid-1234"
        assert body["read_result"]["total_rows_found"] >= 1

    def test_database_returns_failure_when_id_is_none(self) -> None:
        """Should report failure gracefully when the database write returns no ID."""
        mock_no_id = {
            "action_type": "test",
            "id": None,
            "warning": "Database not connected — log not saved",
        }

        with patch("app.database.activity_log.log_activity", return_value=mock_no_id):
            response = client.post("/test/database")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "SUPABASE" in body["detail"].upper() or "database" in body["detail"].lower()
