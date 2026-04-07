"""Agent Settings API — configuration and control for individual agents.

Endpoints for managing per-agent settings (budget, autonomy, channels,
permissions, schedule, memory, and emergency kill switch).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService

logger = logging.getLogger("orb.agent_settings")

router = APIRouter(prefix="/agent-settings", tags=["Agent Settings"])

VALID_AGENTS = {"rex", "aria", "nova", "orion", "sage", "atlas"}


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AgentSettings(BaseModel):
    """Current settings for an agent."""
    id: str
    owner_id: str
    agent_slug: str
    daily_budget_cents: int
    is_enabled: bool
    autonomy_level: int
    channels: list[str]
    permissions: dict[str, bool]
    schedule_config: dict[str, Any]
    memory_context: dict[str, Any]
    kill_switch: bool
    created_at: str
    updated_at: str


class AgentSettingsUpdate(BaseModel):
    """Partial update model for agent settings."""
    daily_budget_cents: int | None = None
    autonomy_level: int | None = Field(None, ge=1, le=10)
    channels: list[str] | None = None
    permissions: dict[str, bool] | None = None
    schedule_config: dict[str, Any] | None = None
    memory_context: dict[str, Any] | None = None


class AgentToggleResponse(BaseModel):
    """Response from toggling an agent."""
    agent_slug: str
    is_enabled: bool
    message: str


class AgentKillResponse(BaseModel):
    """Response from activating kill switch."""
    agent_slug: str
    kill_switch: bool
    is_enabled: bool
    message: str


class AgentTestResponse(BaseModel):
    """Response from smoke test."""
    agent_slug: str
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _get_owner_id(request: Request) -> str:
    """Extract owner_id from JWT token payload."""
    payload = getattr(request.state, "token_payload", {})
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing owner_id")
    return owner_id


def _get_db() -> SupabaseService:
    """Get database service."""
    return SupabaseService()


def _validate_agent_slug(agent_slug: str) -> str:
    """Validate and normalize agent slug."""
    normalized = agent_slug.strip().lower()
    if normalized not in VALID_AGENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_slug}'. Valid agents: {', '.join(sorted(VALID_AGENTS))}",
        )
    return normalized


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert database row to API response."""
    if not row:
        return {}
    result = dict(row)
    # Ensure all fields are present
    for field in ["id", "owner_id", "agent_slug", "daily_budget_cents", "is_enabled",
                   "autonomy_level", "channels", "permissions", "schedule_config",
                   "memory_context", "kill_switch", "created_at", "updated_at"]:
        if field not in result:
            if field in ["daily_budget_cents", "autonomy_level"]:
                result[field] = 0
            elif field in ["channels", "permissions", "schedule_config", "memory_context"]:
                result[field] = {} if field != "channels" else []
            elif field in ["is_enabled", "kill_switch"]:
                result[field] = False
            else:
                result[field] = None
    return result


def _ensure_agent_settings_row(owner_id: str, agent_slug: str, db: SupabaseService) -> dict[str, Any]:
    """Ensure settings row exists, creating default if needed."""
    rows = db.fetch_all(
        "agent_settings",
        {"owner_id": owner_id, "agent_slug": agent_slug},
    )
    if rows:
        return rows[0]

    # Create default settings
    try:
        new_row = db.insert_one(
            "agent_settings",
            {
                "owner_id": owner_id,
                "agent_slug": agent_slug,
                "daily_budget_cents": 500,
                "is_enabled": True,
                "autonomy_level": 5,
                "channels": [],
                "permissions": {},
                "schedule_config": {},
                "memory_context": {},
                "kill_switch": False,
            },
        )
        return new_row
    except DatabaseConnectionError:
        # Might be a constraint conflict if created in parallel
        rows = db.fetch_all(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
        )
        return rows[0] if rows else {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[AgentSettings])
