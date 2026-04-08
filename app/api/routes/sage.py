"""Addendum endpoints for Sage starter capabilities."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.sage.sage_brain import SageBrain

router = APIRouter(prefix="/agents/sage", tags=["sage"])
sage_brain = SageBrain()


class SageLearnOutcomesRequest(BaseModel):
    owner_id: str


@router.get("/status")
def sage_status() -> dict[str, str]:
    """Health check for Sage routes."""
    return {"status": "sage routes ready"}


@router.post("/platform-monitor")
def run_platform_monitor() -> dict[str, Any]:
    """Runs Sage S1 platform health monitor on-demand."""
    try:
        return sage_brain.run_platform_monitor()
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/learn-outcomes")
def sage_learn_outcomes(payload: SageLearnOutcomesRequest) -> dict[str, Any]:
    """Runs Sage weekly self-improvement review for this owner."""
    try:
        return sage_brain.learn_from_outcomes(owner_id=payload.owner_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
