"""Addendum endpoints for safety-first computer use foundation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.computer_use.safety_guard import SafetyGuard

router = APIRouter(prefix="/agents/computer-use", tags=["computer-use"])


class SafetyCheckRequest(BaseModel):
    action: str = Field(min_length=1)
    description: str = ""


@router.get("/status")
def computer_use_status() -> dict[str, str]:
    """Health check for computer-use routes."""
    return {"status": "computer-use routes ready"}


@router.post("/safety-check")
def safety_check(payload: SafetyCheckRequest) -> dict[str, Any]:
    """Validates whether a computer-use action is allowed."""
    try:
        decision = SafetyGuard.evaluate(action=payload.action, description=payload.description)
        return {
            "allowed": decision.allowed,
            "requires_approval": decision.requires_approval,
            "reason": decision.reason,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
