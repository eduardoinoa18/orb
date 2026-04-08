"""Runtime preflight report for startup and setup workflows."""

from __future__ import annotations

from typing import Any

from app.database.schema_readiness import schema_readiness_payload
from config.settings import get_settings


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


def _resolve_setting(settings: Any, key_name: str) -> str:
    resolver = getattr(settings, "resolve", None)
    if callable(resolver):
        return str(resolver(key_name) or "")
    return str(getattr(settings, key_name, "") or "")


def build_preflight_report() -> dict[str, Any]:
    settings = get_settings()
    schema = schema_readiness_payload()

    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    critical_checks = [
        ("supabase_url", settings.supabase_url, "Supabase URL"),
        ("supabase_service_key", settings.supabase_service_key, "Supabase service key"),
        ("anthropic_api_key", _resolve_setting(settings, "anthropic_api_key"), "Anthropic API key"),
    ]

    quality_checks = [
        ("openai_api_key", _resolve_setting(settings, "openai_api_key"), "OpenAI API key"),
        ("twilio_account_sid", _resolve_setting(settings, "twilio_account_sid"), "Twilio SID"),
        ("twilio_auth_token", _resolve_setting(settings, "twilio_auth_token"), "Twilio token"),
        ("stripe_secret_key", settings.stripe_secret_key, "Stripe secret key"),
    ]

    for key, value, label in critical_checks:
        if _looks_placeholder(str(value or "")):
            blockers.append(
                {
                    "code": f"critical_{key}",
                    "message": f"{label} is missing or placeholder.",
                    "action": f"Set {key.upper()} in orb-platform/.env.",
                }
            )

    for key, value, label in quality_checks:
        if _looks_placeholder(str(value or "")):
            warnings.append(
                {
                    "code": f"warn_{key}",
                    "message": f"{label} is missing or placeholder.",
                    "action": f"Set {key.upper()} in orb-platform/.env for full capability.",
                }
            )

    if not schema.get("ready"):
        blockers.append(
            {
                "code": "schema_not_ready",
                "message": "Database schema readiness checks failed.",
                "action": "Run scripts/setup_database.py --strict and apply scripts/database_migration_patch.sql.",
            }
        )

    score = max(0, 100 - len(blockers) * 25 - len(warnings) * 7)

    return {
        "ready": len(blockers) == 0,
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "schema": schema,
        "summary": {
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
        },
    }
