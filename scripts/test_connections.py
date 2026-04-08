"""Level 1 startup checks for ORB external services and database access.

Run with:
    python scripts/test_connections.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

# Allow running this script directly from scripts/ without import errors.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.claude_client import ping_claude
from integrations.openai_client import ask_gpt_mini
from app.database.connection import SupabaseService


def _print_result(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")


def check_supabase_connection(db: SupabaseService) -> tuple[bool, str]:
    try:
        db.select("owners", {})
        return True, "Supabase reachable"
    except Exception as error:
        return False, str(error)


def check_claude() -> tuple[bool, str]:
    try:
        result = ping_claude()
        return True, f"Claude replied: {result.get('response', '').strip()}"
    except Exception as error:
        return False, str(error)


def check_openai() -> tuple[bool, str]:
    try:
        result = ask_gpt_mini(prompt="Reply with exactly: hello", max_tokens=8)
        return True, f"OpenAI replied: {(result.get('text') or '').strip()}"
    except Exception as error:
        return False, str(error)


def check_tables_exist(db: SupabaseService) -> tuple[bool, str]:
    tables = [
        "owners",
        "agents",
        "activity_log",
        "leads",
        "paper_trades",
        "strategies",
        "tasks",
        "content",
        "trades",
    ]
    try:
        for table in tables:
            db.select(table, {})
        return True, f"Validated {len(tables)} tables"
    except Exception as error:
        return False, str(error)


def check_write_activity_log(db: SupabaseService) -> tuple[bool, str]:
    try:
        row = db.log_activity(
            agent_id=None,
            owner_id=None,
            action_type="connection_test",
            description="Write test from scripts/test_connections.py",
            cost_cents=0,
        )
        return True, f"Inserted id={row.get('id', 'unknown')}"
    except Exception as error:
        return False, str(error)


def check_read_activity_log(db: SupabaseService) -> tuple[bool, str]:
    try:
        rows = db.select("activity_log", {"action_type": "connection_test"})
        return True, f"Read {len(rows)} rows"
    except Exception as error:
        return False, str(error)


def main() -> None:
    print("ORB Level 1 Connection Test")
    print(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    print("-" * 60)

    db = SupabaseService()
    checks = [
        ("Supabase connection", lambda: check_supabase_connection(db)),
        ("Anthropic API (send hello)", check_claude),
        ("OpenAI API (send hello)", check_openai),
        ("Database tables exist", lambda: check_tables_exist(db)),
        ("Can write to activity_log", lambda: check_write_activity_log(db)),
        ("Can read from activity_log", lambda: check_read_activity_log(db)),
    ]

    passed = 0
    for label, fn in checks:
        ok, detail = fn()
        _print_result(label, ok, detail)
        if ok:
            passed += 1

    print("-" * 60)
    print(f"Total: {passed}/6 services connected")


if __name__ == "__main__":
    main()
