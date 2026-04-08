"""Orion paper trader and strategy research routes (Level 8)."""

from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agents.orion.orion_brain import OrionBrain
from app.database.connection import DatabaseConnectionError

router = APIRouter(prefix="/agents/orion", tags=["orion"])
orion_brain = OrionBrain()


class OrionIngestRequest(BaseModel):
    agent_id: str
    strategy_name: str
    notes: str = Field(min_length=10)
    source_trader: str | None = None


class OrionScanRequest(BaseModel):
    agent_id: str
    symbols: list[str] = Field(default_factory=lambda: ["ES", "NQ"], min_length=1, max_length=20)
    timeframe: str = "5m"


class OrionPaperTradeTestRequest(BaseModel):
    agent_id: str
    instrument: str = Field(min_length=1, max_length=20)
    direction: Literal["long", "short"] = "long"
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    account_balance: float = Field(default=50000, gt=0)
    risk_percent: float = Field(default=1.0, gt=0, le=5)


class OrionSmokeRunRequest(BaseModel):
    agent_id: str | None = None
    strategy_name: str = "ORB Level 8 Momentum"
    source_trader: str = "orb-dashboard-smoke"
    notes: str | None = Field(default=None, min_length=10)
    symbols: list[str] = Field(default_factory=lambda: ["ES", "NQ"], min_length=1, max_length=20)
    timeframe: str = "5m"
    days: int = Field(default=14, ge=1, le=90)


class OrionLearnOutcomesRequest(BaseModel):
    owner_id: str


def _validate_timeframe(timeframe: str) -> str:
    allowed = {"1m", "5m", "15m", "1h", "4h", "1d"}
    if timeframe not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid timeframe '{timeframe}'. Allowed values: {allowed_list}.",
        )
    return timeframe


def _validate_trade_geometry(payload: OrionPaperTradeTestRequest) -> None:
    if payload.direction == "long":
        if not payload.stop_loss < payload.entry_price:
            raise HTTPException(status_code=422, detail="For long trades, stop_loss must be below entry_price.")
        if not payload.take_profit > payload.entry_price:
            raise HTTPException(status_code=422, detail="For long trades, take_profit must be above entry_price.")
        return

    if not payload.stop_loss > payload.entry_price:
        raise HTTPException(status_code=422, detail="For short trades, stop_loss must be above entry_price.")
    if not payload.take_profit < payload.entry_price:
        raise HTTPException(status_code=422, detail="For short trades, take_profit must be below entry_price.")


@router.get("/status")
def orion_status() -> dict[str, str]:
    """Health check for Orion routes."""
    return {"status": "orion router ready"}


@router.post("/ingest")
def ingest_strategy(payload: OrionIngestRequest) -> dict[str, Any]:
    """Ingests trader notes into a structured strategy row."""
    try:
        return orion_brain.ingest_strategy(
            agent_id=payload.agent_id,
            strategy_name=payload.strategy_name,
            notes=payload.notes,
            source_trader=payload.source_trader,
        )
    except HTTPException:
        raise
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/scan")
def scan_market(payload: OrionScanRequest) -> dict[str, Any]:
    """Runs a market scan and returns candidate setups."""
    try:
        timeframe = _validate_timeframe(payload.timeframe)
        return orion_brain.scan_market(
            agent_id=payload.agent_id,
            symbols=payload.symbols,
            timeframe=timeframe,
        )
    except HTTPException:
        raise
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/paper-trade/test")
def run_paper_trade_test(payload: OrionPaperTradeTestRequest) -> dict[str, Any]:
    """Runs a risk-aware paper trade simulation and persists it."""
    try:
        _validate_trade_geometry(payload)
        return orion_brain.run_paper_trade_test(
            agent_id=payload.agent_id,
            instrument=payload.instrument,
            direction=payload.direction,
            entry_price=payload.entry_price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            account_balance=payload.account_balance,
            risk_percent=payload.risk_percent,
        )
    except HTTPException:
        raise
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/smoke-run")
def run_orion_smoke(payload: OrionSmokeRunRequest) -> dict[str, Any]:
    """Runs a full Orion smoke flow for quick Level 8 validation."""
    try:
        timeframe = _validate_timeframe(payload.timeframe)
        return orion_brain.smoke_run(
            agent_id=payload.agent_id,
            strategy_name=payload.strategy_name,
            source_trader=payload.source_trader,
            notes=payload.notes,
            symbols=payload.symbols,
            timeframe=timeframe,
            days=payload.days,
        )
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/performance")
def get_orion_performance(
    agent_id: str,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> dict[str, Any]:
    """Returns combined live + paper performance and strategy recommendations."""
    try:
        return orion_brain.performance_summary(agent_id=agent_id, days=days)
    except HTTPException:
        raise
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/learn-outcomes")
def orion_learn_outcomes(payload: OrionLearnOutcomesRequest) -> dict[str, Any]:
    """Runs Orion weekly self-improvement review for this owner."""
    try:
        return orion_brain.learn_from_outcomes(owner_id=payload.owner_id)
    except HTTPException:
        raise
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
