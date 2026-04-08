"""Shared schema-readiness checks for setup, onboarding gates, and scripts."""

from __future__ import annotations

from dataclasses import dataclass

from app.database.connection import DatabaseConnectionError, SupabaseService


@dataclass
class SchemaCheck:
    label: str
    ok: bool
    detail: str
    fix_sql: str = ""


def run_schema_checks() -> list[SchemaCheck]:
    try:
        db = SupabaseService()
    except DatabaseConnectionError as exc:
        return [
            SchemaCheck(
                label="database_connection",
                ok=False,
                detail=f"Unable to connect to Supabase: {exc}",
            )
        ]

    checks: list[SchemaCheck] = []

    try:
        db.client.table("activity_log").select("id,metadata").limit(1).execute()
        checks.append(
            SchemaCheck(
                label="activity_log.metadata",
                ok=True,
                detail="Column exists and can be queried.",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            SchemaCheck(
                label="activity_log.metadata",
                ok=False,
                detail=f"Missing or unreadable metadata column: {exc}",
                fix_sql=(
                    "ALTER TABLE public.activity_log "
                    "ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;"
                ),
            )
        )

    try:
        db.client.table("owner_integrations").select("owner_id,integration_key,status").limit(1).execute()
        checks.append(
            SchemaCheck(
                label="owner_integrations table",
                ok=True,
                detail="Table exists and core columns are readable.",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            SchemaCheck(
                label="owner_integrations table",
                ok=False,
                detail=f"Missing or unreadable table/columns: {exc}",
                fix_sql=(
                    "CREATE TABLE IF NOT EXISTS public.owner_integrations (\n"
                    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "  owner_id text NOT NULL,\n"
                    "  integration_key text NOT NULL,\n"
                    "  status text NOT NULL DEFAULT 'pending',\n"
                    "  connection_mode text NOT NULL DEFAULT 'skip',\n"
                    "  connected_at timestamptz,\n"
                    "  created_at timestamptz NOT NULL DEFAULT now(),\n"
                    "  updated_at timestamptz NOT NULL DEFAULT now(),\n"
                    "  UNIQUE(owner_id, integration_key)\n"
                    ");"
                ),
            )
        )

    return checks


def schema_readiness_payload() -> dict[str, object]:
    checks = run_schema_checks()
    return {
        "ready": all(check.ok for check in checks),
        "checks": [
            {
                "label": check.label,
                "ok": check.ok,
                "detail": check.detail,
                "fix_sql": check.fix_sql,
            }
            for check in checks
        ],
    }
