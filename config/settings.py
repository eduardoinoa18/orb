"""Centralized environment settings for ORB.

DESIGN PHILOSOPHY
-----------------
Only truly bootstrapping secrets are *required* at startup:
  - SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY  (database)
  - JWT_SECRET_KEY                                             (auth signing)
  - PLATFORM_NAME / PLATFORM_DOMAIN / ENVIRONMENT             (identity)
  - MY_EMAIL                                                   (owner routing)

All other keys (AI providers, Twilio, Google, Stripe, etc.) are *optional*
and can be configured post-launch via the Integration Hub UI.  The
`require()` / `resolve()` helpers raise clear errors at call-time rather
than blocking the app from starting.
"""

from __future__ import annotations

import base64
import json
import secrets
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
    # Avoid false-positives on real URLs that contain "example"
    if lowered.startswith("http"):
        return False
    marker_words = ("placeholder", "replace", "changeme", "your_", "your-", "insert_")
    return any(word in lowered for word in marker_words)


def _is_probably_service_role_key(value: str) -> bool:
    """Best-effort check that SUPABASE_SERVICE_KEY is a privileged key.

    Accepts both modern secret keys (sb_secret_...) and legacy JWT keys
    whose payload role claim is service_role.
    """
    token = (value or "").strip()
    if not token:
        return False

    # Modern Supabase secret key format
    if token.startswith("sb_secret_"):
        return True

    # Legacy JWT format: header.payload.signature
    parts = token.split(".")
    if len(parts) != 3:
        return False

    try:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8"))
        return payload.get("role") == "service_role"
    except Exception:
        return False


