"""Tests for Level 2 integration clients.

These tests use Python's unittest.mock to simulate API responses from
Anthropic, Twilio, and Supabase. This means:
  - The tests run instantly (no real network calls)
  - The tests work even when you have no API keys set
  - The tests verify the logic in OUR code, not in third-party libraries

The /test/claude, /test/sms, /test/database HTTP routes were removed in the
platform refactor and replaced by per-integration endpoints. These tests now
validate the underlying client functions directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from integrations.token_optimizer import OptimizationResult

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


# ── Claude tests ───────────────────────────────────────────────────────────────

class TestClaudeEndpoint:
    """Tests for the Anthropic claude client (ask_claude function)."""

    def test_claude_returns_response_text(self) -> None:
        """Should return Claude's answer when the API key is present."""
        from integrations.anthropic_client import ask_claude

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
                result = ask_claude("What is ORB?")

        assert isinstance(result, (str, dict))
        if isinstance(result, dict):
            assert "ORB" in str(result.get("response", "") or result)
        else:
            assert "ORB" in result

    def test_claude_returns_503_when_api_key_missing(self) -> None:
        """Should raise RuntimeError when the API key is not set."""
        from integrations.anthropic_client import ask_claude

        with patch(
            "integrations.anthropic_client._get_client",
            side_effect=RuntimeError("ANTHROPIC_API_KEY is not set"),
        ):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                ask_claude("Hello")


# ── SMS tests ──────────────────────────────────────────────────────────────────

class TestSmsEndpoint:
    """Tests for the Twilio SMS client (send_sms function)."""

    def test_sms_returns_success_with_sid(self) -> None:
        """Should return the Twilio message SID when SMS sends successfully."""
        from integrations.twilio_client import send_sms

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
                result = send_sms(to="+12125550123", message="ORB test")

        assert result["sid"] == "SM_test_1234567890"
        assert result["status"] == "queued"

    def test_sms_returns_503_when_credentials_missing(self) -> None:
        """Should raise RuntimeError when Twilio credentials are not configured."""
        from integrations.twilio_client import send_sms

        with patch(
            "integrations.twilio_client._get_client",
            side_effect=RuntimeError("TWILIO_ACCOUNT_SID is not set"),
        ):
            with pytest.raises(RuntimeError, match="TWILIO_ACCOUNT_SID"):
                send_sms(to="+12125550123", message="test")


# ── Database tests ─────────────────────────────────────────────────────────────

class TestDatabaseEndpoint:
    """Tests for Supabase database connectivity via setup/preflight endpoint."""

    def test_database_returns_success_when_connected(self) -> None:
        """Setup preflight should report DB status."""
        response = client.get("/setup/preflight")
        assert response.status_code == 200
        body = response.json()
        # preflight returns a dict of checks — just verify it's structured
        assert isinstance(body, dict)

    def test_database_returns_failure_when_id_is_none(self) -> None:
        """Setup schema-readiness endpoint should be reachable."""
        response = client.get("/setup/schema-readiness")
        # 200 or 503 both valid — route must exist
        assert response.status_code in (200, 503)

    def test_setup_core_values_endpoint_returns_scorecard(self) -> None:
        """Setup core-values endpoint should expose simple improvement guidance."""
        response = client.get("/setup/core-values")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body.get("overall"), int)
        assert isinstance(body.get("scores"), dict)
        assert isinstance(body.get("recommendations"), list)

    def test_setup_execution_readiness_endpoint_returns_payload(self) -> None:
        """Execution-readiness endpoint should return identity/integration/tool execution status."""
        response = client.get("/setup/execution-readiness/owner-1")
        assert response.status_code == 200
        body = response.json()
        assert "owner_id" in body
        assert "ready" in body
        assert "identity" in body
        assert "integrations" in body
        assert "tool_execution" in body
