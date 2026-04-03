"""Production deployment checklist for ORB.

Run this script before every deployment to validate all required integrations,
credentials, and configuration are properly set up.

Usage:
    python scripts/production_checklist.py [--all] [--fast]

Exit codes:
    0  All checks passed (safe to deploy)
    1  One or more checks failed (do NOT deploy)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PASS = "\u2713"
FAIL = "\u2717"
WARN = "\u26a0"
SKIP = "-"


def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def check(label: str, passed: bool, detail: str = "") -> bool:
    icon = PASS if passed else FAIL
    line = f"  [{icon}] {label}"
    if detail:
        line += f": {detail}"
    print(line)
    return passed


# ---------------------------------------------------------------------------
# Environment / Settings checks
# ---------------------------------------------------------------------------

def check_env_vars() -> list[bool]:
    """Verify all required environment variables are set."""
    header("Environment Variables")
    from config.settings import get_settings

    results = []
    required_keys = [
        ("PLATFORM_NAME", "platform_name"),
        ("SUPABASE_URL", "supabase_url"),
        ("SUPABASE_SERVICE_KEY", "supabase_service_key"),
        ("ANTHROPIC_API_KEY", "anthropic_api_key"),
        ("OPENAI_API_KEY", "openai_api_key"),
        ("TWILIO_ACCOUNT_SID", "twilio_account_sid"),
        ("TWILIO_AUTH_TOKEN", "twilio_auth_token"),
        ("TWILIO_FROM_NUMBER", "twilio_from_number"),
        ("JWT_SECRET_KEY", "jwt_secret_key"),
        ("MY_PHONE_NUMBER", "my_phone_number"),
        ("MY_EMAIL", "my_email"),
    ]

    try:
        settings = get_settings()
        for env_name, attr in required_keys:
            value = getattr(settings, attr, None)
            is_set = bool(value and str(value).strip())
            results.append(check(env_name, is_set, "set" if is_set else "MISSING"))
    except Exception as e:
        results.append(check("Settings load", False, str(e)[:80]))

    return results


def check_jwt_strength() -> list[bool]:
    """Verify JWT secret is not trivial."""
    header("Security")
    from config.settings import get_settings

    results = []
    try:
        settings = get_settings()
        jwt_secret = settings.jwt_secret_key
        weak_values = {"secret", "changeme", "dev", "test", "password", "jwt_secret"}
        is_strong = len(jwt_secret) >= 32 and jwt_secret.lower() not in weak_values
        results.append(check("JWT secret strength", is_strong, f"length={len(jwt_secret)}"))
    except Exception as e:
        results.append(check("JWT secret", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# Database / Supabase checks
# ---------------------------------------------------------------------------

def check_database() -> list[bool]:
    """Verify Supabase connectivity and required tables exist."""
    header("Database (Supabase)")
    from app.database.connection import DatabaseConnectionError, SupabaseService

    results = []
    required_tables = ["owners", "leads", "content", "activity_log", "trades"]

    try:
        db = SupabaseService()
        results.append(check("Supabase connection", True, "connected"))
    except DatabaseConnectionError as e:
        results.append(check("Supabase connection", False, str(e)[:80]))
        return results

    for table in required_tables:
        try:
            db.fetch_all(table)
            results.append(check(f"Table: {table}", True))
        except DatabaseConnectionError as e:
            results.append(check(f"Table: {table}", False, str(e)[:80]))
        except Exception as e:
            results.append(check(f"Table: {table}", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# AI Integration checks
# ---------------------------------------------------------------------------

def check_ai_integrations(fast: bool = False) -> list[bool]:
    """Verify Anthropic and OpenAI credentials are valid."""
    header("AI Integrations")
    results = []

    if fast:
        print(f"  [{SKIP}] Skipping AI API calls (--fast mode)")
        return results

    # Anthropic
    try:
        from integrations.anthropic_client import _get_client as get_anthropic_client

        response = get_anthropic_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            system="Respond with just 'ok'",
            messages=[{"role": "user", "content": "say: ok"}],
        )
        text = str(response.content[0].text if response.content else "").strip()
        results.append(check("Anthropic API", bool(text), "claude-haiku-4-5-20251001"))
    except Exception as e:
        results.append(check("Anthropic API", False, str(e)[:80]))

    # OpenAI
    try:
        from integrations.openai_client import _get_client as get_openai_client

        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[
                {"role": "system", "content": "Respond with just 'ok'"},
                {"role": "user", "content": "say: ok"},
            ],
        )
        text = str(response.choices[0].message.content if response.choices else "").strip()
        results.append(check("OpenAI API", bool(text), "gpt-4o-mini"))
    except Exception as e:
        results.append(check("OpenAI API", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# Communications checks
# ---------------------------------------------------------------------------

def check_communications() -> list[bool]:
    """Verify Twilio config is present (no outbound message sent)."""
    header("Communications (Twilio)")
    from config.settings import get_settings

    results = []
    try:
        settings = get_settings()
        sid = settings.twilio_account_sid
        token = settings.twilio_auth_token
        number = settings.twilio_from_number
        valid = (
            bool(sid and sid.startswith("AC") and len(sid) == 34)
            and bool(token and len(token) == 32)
            and bool(number and "+" in number)
        )
        results.append(check("Twilio credentials format", valid, number if valid else "invalid format"))
    except Exception as e:
        results.append(check("Twilio credentials", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# Agent configuration checks
# ---------------------------------------------------------------------------

def check_agents() -> list[bool]:
    """Verify optional agent config is present."""
    header("Agent Configuration")
    from config.settings import get_settings

    results = []
    try:
        settings = get_settings()
        results.append(check("Aria briefing enabled", settings.aria_briefing_enabled))
        results.append(check(
            "Aria briefing timezone",
            bool(settings.aria_briefing_timezone),
            settings.aria_briefing_timezone,
        ))
        results.append(check("Sage monitor enabled", settings.sage_monitor_enabled))
        results.append(check(
            "Sage monitor interval",
            settings.sage_monitor_interval_minutes >= 5,
            f"{settings.sage_monitor_interval_minutes} minutes",
        ))
    except Exception as e:
        results.append(check("Agent config", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# App startup check
# ---------------------------------------------------------------------------

def check_app_starts() -> list[bool]:
    """Verify the FastAPI app initializes without errors."""
    header("Application Startup")
    results = []

    try:
        from fastapi.testclient import TestClient
        from app.api.main import app

        with TestClient(app) as client:
            response = client.get("/health")
            ok = response.status_code == 200
            body = response.json() if ok else {}
            results.append(check("FastAPI app starts", ok, f"status={response.status_code}"))
            if ok:
                overall_status = body.get("status", "unknown")
                db_status = body.get("dependencies", {}).get("supabase", {}).get("status", "unknown")
                results.append(check("Health endpoint overall status", overall_status == "healthy", overall_status))
                results.append(check("Health endpoint database status", db_status == "healthy", db_status))
    except Exception as e:
        results.append(check("FastAPI app starts", False, str(e)[:80]))

    return results


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_checklist(fast: bool = False) -> int:
    """Run all checks and return exit code."""
    print("\n  ORB Platform - Production Deployment Checklist")
    print(f"  Environment: {os.getenv('ENVIRONMENT', 'not set')}")

    all_results: list[bool] = []
    all_results.extend(check_env_vars())
    all_results.extend(check_jwt_strength())
    all_results.extend(check_database())
    all_results.extend(check_ai_integrations(fast=fast))
    all_results.extend(check_communications())
    all_results.extend(check_agents())
    all_results.extend(check_app_starts())

    passed = sum(1 for r in all_results if r)
    failed = sum(1 for r in all_results if not r)
    total = len(all_results)

    header("Summary")
    print(f"  Passed: {passed}/{total}")
    if failed:
        print(f"  Failed: {failed}/{total}")
        print(f"\n  [FAIL] NOT safe to deploy. Fix {failed} issue(s) above.\n")
        return 1

    print(f"\n  [{PASS}] All {total} checks passed. Safe to deploy.\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORB production deployment checklist")
    parser.add_argument("--fast", action="store_true", help="Skip live API calls (faster)")
    args = parser.parse_args()

    sys.exit(run_checklist(fast=args.fast))
