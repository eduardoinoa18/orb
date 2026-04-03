"""Addendum endpoints for token optimization and efficiency reporting."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from integrations.token_optimizer import TokenOptimizer

router = APIRouter(prefix="/agents/optimizer", tags=["optimizer"])
optimizer = TokenOptimizer()


class OptimizePromptRequest(BaseModel):
    prompt: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    max_budget_cents: int = Field(default=5, ge=1, le=50)
    agent_id: str | None = None
    is_critical: bool = False


@router.get("/status")
def optimizer_status() -> dict[str, str]:
    """Health check for token optimizer addendum routes."""
    return {"status": "optimizer routes ready"}


@router.post("/optimize")
def optimize_prompt(payload: OptimizePromptRequest) -> dict[str, Any]:
    """Runs token optimizer pre-check and returns model/token recommendation."""
    try:
        result = optimizer.optimize_prompt(
            prompt=payload.prompt,
            task_type=payload.task_type,
            max_budget_cents=payload.max_budget_cents,
            agent_id=payload.agent_id,
            is_critical=payload.is_critical,
        )
        return {
            "optimized_prompt": result.optimized_prompt,
            "selected_model": result.selected_model,
            "max_tokens": result.max_tokens,
            "used_cache": result.used_cache,
            "cache_key": result.cache_key,
            "needs_ai": result.needs_ai,
            "bypass_reason": result.bypass_reason,
            "cached_result": result.cached_result,
            "budget_mode": result.budget_mode,
            "should_defer": result.should_defer,
            "daily_budget_cents": result.daily_budget_cents,
            "spent_today_cents": result.spent_today_cents,
            "remaining_budget_cents": result.remaining_budget_cents,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/efficiency")
def efficiency_report(agent_id: str, period_days: int = 7) -> dict[str, Any]:
    """Returns per-agent token/cost efficiency snapshot."""
    try:
        return optimizer.track_agent_efficiency(agent_id=agent_id, period_days=period_days)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
