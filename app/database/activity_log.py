"""Activity log helpers for ORB.

Every action an agent takes — SMS sent, call placed, Claude called, trade
evaluated — is written to the activity_log table using these helpers.

This gives you a complete audit trail of everything your agents do, including
cost tracking so you can see exactly what each agent costs per day.
"""

import logging
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService

logger = logging.getLogger("orb.activity_log")


def log_activity(
    agent_id: str | None,
    action_type: str,
    description: str,
    outcome: str | None = None,
    cost_cents: int = 0,
    needs_approval: bool = False,
    request_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """
    Writes a single activity log entry to the database.

    Routes through SupabaseService.log_activity() so that background tasks
    (schedulers, Aria, Sage) automatically resolve an owner_id via the
    fallback lookup when none is explicitly supplied.

    Args:
        agent_id:       UUID of the agent (None for platform-level events)
        action_type:    Short tag: "sms", "call", "claude", "trade", "error"
        description:    Human-readable description of what happened
        outcome:        Optional result: "sent", "failed", "approved"
        cost_cents:     Estimated cost in US cents
        needs_approval: True if this action requires owner review
        request_id:     HTTP request ID for tracing (optional)
        owner_id:       Explicit owner_id — if None the fallback resolver is used
    """
    try:
        db = SupabaseService()
        metadata: dict[str, Any] | None = {"request_id": request_id} if request_id else None
        row = db.log_activity(
            agent_id=agent_id,
            owner_id=owner_id,
            action_type=action_type,
            description=description,
            cost_cents=cost_cents,
            outcome=outcome,
            needs_approval=needs_approval,
            metadata=metadata,
        )
        return row
    except DatabaseConnectionError as error:
        logger.warning("Failed to log activity to database: %s", error)
        return {
            "action_type": action_type,
            "description": description,
            "id": None,
            "warning": "Database not connected — log not saved",
        }


def get_recent_activity(
    agent_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Returns the most recent activity log entries, newest first.

    Args:
        agent_id:  Filter to a specific agent's activity (None = all agents)
        limit:     Maximum number of rows to return
    """
    try:
        db = SupabaseService()
        filters = {"agent_id": agent_id} if agent_id else {}
        rows = db.fetch_all("activity_log", filters)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]
    except DatabaseConnectionError as error:
        logger.warning("Failed to fetch activity log: %s", error)
        return []
