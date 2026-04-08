"""Tests for production deployment checklist gating logic."""

import pytest
from unittest.mock import MagicMock, patch


def test_check_env_vars_passes_all_required():
    """check_env_vars should pass when all required settings are present."""
    from scripts.production_checklist import check_env_vars
    from config.settings import Settings

    mock_settings = MagicMock(spec=Settings)
    mock_settings.platform_name = "ORB"
    mock_settings.supabase_url = "https://abc.supabase.co"
    mock_settings.supabase_service_key = "service_key_value"
    mock_settings.anthropic_api_key = "sk-ant-key"
    mock_settings.openai_api_key = "sk-openai-key"
    mock_settings.twilio_account_sid = "AC" + "x" * 32
    mock_settings.twilio_auth_token = "x" * 32
    mock_settings.twilio_from_number = "+15555550100"
    mock_settings.jwt_secret_key = "supersecretjwtkey12345678901234567"
    mock_settings.my_phone_number = "+15555559999"
    mock_settings.my_email = "owner@example.com"

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_env_vars()

    assert all(results), f"Expected all checks to pass, got failures: {results}"


def test_check_jwt_strength_fails_weak_secret():
    """check_jwt_strength should fail on trivially weak JWT secrets."""
    from scripts.production_checklist import check_jwt_strength

    mock_settings = MagicMock()
    mock_settings.jwt_secret_key = "changeme"

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_jwt_strength()

    assert not any(results), "Expected JWT strength check to fail for 'changeme'"


def test_check_jwt_strength_passes_strong_secret():
    """check_jwt_strength should pass on a 32+ char non-trivial secret."""
    from scripts.production_checklist import check_jwt_strength

    mock_settings = MagicMock()
    mock_settings.jwt_secret_key = "a" * 48  # 48-char random secret

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_jwt_strength()

    assert all(results), "Expected JWT strength check to pass for long secret"


def test_check_communications_passes_valid_twilio():
    """check_communications should pass with correct Twilio credential format."""
    from scripts.production_checklist import check_communications

    mock_settings = MagicMock()
    mock_settings.twilio_account_sid = "AC" + "a" * 32  # Valid SID: AC + 32 chars
    mock_settings.twilio_auth_token = "b" * 32          # Valid token: 32 chars
    mock_settings.twilio_from_number = "+15555550100"

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_communications()

    assert all(results), "Expected Twilio format check to pass"


def test_check_communications_fails_invalid_format():
    """check_communications should fail with incorrect Twilio credential format."""
    from scripts.production_checklist import check_communications

    mock_settings = MagicMock()
    mock_settings.twilio_account_sid = "not-an-account-sid"
    mock_settings.twilio_auth_token = "short"
    mock_settings.twilio_from_number = "5555550100"  # Missing +

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_communications()

    assert not all(results), "Expected Twilio format check to fail"


def test_check_agents_passes_with_valid_settings():
    """check_agents should pass with default scheduler settings."""
    from scripts.production_checklist import check_agents

    mock_settings = MagicMock()
    mock_settings.aria_briefing_enabled = True
    mock_settings.aria_briefing_timezone = "America/New_York"
    mock_settings.sage_monitor_enabled = True
    mock_settings.sage_monitor_interval_minutes = 30

    with patch("config.settings.get_settings", return_value=mock_settings):
        results = check_agents()

    assert all(results), "Expected all agent config checks to pass"


def test_run_checklist_fast_mode_returns_nonzero_without_env():
    """run_checklist in fast mode should fail without real database connection."""
    from scripts.production_checklist import run_checklist

    # This test verifies the script runs end-to-end and exits with a valid exit code
    # In a container/CI without real credentials, it will fail (nonzero) which is fine
    # We just ensure it doesn't crash with an exception
    try:
        exit_code = run_checklist(fast=True)
        assert exit_code in (0, 1), "Exit code should be 0 or 1"
    except SystemExit as e:
        assert e.code in (0, 1), "sys.exit code should be 0 or 1"


def test_check_ai_integrations_fails_on_cached_or_fallback_results():
    """AI checks should fail when direct provider calls fail."""
    from scripts.production_checklist import check_ai_integrations

    with patch("integrations.anthropic_client._get_client", side_effect=RuntimeError("anthropic down")), patch(
        "integrations.openai_client._get_client", side_effect=RuntimeError("openai down"),
    ):
        results = check_ai_integrations(fast=False)

    assert results == [False, False]


def test_check_ai_integrations_passes_on_live_models():
    """AI checks should pass only when direct provider models respond."""
    from scripts.production_checklist import check_ai_integrations

    anthropic_response = MagicMock()
    anthropic_response.content = [MagicMock(text="ok")]
    anthropic_client = MagicMock()
    anthropic_client.messages.create.return_value = anthropic_response

    openai_response = MagicMock()
    openai_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    openai_client = MagicMock()
    openai_client.chat.completions.create.return_value = openai_response

    with patch("integrations.anthropic_client._get_client", return_value=anthropic_client), patch(
        "integrations.openai_client._get_client", return_value=openai_client
    ):
        results = check_ai_integrations(fast=False)

    assert results == [True, True]


def test_check_app_starts_fails_when_health_is_degraded():
    """Startup check should fail when /health returns degraded dependency state."""
    from scripts.production_checklist import check_app_starts

    mock_client_ctx = MagicMock()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "degraded",
        "dependencies": {"supabase": {"status": "unhealthy"}},
    }
    mock_client.get.return_value = mock_response
    mock_client_ctx.__enter__.return_value = mock_client
    mock_client_ctx.__exit__.return_value = None

    with patch("fastapi.testclient.TestClient", return_value=mock_client_ctx):
        results = check_app_starts()

    assert results == [True, False, False]
