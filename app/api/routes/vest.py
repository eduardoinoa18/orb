"""Vest — Investment & Portfolio API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agents.vest.vest_brain import VestBrain

router = APIRouter(prefix="/vest", tags=["vest"])
logger = logging.getLogger("orb.routes.vest")

_brain: VestBrain | None = None


def _get_brain() -> VestBrain:
    global _brain
    if _brain is None:
        _brain = VestBrain()
    return _brain


# ── Pydantic models ────────────────────────────────────────────────────────

class ChatPayload(BaseModel):
    owner_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class AddHoldingPayload(BaseModel):
    owner_id: str
    ticker: str = Field(min_length=1, max_length=12)
    asset_type: str = Field(default="stock", pattern="^(stock|etf|crypto|real_estate|bond|alternative|other)$")
    quantity: float = Field(gt=0)
    avg_cost: float = Field(gt=0)
    notes: str = Field(default="", max_length=1000)


class UpdateHoldingPayload(BaseModel):
    owner_id: str
    ticker: str
    quantity: float = Field(gt=0)
    avg_cost: float | None = None


class RemoveHoldingPayload(BaseModel):
    owner_id: str
    ticker: str


class MemoPayload(BaseModel):
    owner_id: str
    ticker: str
    position_type: str = Field(default="long", pattern="^(long|short|watch)$")


class ComparePayload(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=6)
    asset_type: str = Field(default="stock")


# ── Chat ────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def vest_chat(payload: ChatPayload) -> dict[str, Any]:
    """Chat with Vest about investments, portfolio, or research."""
    brain = _get_brain()
    return brain.chat(owner_id=payload.owner_id, message=payload.message, context=payload.context)


# ── Portfolio ────────────────────────────────────────────────────────────────

@router.post("/portfolio/add")
async def add_holding(payload: AddHoldingPayload) -> dict[str, Any]:
    """Add a holding to the portfolio."""
    brain = _get_brain()
    return brain.add_holding(
        owner_id=payload.owner_id, ticker=payload.ticker,
        asset_type=payload.asset_type, quantity=payload.quantity,
        avg_cost=payload.avg_cost, notes=payload.notes,
    )


@router.post("/portfolio/update")
async def update_holding(payload: UpdateHoldingPayload) -> dict[str, Any]:
    """Update a portfolio holding."""
    brain = _get_brain()
    return brain.update_holding(
        owner_id=payload.owner_id, ticker=payload.ticker,
        quantity=payload.quantity, avg_cost=payload.avg_cost,
    )


@router.delete("/portfolio/remove")
async def remove_holding(payload: RemoveHoldingPayload) -> dict[str, Any]:
    """Remove a holding from the portfolio."""
    brain = _get_brain()
    return brain.remove_holding(owner_id=payload.owner_id, ticker=payload.ticker)


@router.get("/portfolio/{owner_id}")
async def get_portfolio(owner_id: str) -> dict[str, Any]:
    """Get full portfolio with P&L."""
    brain = _get_brain()
    return brain.get_portfolio(owner_id)


@router.get("/portfolio/{owner_id}/rebalance")
async def check_rebalancing(owner_id: str) -> dict[str, Any]:
    """Check rebalancing needs for a portfolio."""
    brain = _get_brain()
    return brain.check_rebalancing_needs(owner_id)


# ── Research ─────────────────────────────────────────────────────────────────

@router.get("/research/{ticker}")
async def research_asset(ticker: str, asset_type: str = "stock") -> dict[str, Any]:
    """Research a single asset."""
    brain = _get_brain()
    return brain.research_asset(ticker=ticker.upper(), asset_type=asset_type)


@router.post("/research/compare")
async def compare_assets(payload: ComparePayload) -> dict[str, Any]:
    """Compare multiple assets."""
    brain = _get_brain()
    return brain.compare_assets(tickers=payload.tickers, asset_type=payload.asset_type)


@router.get("/research/opportunities/{owner_id}")
async def scan_opportunities(owner_id: str) -> dict[str, Any]:
    """Scan for investment opportunities based on current portfolio."""
    brain = _get_brain()
    return brain.scan_opportunities(owner_id)


# ── Memos ─────────────────────────────────────────────────────────────────────

@router.post("/memo")
async def write_investment_memo(payload: MemoPayload) -> dict[str, Any]:
    """Generate a structured investment memo for a ticker."""
    brain = _get_brain()
    return brain.write_investment_memo(
        owner_id=payload.owner_id,
        ticker=payload.ticker,
        position_type=payload.position_type,
    )


@router.post("/thesis/{owner_id}")
async def write_portfolio_thesis(owner_id: str) -> dict[str, Any]:
    """Generate an overall portfolio thesis document."""
    brain = _get_brain()
    return brain.write_portfolio_thesis(owner_id)


# ── Reports ─────────────────────────────────────────────────────────────────

@router.get("/report/{owner_id}")
async def get_performance_report(owner_id: str) -> dict[str, Any]:
    """Get portfolio performance report with AI commentary."""
    brain = _get_brain()
    return brain.get_performance_report(owner_id)


@router.post("/digest/{owner_id}")
async def weekly_portfolio_digest(owner_id: str) -> dict[str, Any]:
    """Generate and push weekly portfolio digest to Commander inbox."""
    brain = _get_brain()
    return brain.run_weekly_portfolio_digest(owner_id)
