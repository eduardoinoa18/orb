"""Nova social scheduling helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.database.connection import SupabaseService


def queue_content(content_id: str, scheduled_for_iso: str) -> dict:
    """Marks a content item as queued for future publishing."""
    db = SupabaseService()
    rows = db.update_many(
        "content",
        {"id": content_id},
        {
            "status": "queued",
            "scheduled_for": scheduled_for_iso,
        },
    )
    return rows[0] if rows else {"id": content_id, "status": "queued"}


def mark_content_published(content_id: str) -> dict:
    """Marks a content item as published right now."""
    db = SupabaseService()
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = db.update_many(
        "content",
        {"id": content_id},
        {
            "status": "published",
            "published_at": now_iso,
        },
    )
    return rows[0] if rows else {"id": content_id, "status": "published", "published_at": now_iso}
