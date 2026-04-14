"""Commander API routes for owner-level orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.commander import CommanderBrain
from app.database.connection import DatabaseConnectionError, SupabaseService
from app.security.action_tokens import create_action_token, verify_and_consume_action_token
from integrations.resend_client import send_resend_email
from integrations.twilio_client import send_sms
from integrations.ws_broadcaster import dispatch_agent_action

router = APIRouter(prefix="/commander", tags=["commander"])
commander_brain = CommanderBrain()

_MEMORY_CHAT_SESSIONS: dict[str, list[dict[str, Any]]] = {}
_MEMORY_CONFIG: dict[str, dict[str, Any]] = {}
_MEMORY_MOBILE_PREFS: dict[str, dict[str, Any]] = {}
_MEMORY_SKILLS_STORE: dict[str, list[dict[str, Any]]] = {}
_MEMORY_FEEDBACK: dict[str, list[dict[str, Any]]] = {}
_CHAT_SESSIONS_DB_AVAILABLE: bool = True


class CommanderMessagePayload(BaseModel):
    """Owner message payload for Commander."""

    message: str = Field(min_length=2)
    owner_id: str = Field(min_length=2)


class CommanderConfigurePayload(BaseModel):
    """Owner customization payload for Commander."""

    owner_id: str = Field(min_length=2)
    commander_name: str | None = None
    personality_style: str | None = None
    briefing_time: str | None = None
    review_day: str | None = None
    language: str | None = None
    communication_style: str | None = None
    proactivity_level: int | None = None
    morning_briefing_enabled: bool | None = None
    weekly_review_enabled: bool | None = None


class MobilePreferencesPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    alerts_enabled: bool = True
    approvals_enabled: bool = True
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class MobileActionLinkPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    action: str = Field(min_length=2)
    payload: dict[str, Any] = Field(default_factory=dict)
    ttl_minutes: int = Field(default=30, ge=1, le=180)


class MobileDispatchAlertPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    message: str = Field(min_length=2)
    include_approval_links: bool = False
    action_payload: dict[str, Any] = Field(default_factory=dict)


class EmailDispatchAlertPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    subject: str = Field(min_length=2)
    message: str = Field(min_length=2)
    include_approval_links: bool = False
    action_payload: dict[str, Any] = Field(default_factory=dict)


def _db() -> SupabaseService | None:
    try:
        return SupabaseService()
    except DatabaseConnectionError:
        return None


def _load_conversation_history(owner_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Loads conversation history from DB when available; otherwise from memory."""
    global _CHAT_SESSIONS_DB_AVAILABLE
    db = _db()
    if db and _CHAT_SESSIONS_DB_AVAILABLE:
        try:
            rows = db.fetch_all("chat_sessions", {"owner_id": owner_id, "agent_role": "commander"})
            rows.sort(key=lambda row: str(row.get("created_at") or ""))
            return [
                {
                    "role": row.get("role") or "owner",
                    "message": row.get("message") or "",
                    "created_at": row.get("created_at") or "",
                }
                for row in rows[-limit:]
            ]
        except DatabaseConnectionError as exc:
            if "chat_sessions" in str(exc).lower():
                _CHAT_SESSIONS_DB_AVAILABLE = False

    cached = _MEMORY_CHAT_SESSIONS.get(owner_id, [])
    return cached[-limit:]


def _save_exchange(owner_id: str, owner_message: str, commander_response: dict[str, Any]) -> None:
    """Saves owner/commander exchange in DB, with in-memory fallback."""
    global _CHAT_SESSIONS_DB_AVAILABLE
    now_iso = datetime.now(timezone.utc).isoformat()
    response_text = str(commander_response.get("response") or "")

    db = _db()
    if db and _CHAT_SESSIONS_DB_AVAILABLE:
        try:
            db.insert_one(
                "chat_sessions",
                {
                    "owner_id": owner_id,
                    "agent_role": "commander",
                    "role": "owner",
                    "message": owner_message,
                    "created_at": now_iso,
                },
            )
            db.insert_one(
                "chat_sessions",
                {
                    "owner_id": owner_id,
                    "agent_role": "commander",
                    "role": "assistant",
                    "message": response_text,
                    "structured_payload": commander_response,
                    "created_at": now_iso,
                },
            )
            return
        except DatabaseConnectionError as exc:
            if "chat_sessions" in str(exc).lower():
                _CHAT_SESSIONS_DB_AVAILABLE = False

    _MEMORY_CHAT_SESSIONS.setdefault(owner_id, []).extend(
        [
            {"role": "owner", "message": owner_message, "created_at": now_iso},
            {"role": "assistant", "message": response_text, "created_at": now_iso},
        ]
    )


