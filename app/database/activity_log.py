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
) -> dict[str, Any]:
    """
    Writes a single activity log entry to the database.

    Args:
        agent_id:       UUID of the agent that performed the action (can be None
                        for platform-level events like startup checks)
        action_type:    Short category tag: "sms", "call", "claude", "trade",
                        "email", "lead", "task", "error"
        description:    Human-readable description of what happened
        outcome:        Optional result: "sent", "failed", "approved", "rejected"
        cost_cents:     Estimated cost in US cents (1 cent = $0.01)
        needs_approval: Set True for actions that require your review before
                        they go through (e.g. drafting an email to send)

    Returns the inserted database row as a dict.
    Logs a warning and returns a partial dict if the database is not yet set up.
    """
    payload: dict[str, Any] = {
        "action_type": action_type,
        "description": description,
        "cost_cents": cost_cents,
        "needs_approval": needs_approval,
    }

    if agent_id:
        payload["agent_id"] = agent_id
    if outcome:
        payload["outcome"] = outcome
    if request_id:
        payload["request_id"] = request_id

    try:
        db = SupabaseService()
        row = db.insert_one("activity_log", payload)
        logger.info(
            "Activity logged — type=%s cost=%d¢ needs_approval=%s",
            action_type, cost_cents, needs_approval,
        )
        return row
    except DatabaseConnectionError as error:
        # Don't crash the whole request just because logging failed.
        # This can happen if Supabase isn't connected yet.
        logger.warning("Failed to log activity to database: %s", error)
        return {**payload, "id": None, "warning": "Database not connected — log not saved"}


def get_recent_activity(
    agent_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Returns the most recent activity log entries, newest first.

    Args:
        agent_id:  Filter to a specific agent's activity (None = all agents)
        limit:     Maximum number of rows to return

    Returns a list of activity log dicts.
    """
    try:
        db = SupabaseService()
        filters = {"agent_id": agent_id} if agent_id else {}
        rows = db.fetch_all("activity_log", filters)
        # Sort newest first (Supabase doesn't guarantee order without ORDER BY)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]
    except DatabaseConnectionError as error:
        logger.warning("Failed to fetch activity log: %s", error)
        return []
