"""Create or update the super admin owner account.

Run this once:
    python scripts/create_superadmin.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_settings
from app.database.connection import get_supabase_client
from postgrest.exceptions import APIError


SUPERADMIN_NAME = "Eduardo"


def create_superadmin() -> None:
    settings = get_settings()
    superadmin_email = (getattr(settings, "resolve", None) and settings.resolve("superadmin_email")) or ""
    if not superadmin_email:
        superadmin_email = settings.my_email

    superadmin_email = str(superadmin_email).strip().lower()
    db = get_supabase_client()

    result = db.table("owners").select("*").eq("email", superadmin_email).limit(1).execute()
    now_payload = {
        "role": "superadmin",
        "is_superadmin": True,
        "plan": "superadmin",
        "subscription_plan": "superadmin",
        "spend_limit_cents": 999999999,
        "monthly_cost_override_cents": 0,
        "name": SUPERADMIN_NAME,
    }

    if result.data:
        try:
            db.table("owners").update(now_payload).eq("email", superadmin_email).execute()
            print(f"Updated {superadmin_email} to superadmin")
        except APIError as error:
            if "is_superadmin" in str(error) or "role" in str(error) or "name" in str(error):
                print("Schema not ready for superadmin fields.")
                print("Run scripts/database_migration_patch.sql in Supabase SQL Editor, then re-run this script.")
                raise SystemExit(1)
            raise
    else:
        try:
            db.table("owners").insert({"email": superadmin_email, **now_payload}).execute()
            print(f"Created superadmin: {superadmin_email}")
        except APIError as error:
            if "is_superadmin" in str(error) or "role" in str(error) or "name" in str(error):
                print("Schema not ready for superadmin fields.")
                print("Run scripts/database_migration_patch.sql in Supabase SQL Editor, then re-run this script.")
                raise SystemExit(1)
            raise

    print("Done. Login at /admin with this email.")


if __name__ == "__main__":
    create_superadmin()
