"""CLI preflight gate for local startup and CI-style checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runtime.preflight import build_preflight_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORB full preflight checks.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when blockers exist.")
    parser.add_argument("--json", action="store_true", help="Print report as JSON.")
    args = parser.parse_args()

    report = build_preflight_report()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ORB preflight report")
        print("=" * 24)
        print(f"Ready: {report.get('ready')}")
        print(f"Score: {report.get('score')}")
        summary = report.get("summary", {})
        print(f"Blockers: {summary.get('blocker_count', 0)}")
        print(f"Warnings: {summary.get('warning_count', 0)}")

        blockers = report.get("blockers", [])
        warnings = report.get("warnings", [])
        if blockers:
            print("\nBlockers:")
            for item in blockers:
                print(f"- {item.get('code')}: {item.get('message')}")
                print(f"  action: {item.get('action')}")
        if warnings:
            print("\nWarnings:")
            for item in warnings:
                print(f"- {item.get('code')}: {item.get('message')}")
                print(f"  action: {item.get('action')}")

    if args.strict and not report.get("ready", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
