"""Centralized environment settings for ORB.

This module loads .env values, validates required fields, and exposes
`get_settings()` so other modules can share one cached settings object.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _looks_placeholder(value: str) -> bool:
    lowered = (value or "").strip().lower()
    if not lowered:
        return True
    marker_words = (
        "placeholder",
        "replace",
        "changeme",
        "example",
        "test",
        "your_",
        "your-",
    )
    return any(word in lowered for word in marker_words)


class Settings(BaseSettings):
    """Strongly typed application settings loaded from environment variables."""

    # Core Platform
    platform_name: str
    platform_domain: str
    jwt_secret_key: str
    environment: str

    # Database
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str

    # AI Brains
    anthropic_api_key: str
    openai_api_key: str

    # Communications
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    bland_ai_api_key: str

    # Owner Details
    my_phone_number: str
    my_email: str
    my_business_address: str

    # Market Data
    alpha_vantage_api_key: str
    marketaux_api_key: str

    # Google APIs
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Helpful runtime metadata
    app_version: str = "0.1.0"
    allowed_local_origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    api_prefix: str = ""
    google_workspace_admin_email: str = ""
    tradingview_webhook_secret: str = ""

    # Addendum optional settings
    railway_api_token: str = ""
    railway_project_id: str = ""
    token_cache_ttl_minutes: int = 1440
    computer_use_enabled: bool = False
    computer_use_screenshot_dir: str = "artifacts/screenshots"
    aria_briefing_enabled: bool = True
    aria_briefing_hour: int = 7
    aria_briefing_minute: int = 0
    aria_briefing_timezone: str = "America/New_York"
    sage_monitor_enabled: bool = True
    sage_monitor_interval_minutes: int = 30
    encryption_secret: str = ""
    mfa_secret_key: str = ""
    session_secret: str = ""
    whisper_enabled: bool = False
    rate_limit_redis_url: str = ""
    google_ai_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    privacy_mode: bool = False
    resend_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter_monthly: str = ""
    stripe_price_starter_annual: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_annual: str = ""
    stripe_price_full_team_monthly: str = ""
    stripe_price_full_team_annual: str = ""
    stripe_price_rex_monthly: str = ""
    stripe_price_aria_monthly: str = ""
    stripe_price_nova_monthly: str = ""
    stripe_price_orion_monthly: str = ""
    stripe_price_sage_monthly: str = ""
    stripe_price_atlas_monthly: str = ""
    stripe_price_commander_monthly: str = ""
    email_webhook_secret: str = ""
    sentry_dsn: str = ""
    next_public_api_url: str = ""
    next_public_stripe_pk: str = ""
    superadmin_email: str = ""

    _required_fields = {
        "platform_name",
        "platform_domain",
        "jwt_secret_key",
        "environment",
        "supabase_url",
        "supabase_service_key",
        "supabase_anon_key",
        "my_phone_number",
        "my_email",
        "my_business_address",
    }

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_required_values(self) -> "Settings":
        """Fail loudly if any required variable is missing or blank."""
        missing: list[str] = []
        for field_name in self._required_fields:
            value = getattr(self, field_name, None)
            if value is None or not str(value).strip():
                missing.append(field_name.upper())

        if missing:
            if "ANTHROPIC_API_KEY" in missing:
                raise ValueError(
                    "Missing required environment variable: ANTHROPIC_API_KEY. "
                    "Get your key from https://console.anthropic.com/settings/keys, "
                    "then add it to orb-platform/.env."
                )
            raise ValueError(
                "Missing required environment variables in orb-platform/.env: "
                + ", ".join(sorted(missing))
            )

        return self

    @property
    def app_name(self) -> str:
        """Backward-compatible alias used by existing `app/*` modules."""
        return self.platform_name

    @property
    def twilio_phone_number(self) -> str:
        """Backward-compatible alias for older integration code."""
        return self.twilio_from_number

    @property
    def cors_origins(self) -> list[str]:
        """Returns CORS origins compatible with both app and platform APIs."""
        production_origins = {
            f"https://{self.platform_domain}",
            f"http://{self.platform_domain}",
        }
        return list(dict.fromkeys([*self.allowed_local_origins, *production_origins]))

    def require(self, key_name: str) -> str:
        """Returns a non-empty setting value or raises a clear runtime error."""
        value = self.resolve(key_name, default="")
        alias_map = {
            "twilio_phone_number": "twilio_from_number",
        }
        resolved_name = alias_map.get(key_name, key_name)
        if value is None or not str(value).strip() or _looks_placeholder(str(value)):
            raise RuntimeError(
                f"Configuration error: '{resolved_name.upper()}' is missing or placeholder in orb-platform/.env and platform settings."
            )
        return str(value).strip()

    def resolve(self, key_name: str, default: str = "") -> str:
        """Resolve a setting from env first, then encrypted UI-stored settings when needed."""
        alias_map = {
            "twilio_phone_number": "twilio_from_number",
        }
        resolved_name = alias_map.get(key_name, key_name)
        value = getattr(self, resolved_name, "")
        normalized = str(value).strip() if value is not None else ""
        if normalized and not _looks_placeholder(normalized):
            return normalized

        try:
            from app.database.settings_store import SettingsStore

            stored = SettingsStore().get(resolved_name, default="")
            stored_normalized = str(stored).strip() if stored is not None else ""
            if stored_normalized:
                return stored_normalized
        except Exception:
            pass

        return normalized or default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns cached settings so env parsing happens once per process."""
    return Settings()