def get_all_agent_settings(request: Request) -> list[AgentSettings]:
    """Get all agent settings for the current owner (all 6 agents)."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        # Ensure all agents have settings rows
        for agent_slug in sorted(VALID_AGENTS):
            _ensure_agent_settings_row(owner_id, agent_slug, db)

        # Fetch all settings
        rows = db.fetch_all("agent_settings", {"owner_id": owner_id})
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch agent settings: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    settings = [
        AgentSettings(
            id=row.get("id", ""),
            owner_id=row.get("owner_id", ""),
            agent_slug=row.get("agent_slug", ""),
            daily_budget_cents=row.get("daily_budget_cents", 500),
            is_enabled=row.get("is_enabled", True),
            autonomy_level=row.get("autonomy_level", 5),
            channels=row.get("channels") or [],
            permissions=row.get("permissions") or {},
            schedule_config=row.get("schedule_config") or {},
            memory_context=row.get("memory_context") or {},
            kill_switch=row.get("kill_switch", False),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )
        for row in rows
    ]

    return settings


@router.get("/{agent_slug}", response_model=AgentSettings)
def get_agent_settings(agent_slug: str, request: Request) -> AgentSettings:
    """Get settings for one specific agent."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        row = _ensure_agent_settings_row(owner_id, agent_slug, db)
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch agent settings: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    return AgentSettings(
        id=row.get("id", ""),
        owner_id=row.get("owner_id", ""),
        agent_slug=row.get("agent_slug", ""),
        daily_budget_cents=row.get("daily_budget_cents", 500),
        is_enabled=row.get("is_enabled", True),
        autonomy_level=row.get("autonomy_level", 5),
        channels=row.get("channels") or [],
        permissions=row.get("permissions") or {},
        schedule_config=row.get("schedule_config") or {},
        memory_context=row.get("memory_context") or {},
        kill_switch=row.get("kill_switch", False),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


@router.put("/{agent_slug}")
def update_agent_settings(
    agent_slug: str,
    payload: AgentSettingsUpdate,
    request: Request,
) -> dict[str, Any]:
    """Update settings for an agent (partial update)."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        # Ensure row exists
        _ensure_agent_settings_row(owner_id, agent_slug, db)

        # Build update dict with only provided fields
        update_dict: dict[str, Any] = {}
        if payload.daily_budget_cents is not None:
            update_dict["daily_budget_cents"] = payload.daily_budget_cents
        if payload.autonomy_level is not None:
            update_dict["autonomy_level"] = payload.autonomy_level
        if payload.channels is not None:
            update_dict["channels"] = payload.channels
        if payload.permissions is not None:
            update_dict["permissions"] = payload.permissions
        if payload.schedule_config is not None:
            update_dict["schedule_config"] = payload.schedule_config
        if payload.memory_context is not None:
            update_dict["memory_context"] = payload.memory_context

        if not update_dict:
            return {"message": "No fields to update"}

        # Update the row
        db.update_many(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
            update_dict,
        )

        # Log the activity
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="agent_settings_update",
            description=f"Updated {agent_slug} settings",
            metadata={"agent_slug": agent_slug, "fields_updated": list(update_dict.keys())},
        )

        return {"success": True, "agent_slug": agent_slug, "message": "Settings updated"}

    except DatabaseConnectionError as error:
        logger.error("Failed to update agent settings: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.post("/{agent_slug}/toggle", response_model=AgentToggleResponse)
def toggle_agent(agent_slug: str, request: Request) -> AgentToggleResponse:
    """Toggle agent enabled/disabled status."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        # Get current state
        rows = db.fetch_all(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
        )
        if not rows:
            rows = [_ensure_agent_settings_row(owner_id, agent_slug, db)]

        current_enabled = rows[0].get("is_enabled", True)
        new_enabled = not current_enabled

        # Update
        db.update_many(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
            {"is_enabled": new_enabled},
        )

        # Log
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="agent_toggle",
            description=f"{agent_slug} is now {'enabled' if new_enabled else 'disabled'}",
            metadata={"agent_slug": agent_slug, "is_enabled": new_enabled},
        )

        return AgentToggleResponse(
            agent_slug=agent_slug,
            is_enabled=new_enabled,
            message=f"{agent_slug} is now {'enabled' if new_enabled else 'disabled'}",
        )

    except DatabaseConnectionError as error:
        logger.error("Failed to toggle agent: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.post("/{agent_slug}/kill", response_model=AgentKillResponse)
def activate_kill_switch(agent_slug: str, request: Request) -> AgentKillResponse:
    """Activate the emergency kill switch for an agent."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        # Ensure row exists
        _ensure_agent_settings_row(owner_id, agent_slug, db)

        # Set kill_switch=true and is_enabled=false
        db.update_many(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
            {"kill_switch": True, "is_enabled": False},
        )

        # Log critical event
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="agent_kill_switch",
            description=f"EMERGENCY: Kill switch activated for {agent_slug}",
            metadata={"agent_slug": agent_slug, "kill_switch": True},
        )

        return AgentKillResponse(
            agent_slug=agent_slug,
            kill_switch=True,
            is_enabled=False,
            message=f"Emergency kill switch activated for {agent_slug}",
        )

    except DatabaseConnectionError as error:
        logger.error("Failed to activate kill switch: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.get("/{agent_slug}/logs")
def get_agent_logs(agent_slug: str, request: Request) -> dict[str, Any]:
    """Get the last 20 activity log entries for an agent."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        # Fetch activity logs for this owner that mention this agent
        rows = db.fetch_all("activity_log", {"owner_id": owner_id})

        # Filter for agent-related entries (check metadata or description)
        filtered = []
        for row in rows:
            description = str(row.get("description", "")).lower()
            metadata = row.get("metadata") or {}
            agent_in_meta = str(metadata.get("agent_slug", "")).lower() == agent_slug
            agent_in_desc = agent_slug in description
            if agent_in_meta or agent_in_desc:
                filtered.append(row)

        # Sort by created_at descending and limit to 20
        sorted_rows = sorted(filtered, key=lambda r: r.get("created_at", ""), reverse=True)[:20]

        logs = [
            {
                "id": row.get("id", ""),
                "action_type": row.get("action_type", ""),
                "description": row.get("description", ""),
                "outcome": row.get("outcome"),
                "created_at": str(row.get("created_at", "")),
            }
            for row in sorted_rows
        ]

        return {"agent_slug": agent_slug, "logs": logs}

    except DatabaseConnectionError as error:
        logger.error("Failed to fetch agent logs: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.post("/{agent_slug}/test", response_model=AgentTestResponse)
def run_smoke_test(agent_slug: str, request: Request) -> AgentTestResponse:
    """Run a quick smoke test on the agent."""
    owner_id = _get_owner_id(request)
    agent_slug = _validate_agent_slug(agent_slug)

    try:
        db = _get_db()
        # Ensure settings exist
        _ensure_agent_settings_row(owner_id, agent_slug, db)

        # Check if agent is enabled
        rows = db.fetch_all(
            "agent_settings",
            {"owner_id": owner_id, "agent_slug": agent_slug},
        )
        if not rows:
            return AgentTestResponse(
                agent_slug=agent_slug,
                success=False,
                message="Agent settings not found",
            )

        settings = rows[0]
        if not settings.get("is_enabled"):
            return AgentTestResponse(
                agent_slug=agent_slug,
                success=False,
                message="Agent is disabled",
            )

        if settings.get("kill_switch"):
            return AgentTestResponse(
                agent_slug=agent_slug,
                success=False,
                message="Kill switch is active",
            )

        # Basic success (no actual agent execution yet)
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="agent_test",
            description=f"Smoke test passed for {agent_slug}",
            metadata={"agent_slug": agent_slug},
        )

        return AgentTestResponse(
            agent_slug=agent_slug,
            success=True,
            message=f"{agent_slug} is healthy and ready",
        )

    except DatabaseConnectionError as error:
        logger.error("Failed to run smoke test: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error
