"""Business Profile — Per-Owner Business Identity Engine.

Every owner has a business profile that Commander reads on every conversation.
This is how Commander knows your business name, your customers, your goals,
your tone, and what matters most — so every interaction is uniquely yours.

Owner → Commander: "My business sells high-end real estate in Miami. We close
  about 8 deals a month. My main goal is to grow to 15 deals by Q3."
Commander stores this and uses it in every future response, tool call, and
morning briefing — without the owner ever repeating themselves.

Endpoints:
  GET    /business-profile          — load current profile
  PUT    /business-profile          — create or update full profile
  PATCH  /business-profile          — update specific fields
  DELETE /business-profile          — reset to default
  GET    /business-profile/context  — get AI-ready context string for Commander
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.business_profile")

router = APIRouter(prefix="/business-profile", tags=["Business Profile"])

DEFAULT_PROFILE: dict[str, Any] = {
    "business_name": None,
    "industry": None,
    "business_type": "solo",
    "products_services": None,
    "target_customer": None,
    "avg_deal_size": None,
    "sales_cycle": None,
    "team_size": 1,
    "key_team_members": [],
    "primary_goal": None,
    "secondary_goals": [],
    "current_challenges": None,
    "communication_tone": "professional",
    "response_length": "concise",
    "language": "en",
    "commander_name": "Commander",
    "tracked_metrics": [],
    "kpi_targets": {},
    "automation_rules": [],
    "commander_memory_file": "",
    "platform_tier": "user",
    "is_platform_admin": False,
}


# ─── Models ──────────────────────────────────────────────────────────────────

class BusinessProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    business_type: Optional[str] = None
    founding_year: Optional[int] = None
    website: Optional[str] = None
    location: Optional[str] = None
    products_services: Optional[str] = None
    target_customer: Optional[str] = None
    avg_deal_size: Optional[str] = None
    sales_cycle: Optional[str] = None
    team_size: Optional[int] = None
    key_team_members: Optional[list] = None
    primary_goal: Optional[str] = None
    secondary_goals: Optional[list] = None
    current_challenges: Optional[str] = None
    communication_tone: Optional[str] = None
    response_length: Optional[str] = None
    language: Optional[str] = None
    commander_name: Optional[str] = None
    tracked_metrics: Optional[list] = None
    kpi_targets: Optional[dict] = None
    automation_rules: Optional[list] = None
    commander_memory_file: Optional[str] = None


class MemoryFileUpdate(BaseModel):
    content: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _require_owner(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(owner_id)


def _build_context_string(profile: dict[str, Any]) -> str:
    """Builds a human-readable context block for Commander's system prompt."""
    lines = ["=== OWNER BUSINESS PROFILE ==="]

    if profile.get("business_name"):
        lines.append(f"Business: {profile['business_name']}")
    if profile.get("industry"):
        lines.append(f"Industry: {profile['industry']}")
    if profile.get("business_type"):
        bt_map = {"solo": "Solo operator", "small_team": "Small team", "agency": "Agency", "enterprise": "Enterprise"}
        lines.append(f"Type: {bt_map.get(profile['business_type'], profile['business_type'])}")
    if profile.get("location"):
        lines.append(f"Location: {profile['location']}")
    if profile.get("products_services"):
        lines.append(f"What they sell: {profile['products_services']}")
    if profile.get("target_customer"):
        lines.append(f"Target customer: {profile['target_customer']}")
    if profile.get("avg_deal_size"):
        lines.append(f"Average deal size: {profile['avg_deal_size']}")
    if profile.get("sales_cycle"):
        lines.append(f"Sales cycle: {profile['sales_cycle']}")

    team_size = profile.get("team_size", 1)
    lines.append(f"Team size: {team_size}")

    members = profile.get("key_team_members") or []
    if members:
        member_str = ", ".join(f"{m.get('name', '?')} ({m.get('role', '?')})" for m in members[:5])
        lines.append(f"Key team members: {member_str}")

    if profile.get("primary_goal"):
        lines.append(f"Primary goal: {profile['primary_goal']}")

    sec_goals = profile.get("secondary_goals") or []
    if sec_goals:
        lines.append(f"Secondary goals: {', '.join(str(g) for g in sec_goals[:3])}")

    if profile.get("current_challenges"):
        lines.append(f"Current challenge: {profile['current_challenges']}")

    kpis = profile.get("kpi_targets") or {}
    if kpis:
        kpi_str = ", ".join(f"{k}={v}" for k, v in list(kpis.items())[:5])
        lines.append(f"KPI targets: {kpi_str}")

    metrics = profile.get("tracked_metrics") or []
    if metrics:
        lines.append(f"Always track: {', '.join(str(m) for m in metrics[:6])}")

    tone = profile.get("communication_tone", "professional")
    resp_len = profile.get("response_length", "concise")
    lang = profile.get("language", "en")
    lines.append(f"Communication style: {tone}, {resp_len} responses, language={lang}")

    commander_name = profile.get("commander_name", "Commander")
    lines.append(f"Commander name: {commander_name}")

    auto_rules = profile.get("automation_rules") or []
    if auto_rules:
        lines.append(f"Automation rules ({len(auto_rules)} configured):")
        for rule in auto_rules[:3]:
            trigger = rule.get("trigger", "?")
            action = rule.get("action", "?")
            lines.append(f"  - When {trigger} → {action}")

    memory_file = str(profile.get("commander_memory_file") or "").strip()
    if memory_file:
        lines.append("Commander memory file (always honor):")
        for line in memory_file.splitlines()[:12]:
            trimmed = line.strip()
            if trimmed:
                lines.append(f"  {trimmed[:240]}")

    lines.append("=== END BUSINESS PROFILE ===")
    return "\n".join(lines)


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("")
async def get_profile(request: Request):
    """Load the current owner's business profile. Returns defaults if not set."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        rows = db.client.table("business_profiles") \
            .select("*") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        if rows.data:
            return {"profile": rows.data[0], "has_profile": True}
        # Return default profile shape with no data
        return {"profile": {**DEFAULT_PROFILE, "owner_id": owner_id}, "has_profile": False}
    except Exception as e:
        logger.error(f"Failed to load business profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def upsert_profile(request: Request, body: BusinessProfileUpdate):
    """Create or replace the full business profile."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        data = {k: v for k, v in body.model_dump().items() if v is not None}
        data["owner_id"] = owner_id
        result = db.client.table("business_profiles") \
            .upsert(data, on_conflict="owner_id") \
            .execute()
        return {"profile": result.data[0] if result.data else data, "status": "saved"}
    except Exception as e:
        logger.error(f"Failed to upsert business profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("")
async def patch_profile(request: Request, body: BusinessProfileUpdate):
    """Update specific fields without overwriting the whole profile."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Check if row exists — upsert if not
        existing = db.client.table("business_profiles") \
            .select("id") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()

        updates["owner_id"] = owner_id
        if existing.data:
            result = db.client.table("business_profiles") \
                .update(updates) \
                .eq("owner_id", owner_id) \
                .execute()
        else:
            result = db.client.table("business_profiles") \
                .upsert(updates, on_conflict="owner_id") \
                .execute()

        return {"profile": result.data[0] if result.data else updates, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to patch business profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def reset_profile(request: Request):
    """Delete this owner's business profile and revert to defaults."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        db.client.table("business_profiles") \
            .delete() \
            .eq("owner_id", owner_id) \
            .execute()
        return {"status": "reset"}
    except Exception as e:
        logger.error(f"Failed to reset business profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context")
async def get_context_string(request: Request):
    """Returns an AI-ready context block for use in Commander's system prompt.

    The Commander calls this on every conversation to inject the owner's
    business identity, goals, and preferences.
    """
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        rows = db.client.table("business_profiles") \
            .select("*") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        profile = rows.data[0] if rows.data else {**DEFAULT_PROFILE, "owner_id": owner_id}
        return {
            "context": _build_context_string(profile),
            "commander_name": profile.get("commander_name", "Commander"),
            "communication_tone": profile.get("communication_tone", "professional"),
            "response_length": profile.get("response_length", "concise"),
            "language": profile.get("language", "en"),
        }
    except Exception as e:
        logger.error(f"Failed to build context string: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory-file")
async def get_memory_file(request: Request):
    """Returns the owner's Commander memory file as editable durable context."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        rows = db.client.table("business_profiles") \
            .select("owner_id, commander_memory_file, updated_at") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        if rows.data:
            row = rows.data[0]
            return {
                "owner_id": owner_id,
                "content": str(row.get("commander_memory_file") or ""),
                "updated_at": row.get("updated_at"),
            }
        return {"owner_id": owner_id, "content": "", "updated_at": None}
    except Exception as e:
        logger.error(f"Failed to get commander memory file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/memory-file")
async def put_memory_file(request: Request, body: MemoryFileUpdate):
    """Creates or updates the owner's Commander memory file content."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        data = {
            "owner_id": owner_id,
            "commander_memory_file": body.content,
        }
        result = db.client.table("business_profiles") \
            .upsert(data, on_conflict="owner_id") \
            .execute()
        row = result.data[0] if result.data else data
        return {
            "owner_id": owner_id,
            "content": str(row.get("commander_memory_file") or body.content),
            "updated_at": row.get("updated_at"),
            "status": "saved",
        }
    except Exception as e:
        logger.error(f"Failed to save commander memory file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