class Settings(BaseSettings):
    """Strongly typed application settings loaded from environment variables."""

    # ── Core Platform (REQUIRED) ───────────────────────────────────────────────
    platform_name: str = "ORB"
    platform_domain: str = "localhost"
    jwt_secret_key: str = ""
    environment: str = "development"

    # ── Database (REQUIRED) ───────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""

    # ── Owner Identity (REQUIRED) ─────────────────────────────────────────────
    my_email: str = ""
    my_phone_number: str = ""
    my_business_address: str = ""

    # ── AI Providers (optional — configure via Integration Hub) ───────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_ai_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Communications (optional) ─────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    bland_ai_api_key: str = ""
    resend_api_key: str = ""

    # ── Google OAuth (optional) ───────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_redirect_uri: str = ""
    google_workspace_admin_email: str = ""

    # ── Extended Integrations (optional) ─────────────────────────────────────
    slack_bot_token: str = ""
    notion_api_key: str = ""
    notion_database_id: str = ""
    github_token: str = ""
    hubspot_api_key: str = ""
    elevenlabs_api_key: str = ""

    # ── Payments (optional) ───────────────────────────────────────────────────
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

    # ── Market Data (optional) ────────────────────────────────────────────────
    alpha_vantage_api_key: str = ""
    marketaux_api_key: str = ""
    tradingview_webhook_secret: str = ""

    # ── Security extras (auto-generated if blank) ─────────────────────────────
    encryption_secret: str = ""
    mfa_secret_key: str = ""
    session_secret: str = ""
    email_webhook_secret: str = ""

    # ── Infrastructure (optional) ─────────────────────────────────────────────
    railway_api_token: str = ""
    railway_project_id: str = ""
    sentry_dsn: str = ""
    rate_limit_redis_url: str = ""
    superadmin_email: str = ""

    # ── Feature flags ─────────────────────────────────────────────────────────
    computer_use_enabled: bool = False
    computer_use_screenshot_dir: str = "artifacts/screenshots"
    aria_briefing_enabled: bool = False
    aria_briefing_hour: int = 7
    aria_briefing_minute: int = 0
    aria_briefing_timezone: str = "America/New_York"
    sage_monitor_enabled: bool = False
    sage_monitor_interval_minutes: int = 30
    token_cache_ttl_minutes: int = 1440
    whisper_enabled: bool = False
    privacy_mode: bool = False

    # ── Frontend ──────────────────────────────────────────────────────────────
    next_public_api_url: str = ""
    next_public_stripe_pk: str = ""

    # ── Runtime metadata ──────────────────────────────────────────────────────
    app_version: str = "1.0.0"
    api_prefix: str = ""
    allowed_local_origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Validation ────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def validate_bootstrap_secrets(self) -> "Settings":
        """Ensure the minimal set of bootstrap secrets is present."""
        missing: list[str] = []

        if not self.supabase_url.strip():
            missing.append("SUPABASE_URL")
        if not self.supabase_service_key.strip():
            missing.append("SUPABASE_SERVICE_KEY")
        if not self.supabase_anon_key.strip():
            missing.append("SUPABASE_ANON_KEY")

        if self.supabase_service_key.strip() and not _is_probably_service_role_key(self.supabase_service_key):
            missing.append("SUPABASE_SERVICE_KEY (must be service_role or sb_secret_ key)")

        # Auto-generate JWT secret if missing (non-production)
        if not self.jwt_secret_key.strip():
            if self.environment.lower() in ("production", "prod"):
                missing.append("JWT_SECRET_KEY")
            else:
                object.__setattr__(self, "jwt_secret_key", secrets.token_hex(32))

        # Auto-generate encryption secret if missing
        if not self.encryption_secret.strip():
            object.__setattr__(self, "encryption_secret", secrets.token_hex(32))

        if missing:
            raise ValueError(
                "ORB cannot start. Missing required environment variables:\n"
                + "\n".join(f"  • {v}" for v in sorted(missing))
                + "\n\nSet these in Railway → Variables or in orb-platform/.env"
            )

        return self

    # ── Backward-compat properties ────────────────────────────────────────────
    @property
    def app_name(self) -> str:
        return self.platform_name

    @property
    def twilio_phone_number(self) -> str:
        return self.twilio_from_number

    @property
    def cors_origins(self) -> list[str]:
        production_origins = {
            # Custom domain
            f"https://{self.platform_domain}",
            f"http://{self.platform_domain}",
            f"https://www.{self.platform_domain}",
            # Vercel preview and production deployments
            "https://orb-landing.vercel.app",
            "https://www.orb-landing.vercel.app",
            # Railway backend itself (for same-origin calls)
            "https://orb-platform.up.railway.app",
        }
        # Also allow any *.vercel.app subdomain (Vercel preview URLs)
        extra = [o for o in self.allowed_local_origins]
        return list(dict.fromkeys([*extra, *production_origins]))

    # ── Runtime helpers ───────────────────────────────────────────────────────
    def require(self, key_name: str) -> str:
        """Returns a non-empty setting or raises a clear runtime error."""
        value = self.resolve(key_name, default="")
        if not value or _looks_placeholder(value):
            raise RuntimeError(
                f"Integration '{key_name.upper()}' is not configured. "
                f"Add it in the Integration Hub or set {key_name.upper()} in Railway Variables."
            )
        return value

    def resolve(self, key_name: str, default: str = "") -> str:
        """Resolve from env first, then encrypted DB settings store."""
        alias_map = {"twilio_phone_number": "twilio_from_number"}
        resolved_name = alias_map.get(key_name, key_name)
        value = getattr(self, resolved_name, "") or ""
        normalized = str(value).strip()
        if normalized and not _looks_placeholder(normalized):
            return normalized

        # Fall back to encrypted UI-stored value
        try:
            from app.database.settings_store import SettingsStore
            stored = SettingsStore().get(resolved_name, default="")
            stored_norm = str(stored).strip() if stored else ""
            if stored_norm:
                return stored_norm
        except Exception:
            pass

        return normalized or default

    def is_configured(self, key_name: str) -> bool:
        """Returns True if a setting has a real (non-placeholder) value."""
        try:
            val = self.resolve(key_name, default="")
            return bool(val and not _looks_placeholder(val))
        except Exception:
            return False

    def integration_status(self) -> dict[str, bool]:
        """Returns a dict of integration name -> configured status for the UI."""
        return {
            "anthropic": self.is_configured("anthropic_api_key"),
            "openai": self.is_configured("openai_api_key"),
            "twilio": self.is_configured("twilio_account_sid"),
            "bland_ai": self.is_configured("bland_ai_api_key"),
            "google_oauth": self.is_configured("google_client_id"),
            "google_calendar": self.is_configured("google_refresh_token"),
            "slack": self.is_configured("slack_bot_token"),
            "notion": self.is_configured("notion_api_key"),
            "github": self.is_configured("github_token"),
            "hubspot": self.is_configured("hubspot_api_key"),
            "elevenlabs": self.is_configured("elevenlabs_api_key"),
            "stripe": self.is_configured("stripe_secret_key"),
            "resend": self.is_configured("resend_api_key"),
            "alpha_vantage": self.is_configured("alpha_vantage_api_key"),
            "sentry": self.is_configured("sentry_dsn"),
            "railway": self.is_configured("railway_api_token"),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns cached settings; env parsing happens once per process."""
    return Settings()
      