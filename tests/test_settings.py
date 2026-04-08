"""Basic tests for ORB settings."""

from unittest.mock import MagicMock, patch

from config.settings import get_settings
from config.settings import Settings



def test_settings_load_core_platform_values() -> None:
    """Ensures the settings object loads the expected application metadata."""
    settings = get_settings()

    assert settings.app_name == "ORB"
    assert settings.app_version == "0.1.0"
    assert "http://localhost:3000" in settings.cors_origins


def test_settings_require_uses_ui_stored_secret_when_env_placeholder() -> None:
    settings = Settings.model_construct(
        platform_name="ORB",
        platform_domain="example.com",
        jwt_secret_key="x" * 40,
        environment="development",
        supabase_url="https://example.supabase.co",
        supabase_service_key="svc",
        supabase_anon_key="anon",
        anthropic_api_key="anthropic-placeholder",
        openai_api_key="",
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_from_number="",
        bland_ai_api_key="",
        my_phone_number="+15550000000",
        my_email="owner@example.com",
        my_business_address="123 Main St",
        alpha_vantage_api_key="",
        marketaux_api_key="",
        google_client_id="",
        google_client_secret="",
        google_redirect_uri="",
    )

    fake_store = MagicMock()
    fake_store.get.return_value = "sk-ant-real-from-ui"

    with patch("app.database.settings_store.SettingsStore", return_value=fake_store):
        assert settings.require("anthropic_api_key") == "sk-ant-real-from-ui"


def test_settings_require_raises_when_no_env_or_ui_secret() -> None:
    settings = Settings.model_construct(
        platform_name="ORB",
        platform_domain="example.com",
        jwt_secret_key="x" * 40,
        environment="development",
        supabase_url="https://example.supabase.co",
        supabase_service_key="svc",
        supabase_anon_key="anon",
        anthropic_api_key="anthropic-placeholder",
        openai_api_key="",
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_from_number="",
        bland_ai_api_key="",
        my_phone_number="+15550000000",
        my_email="owner@example.com",
        my_business_address="123 Main St",
        alpha_vantage_api_key="",
        marketaux_api_key="",
        google_client_id="",
        google_client_secret="",
        google_redirect_uri="",
    )

    fake_store = MagicMock()
    fake_store.get.return_value = ""

    with patch("app.database.settings_store.SettingsStore", return_value=fake_store):
        try:
            settings.require("anthropic_api_key")
            assert False, "Expected require() to fail when neither env nor UI key is usable"
        except RuntimeError as exc:
            assert "missing or placeholder" in str(exc)
