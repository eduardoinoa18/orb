"""Commander Settings API — configuration for the AI command center.

Endpoints for managing Commander personality, communication style, automation
rules, briefing schedules, and training feedback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService

logger = logging.getLogger("orb.commander_settings")

router = APIRouter(prefix="/commander", tags=["Commander"])


def _default_commander_config(owner_id: str) -> CommanderConfig:
    """Safe fallback config when persistence is unavailable."""
    return CommanderConfig(
        id="",
        owner_id=owner_id,
        commander_name="Max",
        personality_style="professional",
        communication_style="concise",
        proactivity_level=7,
        morning_briefing_enabled=True,
        briefing_time="07:00",
        weekly_review_enabled=True,
        review_day="sunday",
        language="en",
        safe_mode=False,
        autonomy_level=5,
        channel_preferences={},
        approval_rules={},
        created_at="",
        updated_at="",
    )


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class CommanderConfig(BaseModel):
    """Current Commander configuration for an owner."""
    id: str
    owner_id: str
    commander_name: str
    personality_style: str
    communication_style: str
    proactivity_level: int
    morning_briefing_enabled: bool
    briefing_time: str
    weekly_review_enabled: bool
    review_day: str
    language: str
    safe_mode: bool
    autonomy_level: int
    channel_preferences: dict[str, bool]
    approval_rules: dict[str, Any]
    created_at: str
    updated_at: str


class CommanderSettingsUpdate(BaseModel):
    """Partial update model for Commander settings."""
    commander_name: str | None = None
    personality_style: str | None = None
    communication_style: str | None = None
    proactivity_level: int | None = Field(None, ge=1, le=10)
    morning_briefing_enabled: bool | None = None
    briefing_time: str | None = None
    weekly_review_enabled: bool | None = None
    review_day: str | None = None
    language: str | None = None
    safe_mode: bool | None = None
    autonomy_level: int | None = Field(None, ge=1, le=10)
    channel_preferences: dict[str, bool] | None = None
    approval_rules: dict[str, Any] | None = None


class PersonaPreview(BaseModel):
    """Commander persona and system prompt preview."""
    commander_name: str
    personality_style: str
    communication_style: str
    proactivity_level: int
    system_prompt_preview: str


class TrainingFeedback(BaseModel):
    """Training feedback for Commander fine-tuning."""
    response_text: str
    rating: int = Field(..., ge=1, le=5)
    feedback_notes: str | None = None


class BriefingPreview(BaseModel):
    """Preview of today's briefing without sending."""
    title: str
    content: str
    estimated_read_time_minutes: int


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


def _ensure_commander_config_row(owner_id: str, db: SupabaseService) -> dict[str, Any]:
    """Ensure Commander config row exists, creating defaults if needed."""
    rows = db.fetch_all("commander_config", {"owner_id": owner_id})
    if rows:
        return rows[0]

    # Create default config
    try:
        new_row = db.insert_one(
            "commander_config",
            {
                "owner_id": owner_id,
                "commander_name": "Max",
                "personality_style": "professional",
                "communication_style": "concise",
                "proactivity_level": 7,
                "morning_briefing_enabled": True,
                "briefing_time": "07:00",
                "weekly_review_enabled": True,
                "review_day": "sunday",
                "language": "en",
                "safe_mode": False,
                "autonomy_level": 5,
                "channel_preferences": {},
                "approval_rules": {},
            },
        )
        return new_row
    except DatabaseConnectionError:
        # Might have been created in parallel
        rows = db.fetch_all("commander_config", {"owner_id": owner_id})
        return rows[0] if rows else {}


def _build_system_prompt(config: dict[str, Any]) -> str:
    """Generate system prompt from Commander configuration."""
    name = config.get("commander_name", "Max")
    personality = config.get("personality_style", "professional")
    communication = config.get("communication_style", "concise")
    proactivity = config.get("proactivity_level", 7)

    style_desc = {
        "professional": "formal, respectful, data-driven",
        "friendly": "approachable, warm, conversational",
        "analytical": "detailed, thorough, quantitative",
        "creative": "innovative, imaginative, forward-thinking",
    }.get(personality, "professional")

    comm_desc = {
        "concise": "brief and to-the-point",
        "detailed": "comprehensive and thorough",
        "casual": "relaxed and informal",
        "formal": "structured and formal",
    }.get(communication, "concise")

    prompt = (
        f"You are {name}, the Commander AI for this platform. "
        f"Your personality is {style_desc}. "
        f"Your communication style is {comm_desc}. "
        f"Your proactivity level is {proactivity}/10 (more = more initiative). "
        f"You manage AI agents, monitor integrations, and brief the owner on important events. "
        f"Be helpful, clear, and always prioritize the owner's goals and safety."
    )

    return prompt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=CommanderConfig)