def _save_config(payload: CommanderConfigurePayload) -> dict[str, Any]:
    updates = {
        key: value
        for key, value in payload.model_dump().items()
        if key != "owner_id" and value is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No configuration fields provided.")

    db = _db()
    if db:
        try:
            existing = db.fetch_all("commander_config", {"owner_id": payload.owner_id})
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            if existing:
                db.update_many("commander_config", {"owner_id": payload.owner_id}, updates)
            else:
                db.insert_one("commander_config", {"owner_id": payload.owner_id, **updates})
            return {"owner_id": payload.owner_id, **updates}
        except DatabaseConnectionError:
            pass

    current = _MEMORY_CONFIG.get(payload.owner_id, {"owner_id": payload.owner_id})
    current.update(updates)
    _MEMORY_CONFIG[payload.owner_id] = current
    return current


def _normalize_phone(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _find_owner_by_phone(phone_number: str) -> dict[str, Any] | None:
    target = _normalize_phone(phone_number)
    if not target:
        return None

    db = _db()
    if not db:
        return None

    try:
        owners = db.fetch_all("owners", {})
    except DatabaseConnectionError:
        return None

    for owner in owners:
        owner_phone = str(owner.get("phone") or owner.get("phone_number") or "")
        if _normalize_phone(owner_phone) == target:
            return owner
    return None


def _find_owner_by_email(email: str) -> dict[str, Any] | None:
    target = str(email or "").strip().lower()
    if not target:
        return None

    db = _db()
    if not db:
        return None

    try:
        owners = db.fetch_all("owners", {})
    except DatabaseConnectionError:
        return None

    for owner in owners:
        owner_email = str(owner.get("email") or "").strip().lower()
        if owner_email == target:
            return owner
    return None


def _process_owner_mobile_message(owner_id: str, message_body: str) -> dict[str, Any] | None:
    message = (message_body or "").strip()
    if not owner_id or not message:
        return None

    upper = message.upper()
    if upper.startswith("STATUS"):
        context = asyncio.run(commander_brain.gather_full_context(owner_id))
        active = len(context.get("active_agents") or [])
        summary = str(context.get("business_state", {}).get("summary") or "No business summary yet.")
        return {
            "success": True,
            "kind": "status",
            "message": f"Commander status: {active} active agents. {summary}",
            "owner_id": owner_id,
        }

    if upper.startswith("APPROVE ") or upper.startswith("DECLINE "):
        parts = message.split(maxsplit=1)
        decision = parts[0].lower()
        token = parts[1].strip() if len(parts) > 1 else ""
        if not token:
            return {"success": False, "kind": "action", "message": "Missing action token."}
        try:
            decoded = verify_and_consume_action_token(token, expected_action="approval")
        except ValueError as error:
            return {"success": False, "kind": "action", "message": str(error)}
        payload = decoded.get("payload") or {}
        item_label = str(payload.get("label") or payload.get("id") or "item")
        return {
            "success": True,
            "kind": "action",
            "message": f"{decision.title()} recorded for {item_label}.",
            "owner_id": owner_id,
            "decision": decision,
            "action_payload": payload,
        }

    response = commander_brain.process_owner_request(
        owner_message=message,
        owner_id=owner_id,
        conversation_history=_load_conversation_history(owner_id),
        context=asyncio.run(commander_brain.gather_full_context(owner_id)),
    )
    _save_exchange(owner_id, message, response)
    return {
        "success": True,
        "kind": "chat",
        "message": str(response.get("response") or "Commander processed your request."),
        "owner_id": owner_id,
    }


def _save_mobile_prefs(payload: MobilePreferencesPayload) -> dict[str, Any]:
    prefs = payload.model_dump()
    prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = _db()
    if db:
        try:
            existing = db.fetch_all("commander_mobile_prefs", {"owner_id": payload.owner_id})
            if existing:
                db.update_many("commander_mobile_prefs", {"owner_id": payload.owner_id}, prefs)
            else:
                db.insert_one("commander_mobile_prefs", prefs)
            return prefs
        except DatabaseConnectionError:
            pass
    _MEMORY_MOBILE_PREFS[payload.owner_id] = prefs
    return prefs


def _load_mobile_prefs(owner_id: str) -> dict[str, Any]:
    db = _db()
    if db:
        try:
            rows = db.fetch_all("commander_mobile_prefs", {"owner_id": owner_id})
            if rows:
                return rows[0]
        except DatabaseConnectionError:
            pass
    return _MEMORY_MOBILE_PREFS.get(
        owner_id,
        {
            "owner_id": owner_id,
            "alerts_enabled": True,
            "approvals_enabled": True,
            "quiet_hours_start": None,
            "quiet_hours_end": None,
        },
    )


def process_mobile_command(from_number: str, message_body: str) -> dict[str, Any] | None:
    owner = _find_owner_by_phone(from_number)
    if not owner:
        return None

    owner_id = str(owner.get("id") or "")
    return _process_owner_mobile_message(owner_id=owner_id, message_body=message_body)


def process_owner_channel_message(owner_id: str, message_body: str) -> dict[str, Any] | None:
    """Process a channel message when owner_id has already been resolved upstream."""
    if not owner_id:
        return None
    return _process_owner_mobile_message(owner_id=owner_id, message_body=message_body)


def process_owner_email_command(from_email: str, message_body: str) -> dict[str, Any] | None:
    owner = _find_owner_by_email(from_email)
    if not owner:
        return None

    owner_id = str(owner.get("id") or "")
    return _process_owner_mobile_message(owner_id=owner_id, message_body=message_body)


class SkillLearnPayload(BaseModel):
    """Payload for teaching Commander a new skill or preference."""

    owner_id: str = Field(min_length=2)
    skill_name: str = Field(min_length=2)
    skill_type: str = Field(default="preference")  # preference, workflow, integration, knowledge
    description: str = Field(min_length=2)
    trigger_phrases: list[str] = Field(default_factory=list)
    action_template: str = Field(default="")


class FeedbackPayload(BaseModel):
    """Payload for Commander self-improvement feedback."""

    owner_id: str = Field(min_length=2)
    message_id: str = Field(default="")
    rating: int = Field(ge=1, le=5)
    feedback: str = Field(default="")


class CommanderSetupStepUpdatePayload(BaseModel):
    owner_id: str = Field(min_length=2)
    step_key: str = Field(min_length=2)
    done: bool = True


class AIRoutingPreferencesPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    mode: str = Field(pattern="^(platform_default|byok_only|hybrid_fallback)$")
    fallback_to_platform: bool = True
    lock_to_owner_keys: bool = True


def _default_setup_steps() -> list[dict[str, Any]]:
    return [
        {
            "key": "connect_channels",
            "title": "Connect your channels",
            "description": "Link email/SMS/CRM so agents can execute real work.",
            "done": False,
        },
        {
            "key": "set_budget_controls",
            "title": "Set token and cost controls",
            "description": "Define hourly/daily/weekly/monthly caps and PAYG behavior.",
            "done": False,
        },
        {
            "key": "choose_ai_routing",
            "title": "Choose AI routing",
            "description": "Decide between platform default, BYO-only, or hybrid fallback.",
            "done": False,
        },
        {
            "key": "confirm_privacy",
            "title": "Confirm privacy profile",
            "description": "Your workspace memory and learned skills are isolated per owner.",
            "done": False,
        },
    ]


def _get_owner(owner_id: str) -> dict[str, Any]:
    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    try:
        owners = db.fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not owners:
        raise HTTPException(status_code=404, detail="Owner not found.")
    return owners[0]


def _get_ai_routing(owner_id: str) -> dict[str, Any]:
    db = _db()
    default_row = {
        "owner_id": owner_id,
        "mode": "platform_default",
        "fallback_to_platform": True,
        "lock_to_owner_keys": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not db:
        return default_row
    try:
        rows = db.fetch_all("owner_ai_routing_prefs", {"owner_id": owner_id})
        if rows:
            return rows[0]
    except DatabaseConnectionError:
        return default_row
    return default_row


def _save_ai_routing(payload: AIRoutingPreferencesPayload) -> dict[str, Any]:
    db = _db()
    data = {
        "owner_id": payload.owner_id,
        "mode": payload.mode,
        "fallback_to_platform": payload.fallback_to_platform,
        "lock_to_owner_keys": payload.lock_to_owner_keys,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not db:
        return data
    try:
        existing = db.fetch_all("owner_ai_routing_prefs", {"owner_id": payload.owner_id})
        if existing:
            db.update_many("owner_ai_routing_prefs", {"owner_id": payload.owner_id}, data)
        else:
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            db.insert_one("owner_ai_routing_prefs", data)
    except DatabaseConnectionError:
        pass
    return data


def _get_setup_state(owner_id: str) -> dict[str, Any]:
    db = _db()
    default_state = {
        "owner_id": owner_id,
        "completed": False,
        "steps": _default_setup_steps(),
    }
    if not db:
        return default_state
    try:
        rows = db.fetch_all("commander_onboarding_state", {"owner_id": owner_id})
        if rows:
            row = rows[0]
            return {
                "owner_id": owner_id,
                "completed": bool(row.get("completed") or False),
                "steps": row.get("steps") or _default_setup_steps(),
            }
    except DatabaseConnectionError:
        return default_state
    return default_state


def _save_setup_state(owner_id: str, steps: list[dict[str, Any]], completed: bool) -> dict[str, Any]:
    db = _db()
    payload = {
        "owner_id": owner_id,
        "steps": steps,
        "completed": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not db:
        return payload
    try:
        existing = db.fetch_all("commander_onboarding_state", {"owner_id": owner_id})
        if existing:
            db.update_many("commander_onboarding_state", {"owner_id": owner_id}, payload)
        else:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
            db.insert_one("commander_onboarding_state", payload)
    except DatabaseConnectionError:
        pass
    return payload


# ─── History & Skills Endpoints ──────────────────────────────────────────────


@router.get("/history/{owner_id}")
def commander_history(owner_id: str, limit: int = 30) -> dict[str, Any]:
    """Returns persisted conversation history for frontend hydration."""
    history = _load_conversation_history(owner_id, limit=min(limit, 50))
    return {
        "owner_id": owner_id,
        "history": history,
        "count": len(history),
    }


@router.post("/skills/learn")
def commander_learn_skill(payload: SkillLearnPayload) -> dict[str, Any]:
    """Teaches Commander a new skill or preference that persists across sessions."""
    db = _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    skill_data = {
        "owner_id": payload.owner_id,
        "skill_name": payload.skill_name,
        "skill_type": payload.skill_type,
        "description": payload.description,
        "trigger_phrases": payload.trigger_phrases,
        "action_template": payload.action_template,
        "learned_at": now_iso,
        "usage_count": 0,
        "active": True,
    }

    if db:
        try:
            db.insert_one("commander_skills", skill_data)
        except DatabaseConnectionError:
            pass

    # Also store in memory for immediate use
    _MEMORY_SKILLS = _MEMORY_SKILLS_STORE.setdefault(payload.owner_id, [])
    _MEMORY_SKILLS.append(skill_data)

    return {"status": "learned", "skill": skill_data}


@router.get("/skills/{owner_id}")
def commander_skills_list(owner_id: str) -> dict[str, Any]:
    """Lists all skills Commander has learned for this owner."""
    db = _db()
    skills: list[dict[str, Any]] = []

    if db:
        try:
            skills = db.fetch_all("commander_skills", {"owner_id": owner_id})
        except DatabaseConnectionError:
            pass

    if not skills:
        skills = _MEMORY_SKILLS_STORE.get(owner_id, [])

    return {"owner_id": owner_id, "skills": skills, "count": len(skills)}


@router.post("/feedback")
def commander_feedback(payload: FeedbackPayload) -> dict[str, Any]:
    """Records feedback on Commander responses for self-improvement."""
    db = _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    feedback_data = {
        "owner_id": payload.owner_id,
        "message_id": payload.message_id,
        "rating": payload.rating,
        "feedback": payload.feedback,
        "created_at": now_iso,
    }

    if db:
        try:
            db.insert_one("commander_feedback", feedback_data)
        except DatabaseConnectionError:
            pass

    _MEMORY_FEEDBACK.setdefault(payload.owner_id, []).append(feedback_data)

    return {"status": "recorded", "feedback": feedback_data}


@router.get("/profile/{owner_id}")
def commander_profile(owner_id: str) -> dict[str, Any]:
    """Returns Commander's full profile: config + skills count + feedback stats."""
    db = _db()
    config: dict[str, Any] = {}
    skills_count = 0
    avg_rating = 0.0

    if db:
        try:
            configs = db.fetch_all("commander_config", {"owner_id": owner_id})
            if configs:
                config = configs[0]
        except DatabaseConnectionError:
            pass
        try:
            skills = db.fetch_all("commander_skills", {"owner_id": owner_id})
            skills_count = len(skills)
        except DatabaseConnectionError:
            pass
        try:
            feedbacks = db.fetch_all("commander_feedback", {"owner_id": owner_id})
            if feedbacks:
                ratings = [int(f.get("rating") or 0) for f in feedbacks]
                avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        except DatabaseConnectionError:
            pass

    if not config:
        config = _MEMORY_CONFIG.get(owner_id, {})
    if not skills_count:
        skills_count = len(_MEMORY_SKILLS_STORE.get(owner_id, []))

    return {
        "owner_id": owner_id,
        "config": config,
        "skills_count": skills_count,
        "avg_rating": avg_rating,
        "self_improvement_active": True,
    }


@router.post("/message")
def commander_message(payload: CommanderMessagePayload) -> dict[str, Any]:
    """Owner chats with Commander and receives one unified response."""

    # ── Auto-skill detection: if owner says "remember" / "learn" etc ──
    auto_skill = commander_brain.detect_auto_skill(payload.message, payload.owner_id)

    history = _load_conversation_history(payload.owner_id, limit=20)
    context = asyncio.run(commander_brain.gather_full_context(payload.owner_id))

    response = commander_brain.process_owner_request(
        owner_message=payload.message,
        owner_id=payload.owner_id,
        conversation_history=history,
        context=context,
    )

    _save_exchange(payload.owner_id, payload.message, response)

    dispatch_agent_action(
        agent_id="commander",
        agent_name=str(response.get("commander_name") or "Commander"),
        action_type="commander_response",
        message=str(response.get("summary_for_activity_log") or "Commander responded to owner."),
        outcome="completed",
    )

    result = {
        **response,
        "owner_id": payload.owner_id,
        "history_count": len(history),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if auto_skill:
        result["skill_learned"] = auto_skill.get("skill_name", "")
        result["auto_learn"] = True

    return result


@router.post("/self-improve/{owner_id}")
def commander_self_improve(owner_id: str) -> dict[str, Any]:
    """Triggers Commander self-improvement cycle from feedback data.

    Analyzes all collected feedback, identifies behavior patterns,
    and auto-generates new skills/preferences.
    """
    result = commander_brain.self_improve(owner_id)
    return result


@router.get("/ai-providers")
def commander_ai_providers() -> dict[str, Any]:
    """Returns which AI providers are available and their status."""
    from config.settings import get_settings
    settings = get_settings()

    providers = {
        "anthropic": {
            "name": "Claude (Anthropic)",
            "available": settings.is_configured("anthropic_api_key"),
            "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-6"],
            "cost": "paid",
            "default_for": "Commander brain, complex analysis",
        },
        "groq": {
            "name": "Groq (Llama/Mixtral)",
            "available": settings.is_configured("groq_api_key"),
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
            "cost": "free",
            "default_for": "Simple decisions, data extraction, health checks",
        },
        "google": {
            "name": "Gemini (Google)",
            "available": settings.is_configured("google_ai_api_key"),
            "models": ["gemini-2.0-flash"],
            "cost": "free",
            "default_for": "Content generation, summarization fallback",
        },
        "openai": {
            "name": "GPT (OpenAI)",
            "available": settings.is_configured("openai_api_key"),
            "models": ["gpt-4o-mini"],
            "cost": "paid",
            "default_for": "Alternative general-purpose AI",
        },
    }

    available_count = sum(1 for p in providers.values() if p["available"])
    free_count = sum(1 for p in providers.values() if p["available"] and p["cost"] == "free")

    return {
        "providers": providers,
        "available_count": available_count,
        "free_providers": free_count,
        "recommendation": (
            "Anthropic is your primary provider. Add GROQ_API_KEY (free) for $0 simple tasks."
            if not providers["groq"]["available"]
            else "Multi-provider routing active. Groq handles free tasks, Claude handles complex ones."
        ),
    }


@router.get("/briefing/{owner_id}")
async def commander_briefing(owner_id: str) -> dict[str, Any]:
    """Returns the owner's morning briefing, generating it on-demand."""
    briefing = await commander_brain.morning_briefing(owner_id)
    return {"owner_id": owner_id, "briefing": briefing, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/context/{owner_id}")
def commander_context(owner_id: str) -> dict[str, Any]:
    """Returns the latest full Commander context snapshot for dashboard use."""
    snapshot = asyncio.run(commander_brain.gather_full_context(owner_id))
    return snapshot


@router.post("/configure")
def commander_configure(payload: CommanderConfigurePayload) -> dict[str, Any]:
    """Updates owner-specific Commander preferences immediately."""
    saved = _save_config(payload)
    return {"status": "configured", "config": saved, "updated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/mobile/preferences")
def commander_mobile_preferences(payload: MobilePreferencesPayload) -> dict[str, Any]:
    saved = _save_mobile_prefs(payload)
    return {"status": "configured", "preferences": saved}


@router.get("/mobile/preferences/{owner_id}")
def commander_mobile_preferences_get(owner_id: str) -> dict[str, Any]:
    return {"owner_id": owner_id, "preferences": _load_mobile_prefs(owner_id)}


@router.post("/mobile/action-link")
def commander_mobile_action_link(payload: MobileActionLinkPayload) -> dict[str, Any]:
    token = create_action_token(
        owner_id=payload.owner_id,
        action=payload.action,
        payload=payload.payload,
        ttl_minutes=payload.ttl_minutes,
    )
    return {
        "owner_id": payload.owner_id,
        "action": payload.action,
        "token": token,
        "expires_in_minutes": payload.ttl_minutes,
    }


@router.post("/mobile/dispatch-alert")
def commander_mobile_dispatch_alert(payload: MobileDispatchAlertPayload) -> dict[str, Any]:
    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    try:
        owners = db.fetch_all("owners", {"id": payload.owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not owners:
        raise HTTPException(status_code=404, detail="Owner not found.")

    owner_phone = str(owners[0].get("phone") or owners[0].get("phone_number") or "").strip()
    if not owner_phone:
        raise HTTPException(status_code=400, detail="Owner phone number is missing.")

    message = payload.message
    if payload.include_approval_links:
        approve = create_action_token(payload.owner_id, "approval", {**payload.action_payload, "decision": "approve"})
        decline = create_action_token(payload.owner_id, "approval", {**payload.action_payload, "decision": "decline"})
        message = (
            f"{message}\n"
            f"Reply APPROVE {approve} to approve.\n"
            f"Reply DECLINE {decline} to decline."
        )

    sms_result = send_sms(to=owner_phone, message=message)
    return {"status": "sent", "owner_id": payload.owner_id, "sms": sms_result}


@router.post("/email/dispatch-alert")
def commander_email_dispatch_alert(payload: EmailDispatchAlertPayload) -> dict[str, Any]:
    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    try:
        owners = db.fetch_all("owners", {"id": payload.owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not owners:
        raise HTTPException(status_code=404, detail="Owner not found.")

    owner_email = str(owners[0].get("email") or "").strip()
    if not owner_email:
        raise HTTPException(status_code=400, detail="Owner email is missing.")

    message = payload.message
    if payload.include_approval_links:
        approve = create_action_token(payload.owner_id, "approval", {**payload.action_payload, "decision": "approve"})
        decline = create_action_token(payload.owner_id, "approval", {**payload.action_payload, "decision": "decline"})
        message = (
            f"{message}\n\n"
            "To approve, reply with this subject line:\n"
            f"APPROVE {approve}\n\n"
            "To decline, reply with this subject line:\n"
            f"DECLINE {decline}"
        )

    # Simple html conversion keeps plaintext semantics and improves readability in mail clients.
    html = "<br>".join(message.splitlines())
    email_result = send_resend_email(to_email=owner_email, subject=payload.subject, html=html)
    return {"status": "sent", "owner_id": payload.owner_id, "email": email_result}


@router.get("/ai-routing/{owner_id}")
def commander_ai_routing(owner_id: str) -> dict[str, Any]:
    """Returns how this owner wants AI calls to route between BYO and platform keys."""
    _get_owner(owner_id)
    prefs = _get_ai_routing(owner_id)
    return {
        "owner_id": owner_id,
        "preferences": prefs,
        "modes": [
            {
                "key": "platform_default",
                "label": "Platform default brain",
                "summary": "Use ORB-managed keys and billing by default.",
            },
            {
                "key": "byok_only",
                "label": "Bring your own API only",
                "summary": "Use only your connected API keys. No platform fallback.",
            },
            {
                "key": "hybrid_fallback",
                "label": "Hybrid fallback",
                "summary": "Use your keys first, then fallback to ORB PAYG when your quota is exhausted.",
            },
        ],
    }


@router.post("/ai-routing/{owner_id}")
def commander_ai_routing_update(owner_id: str, payload: AIRoutingPreferencesPayload) -> dict[str, Any]:
    """Updates owner AI routing preference between default/BYOK/hybrid."""
    if payload.owner_id != owner_id:
        raise HTTPException(status_code=400, detail="Owner mismatch in routing payload.")
    _get_owner(owner_id)
    saved = _save_ai_routing(payload)
    return {"status": "updated", "owner_id": owner_id, "preferences": saved}


@router.get("/onboarding-setup/{owner_id}")
def commander_onboarding_setup(owner_id: str) -> dict[str, Any]:
    """Second-stage Commander onboarding guide shown after platform onboarding."""
    _get_owner(owner_id)
    setup = _get_setup_state(owner_id)
    routing = _get_ai_routing(owner_id)
    return {
        "owner_id": owner_id,
        "completed": setup.get("completed", False),
        "steps": setup.get("steps", []),
        "ai_routing": routing,
        "policy": {
            "default_brain": "ORB provides a managed AI brain by default so users can start immediately.",
            "byok_behavior": "If you connect your own API keys, you can choose BYOK-only or hybrid fallback.",
            "fallback_behavior": "In hybrid mode, usage attempts your key first; when quota/rate limits are hit, ORB can continue with PAYG if enabled.",
            "privacy": "Owner memory, skills, chat history, and automation context are isolated per owner_id and are never shared across workspaces.",
        },
    }


@router.post("/onboarding-setup/{owner_id}/step")
def commander_onboarding_setup_step(owner_id: str, payload: CommanderSetupStepUpdatePayload) -> dict[str, Any]:
    """Marks a specific Commander setup step as done/undone."""
    if payload.owner_id != owner_id:
        raise HTTPException(status_code=400, detail="Owner mismatch in setup payload.")
    _get_owner(owner_id)
    state = _get_setup_state(owner_id)
    steps = list(state.get("steps") or _default_setup_steps())
    updated = False
    for idx, step in enumerate(steps):
        if str(step.get("key") or "") == payload.step_key:
            steps[idx] = {**step, "done": payload.done}
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Setup step not found.")
    completed = all(bool(step.get("done")) for step in steps)
    saved = _save_setup_state(owner_id, steps, completed)
    return {"status": "updated", "state": saved}


@router.post("/onboarding-setup/{owner_id}/complete")
def commander_onboarding_setup_complete(owner_id: str) -> dict[str, Any]:
    """Completes Commander second-stage onboarding for this owner."""
    _get_owner(owner_id)
    state = _get_setup_state(owner_id)
    steps = [
        {**step, "done": True}
        for step in (state.get("steps") or _default_setup_steps())
    ]
    saved = _save_setup_state(owner_id, steps, True)
    return {"status": "completed", "state": saved}
