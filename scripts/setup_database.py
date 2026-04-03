"""Schema readiness helper for ORB Supabase database.

This script verifies required tables/columns and prints SQL fixups for missing
pieces. It does not mutate schema automatically because many Supabase projects
restrict direct SQL execution through API clients.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow running this script directly from scripts/ without import errors.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.schema_readiness import SchemaCheck, run_schema_checks


def print_report(checks: list[SchemaCheck]) -> None:
    print("ORB schema readiness report")
    print("=" * 30)
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        print(f"[{marker}] {check.label}")
        print(f"       {check.detail}")
        if (not check.ok) and check.fix_sql:
            print("       Suggested SQL:")
            print(f"       {check.fix_sql}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ORB Supabase schema readiness.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any schema check fails.",
    )
    args = parser.parse_args()

    checks = run_schema_checks()
    print_report(checks)

    has_failure = any(not c.ok for c in checks)
    if args.strict and has_failure:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