def get_commander_settings(request: Request) -> CommanderConfig:
    """Get current Commander configuration for the owner."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        row = _ensure_commander_config_row(owner_id, db)
        if not isinstance(row, dict):
            logger.warning("Commander config row had unexpected type: %s", type(row))
            return _default_commander_config(owner_id)
    except DatabaseConnectionError as error:
        logger.warning("Failed to fetch Commander settings, returning defaults: %s", error)
        return _default_commander_config(owner_id)

    channel_preferences = row.get("channel_preferences")
    approval_rules = row.get("approval_rules")

    proactivity_level = row.get("proactivity_level")
    if not isinstance(proactivity_level, int):
        proactivity_level = 7

    autonomy_level = row.get("autonomy_level")
    if not isinstance(autonomy_level, int):
        autonomy_level = 5

    morning_briefing_enabled = row.get("morning_briefing_enabled")
    if not isinstance(morning_briefing_enabled, bool):
        morning_briefing_enabled = True

    weekly_review_enabled = row.get("weekly_review_enabled")
    if not isinstance(weekly_review_enabled, bool):
        weekly_review_enabled = True

    safe_mode = row.get("safe_mode")
    if not isinstance(safe_mode, bool):
        safe_mode = False

    return CommanderConfig(
        id=row.get("id", ""),
        owner_id=row.get("owner_id") or owner_id,
        commander_name=row.get("commander_name") or "Max",
        personality_style=row.get("personality_style") or "professional",
        communication_style=row.get("communication_style") or "concise",
        proactivity_level=proactivity_level,
        morning_briefing_enabled=morning_briefing_enabled,
        briefing_time=row.get("briefing_time") or "07:00",
        weekly_review_enabled=weekly_review_enabled,
        review_day=row.get("review_day") or "sunday",
        language=row.get("language") or "en",
        safe_mode=safe_mode,
        autonomy_level=autonomy_level,
        channel_preferences=channel_preferences if isinstance(channel_preferences, dict) else {},
        approval_rules=approval_rules if isinstance(approval_rules, dict) else {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


@router.put("/settings")
def update_commander_settings(
    payload: CommanderSettingsUpdate,
    request: Request,
) -> dict[str, Any]:
    """Update Commander settings (partial update)."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        # Ensure row exists
        _ensure_commander_config_row(owner_id, db)

        # Build update dict with only provided fields
        update_dict: dict[str, Any] = {}
        if payload.commander_name is not None:
            update_dict["commander_name"] = payload.commander_name
        if payload.personality_style is not None:
            update_dict["personality_style"] = payload.personality_style
        if payload.communication_style is not None:
            update_dict["communication_style"] = payload.communication_style
        if payload.proactivity_level is not None:
            update_dict["proactivity_level"] = payload.proactivity_level
        if payload.morning_briefing_enabled is not None:
            update_dict["morning_briefing_enabled"] = payload.morning_briefing_enabled
        if payload.briefing_time is not None:
            update_dict["briefing_time"] = payload.briefing_time
        if payload.weekly_review_enabled is not None:
            update_dict["weekly_review_enabled"] = payload.weekly_review_enabled
        if payload.review_day is not None:
            update_dict["review_day"] = payload.review_day
        if payload.language is not None:
            update_dict["language"] = payload.language
        if payload.safe_mode is not None:
            update_dict["safe_mode"] = payload.safe_mode
        if payload.autonomy_level is not None:
            update_dict["autonomy_level"] = payload.autonomy_level
        if payload.channel_preferences is not None:
            update_dict["channel_preferences"] = payload.channel_preferences
        if payload.approval_rules is not None:
            update_dict["approval_rules"] = payload.approval_rules

        if not update_dict:
            return {"message": "No fields to update"}

        # Update the row
        db.update_many(
            "commander_config",
            {"owner_id": owner_id},
            update_dict,
        )

        # Log the activity
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="commander_settings_update",
            description="Updated Commander configuration",
            metadata={"fields_updated": list(update_dict.keys())},
        )

        return {"success": True, "message": "Commander settings updated"}

    except DatabaseConnectionError as error:
        logger.error("Failed to update Commander settings: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.post("/settings/reset")
def reset_commander_settings(request: Request) -> dict[str, Any]:
    """Reset Commander settings to defaults."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        # Reset to defaults
        db.update_many(
            "commander_config",
            {"owner_id": owner_id},
            {
                "commander_name": "Max",
                "personality_style": "professional",
                "communication_style": "concise",
                "proactivity_level": 7,
                "morning_briefing_enabled": True,
                "briefing_time": "07:00",
                "weekly_review_enabled": True,
                "review_day": "sunday",
                "language": "en",
                "safe_mode": False,
                "autonomy_level": 5,
                "channel_preferences": {},
                "approval_rules": {},
            },
        )

        # Log the activity
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="commander_reset",
            description="Reset Commander to default settings",
        )

        return {"success": True, "message": "Commander settings reset to defaults"}

    except DatabaseConnectionError as error:
        logger.error("Failed to reset Commander settings: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.get("/persona", response_model=PersonaPreview)
def get_commander_persona(request: Request) -> PersonaPreview:
    """Get current Commander persona and system prompt preview."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        row = _ensure_commander_config_row(owner_id, db)
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch Commander persona: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    prompt = _build_system_prompt(row)

    return PersonaPreview(
        commander_name=row.get("commander_name", "Max"),
        personality_style=row.get("personality_style", "professional"),
        communication_style=row.get("communication_style", "concise"),
        proactivity_level=row.get("proactivity_level", 7),
        system_prompt_preview=prompt,
    )


@router.post("/train")
def submit_training_feedback(
    payload: TrainingFeedback,
    request: Request,
) -> dict[str, Any]:
    """Submit feedback example for Commander fine-tuning."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        # Log as training feedback
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="commander_training",
            description=f"Training feedback submitted (rating: {payload.rating}/5)",
            metadata={
                "response_text": payload.response_text[:500],  # Truncate for logging
                "rating": payload.rating,
                "feedback_notes": payload.feedback_notes or "",
            },
        )

        return {
            "success": True,
            "message": "Training feedback recorded",
            "rating": payload.rating,
        }

    except DatabaseConnectionError as error:
        logger.error("Failed to store training feedback: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error


@router.get("/briefing/preview", response_model=BriefingPreview)
def get_briefing_preview(request: Request) -> BriefingPreview:
    """Generate a preview of today's briefing without sending."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        # Fetch Commander config
        _ensure_commander_config_row(owner_id, db)

        # Fetch recent activity for today
        rows = db.fetch_all("activity_log", {"owner_id": owner_id})

        # Filter for today's activities
        today = datetime.now(timezone.utc).date()
        today_activities = []
        for row in rows:
            created_at = row.get("created_at")
            if created_at:
                try:
                    row_date = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
                    if row_date == today:
                        today_activities.append(row)
                except (ValueError, TypeError):
                    pass

        # Build preview content
        content_lines = ["# Daily Briefing", f"Date: {today.isoformat()}", ""]

        if today_activities:
            content_lines.append(f"## Today's Activity ({len(today_activities)} events)")
            content_lines.append("")
            for idx, activity in enumerate(today_activities[:5], 1):
                desc = activity.get("description", "No description")
                cost = activity.get("cost_cents", 0)
                content_lines.append(f"{idx}. {desc} (Cost: ${cost/100:.2f})")
            if len(today_activities) > 5:
                content_lines.append(f"... and {len(today_activities) - 5} more")
        else:
            content_lines.append("No significant activity today.")

        content_lines.append("")
        content_lines.append("---")
        content_lines.append("This is a preview of your briefing. Check back later for updates.")

        content = "\n".join(content_lines)
        read_time = max(1, len(content) // 200)  # Rough estimate

        return BriefingPreview(
            title=f"Daily Briefing for {today.isoformat()}",
            content=content,
            estimated_read_time_minutes=read_time,
        )

    except DatabaseConnectionError as error:
        logger.error("Failed to generate briefing preview: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error
