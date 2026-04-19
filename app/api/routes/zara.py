"""Zara — Customer Success & Onboarding API routes."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agents.zara.zara_brain import ZaraBrain
from app.database.connection import SupabaseService

router = APIRouter(prefix="/zara", tags=["zara"])
logger = logging.getLogger("orb.routes.zara")

_CRON_KEY_ENV = "ORB_CRON_SECRET"

_brain: ZaraBrain | None = None


def _get_brain() -> ZaraBrain:
    global _brain
    if _brain is None:
        _brain = ZaraBrain()
    return _brain


def _require_admin_or_cron(request: Request, cron_key: str | None = None) -> bool:
    """Allow either ORB_CRON_SECRET or an admin JWT from request state."""
    expected_cron = os.environ.get(_CRON_KEY_ENV, "")
    if expected_cron and cron_key == expected_cron:
        return True

    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SupabaseService()
        rows = (
            db.client.table("business_profiles")
            .select("is_platform_admin")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        if rows.data and rows.data[0].get("is_platform_admin"):
            return True

        owner_rows = (
            db.client.table("owners")
            .select("role,is_superadmin")
            .eq("id", owner_id)
            .limit(1)
            .execute()
        )
        if owner_rows.data:
            row = owner_rows.data[0]
            if bool(row.get("is_superadmin")) or str(row.get("role", "")).lower() in {"superadmin", "admin"}:
                return True
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="Platform admin access required")


# ── Pydantic models ────────────────────────────────────────────────────────

class ChatPayload(BaseModel):
    owner_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class OnboardingInitPayload(BaseModel):
    owner_id: str = Field(min_length=1)
    business_profile: dict[str, Any] = Field(default_factory=dict)


class StepCompletePayload(BaseModel):
    owner_id: str = Field(min_length=1)
    step_key: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)


class NPSResponsePayload(BaseModel):
    owner_id: str = Field(min_length=1)
    score: int = Field(ge=0, le=10)
    comment: str = Field(default="", max_length=2000)


# ── Chat ────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def zara_chat(payload: ChatPayload) -> dict[str, Any]:
    """Chat with Zara about success, onboarding, or account health."""
    brain = _get_brain()
    return brain.chat(
        owner_id=payload.owner_id,
        message=payload.message,
        context=payload.context,
    )


# ── Onboarding ───────────────────────────────────────────────────────────────

@router.post("/onboarding/start")
async def start_onboarding(payload: OnboardingInitPayload) -> dict[str, Any]:
    """Initialize the onboarding flow for a new owner."""
    brain = _get_brain()
    return brain.start_onboarding(
        owner_id=payload.owner_id,
        business_profile=payload.business_profile,
    )


@router.get("/onboarding/{owner_id}")
async def get_onboarding_status(owner_id: str) -> dict[str, Any]:
    """Get current onboarding progress for an owner."""
    brain = _get_brain()
    return brain.get_onboarding_status(owner_id)


@router.post("/onboarding/step")
async def complete_step(payload: StepCompletePayload) -> dict[str, Any]:
    """Mark an onboarding step complete and get next step guidance."""
    brain = _get_brain()
    return brain.complete_onboarding_step(
        owner_id=payload.owner_id,
        step_key=payload.step_key,
        data=payload.data,
    )


# ── Health & Churn ───────────────────────────────────────────────────────────

@router.get("/health/{owner_id}")
async def get_health_score(owner_id: str) -> dict[str, Any]:
    """Get the health score for an owner."""
    brain = _get_brain()
    return brain.tracker.get_health_score(owner_id)


@router.get("/churn-risk/{owner_id}")
async def get_churn_risk(owner_id: str) -> dict[str, Any]:
    """Run a full churn risk analysis for an owner."""
    brain = _get_brain()
    return brain.analyze_churn_risk(owner_id)


# ── NPS ─────────────────────────────────────────────────────────────────────

@router.post("/nps/send/{owner_id}")
async def send_nps_survey(owner_id: str) -> dict[str, Any]:
    """Dispatch an NPS survey to an owner."""
    brain = _get_brain()
    return brain.send_nps_survey(owner_id)


@router.post("/nps/respond")
async def record_nps_response(payload: NPSResponsePayload) -> dict[str, Any]:
    """Record an owner's NPS response."""
    brain = _get_brain()
    return brain.record_nps_response(
        owner_id=payload.owner_id,
        score=payload.score,
        comment=payload.comment,
    )


@router.get("/nps/summary")
async def get_nps_summary() -> dict[str, Any]:
    """Get platform-wide NPS summary (admin only)."""
    brain = _get_brain()
    return brain.get_nps_summary()


# ── Weekly Review ─────────────────────────────────────────────────────────────

@router.post("/review/weekly")
async def run_weekly_review() -> dict[str, Any]:
    """Trigger Zara's weekly platform success review (admin/cron)."""
    brain = _get_brain()
    return brain.run_weekly_success_review()


@router.post("/check-ins/send")
async def send_weekly_check_ins(
    request: Request,
    cron_key: str | None = Query(None),
    dry_run: bool = Query(False),
    max_accounts: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """Trigger Zara's at-risk owner check-ins (admin JWT or cron key)."""
    _require_admin_or_cron(request, cron_key)
    brain = _get_brain()
    return brain.send_at_risk_check_ins(dry_run=dry_run, max_accounts=max_accounts)
