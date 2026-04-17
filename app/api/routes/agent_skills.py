"""Agent skills routes for adaptive skill profiles and manual reviews."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agents.skill_engine import AGENT_CORE_SKILLS, AgentSkillEngine, UNIVERSAL_SKILLS
from app.security.guard import validate_owner_id

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])


class SkillReviewRequest(BaseModel):
    """Request payload for manual skill review."""

    lookback_days: int = Field(default=7, ge=1, le=90)


def _require_owner_id(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return validate_owner_id(owner_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _normalize_slug(slug: str) -> str:
    normalized = str(slug or "").strip().lower()
    if normalized not in AGENT_CORE_SKILLS:
        raise HTTPException(status_code=404, detail=f"Unknown agent slug: {slug}")
    return normalized


@router.get("/{slug}")
async def get_agent_skills(slug: str, request: Request) -> dict[str, object]:
    """Get the skill profile for one agent and the current owner."""
    owner_id = _require_owner_id(request)
    agent_slug = _normalize_slug(slug)

    engine = AgentSkillEngine()
    engine.agent_slug = agent_slug
    profile = engine.load_skill_profile(owner_id)

    skills_info = {
        skill: UNIVERSAL_SKILLS.get(skill, "")
        for skill in (profile.core_skills + profile.expanded_skills + profile.pending_skills)
    }

    return {
        "agent_slug": agent_slug,
        "owner_id": owner_id,
        "core_skills": profile.core_skills,
        "expanded_skills": profile.expanded_skills,
        "pending_skills": profile.pending_skills,
        "skill_scores": profile.skill_scores,
        "business_adaptations": profile.business_adaptations,
        "last_review": profile.last_review.isoformat() if profile.last_review else None,
        "skill_context": engine.build_skill_context(owner_id),
        "skills_info": skills_info,
    }


@router.post("/{slug}/review")
async def run_agent_skill_review(slug: str, body: SkillReviewRequest, request: Request) -> dict[str, object]:
    """Trigger a manual skill review for one agent and the current owner."""
    owner_id = _require_owner_id(request)
    agent_slug = _normalize_slug(slug)

    engine = AgentSkillEngine()
    engine.agent_slug = agent_slug
    result = engine.run_skill_review(owner_id=owner_id, lookback_days=body.lookback_days)

    return {
        "agent_slug": agent_slug,
        "owner_id": owner_id,
        "lookback_days": body.lookback_days,
        "result": result,
    }
