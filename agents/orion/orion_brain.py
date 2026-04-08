"""Orion orchestrator for ingestion, scanning, paper tests, and coaching."""

from __future__ import annotations

import re
from typing import Any

from agents.self_improvement import AgentSelfImprovement
from agents.orion.market_scanner import OrionMarketScanner
from agents.orion.paper_trader import OrionPaperTrader
from agents.orion.performance_analyzer import OrionPerformanceAnalyzer
from agents.orion.strategy_improver import OrionStrategyImprover
from agents.orion.strategy_researcher import OrionStrategyResearcher
from app.database.connection import SupabaseService


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


class OrionBrain(AgentSelfImprovement):
    """High-level Orion workflow facade used by API routes."""

    agent_slug = "orion"

    def __init__(self) -> None:
        super().__init__()
        self.researcher = OrionStrategyResearcher()
        self.scanner = OrionMarketScanner()
        self.paper_trader = OrionPaperTrader()
        self.performance = OrionPerformanceAnalyzer()
        self.improver = OrionStrategyImprover()

    def ingest_strategy(
        self,
        agent_id: str,
        strategy_name: str,
        notes: str,
        source_trader: str | None = None,
    ) -> dict[str, Any]:
        return self.researcher.ingest_strategy(
            agent_id=agent_id,
            strategy_name=strategy_name,
            notes=notes,
            source_trader=source_trader,
        )

    def scan_market(self, agent_id: str, symbols: list[str], timeframe: str = "5m") -> dict[str, Any]:
        return self.scanner.scan(agent_id=agent_id, symbols=symbols, timeframe=timeframe)

    def run_paper_trade_test(
        self,
        agent_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        account_balance: float = 50000,
        risk_percent: float = 1.0,
    ) -> dict[str, Any]:
        return self.paper_trader.run_test_trade(
            agent_id=agent_id,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            account_balance=account_balance,
            risk_percent=risk_percent,
        )

    def performance_summary(self, agent_id: str, days: int = 14) -> dict[str, Any]:
        summary = self.performance.summarize(agent_id=agent_id, days=days)
        summary["recommendations"] = self.improver.suggest(summary)
        return summary

    def learn_from_outcomes(self, owner_id: str) -> dict[str, Any]:
        """Runs weekly Orion review and returns improvement plan."""
        result = super().learn_from_outcomes(agent_id=owner_id, lookback_days=7)
        return {
            "status": "updated",
            "owner_id": owner_id,
            "improvements_made": result.get("improvements_made", 0),
            "plan": result.get("plan", {}),
        }

    def smoke_run(
        self,
        agent_id: str | None = None,
        strategy_name: str = "ORB Level 8 Momentum",
        source_trader: str = "orb-dashboard-smoke",
        notes: str | None = None,
        symbols: list[str] | None = None,
        timeframe: str = "5m",
        days: int = 14,
    ) -> dict[str, Any]:
        resolved_agent_id = self._resolve_agent_id(agent_id)
        symbols = symbols or ["ES", "NQ"]
        notes = notes or (
            "Long only breakout pullback setup during the opening hour. "
            "One to two trades max, stop after two losses, and preserve capital first."
        )

        ingest = self.ingest_strategy(
            agent_id=resolved_agent_id,
            strategy_name=strategy_name,
            notes=notes,
            source_trader=source_trader,
        )
        scan = self.scan_market(agent_id=resolved_agent_id, symbols=symbols, timeframe=timeframe)
        setups = [item for item in (scan.get("setups") or []) if isinstance(item, dict)]

        selected_setup: dict[str, Any]
        if setups:
            selected_setup = setups[0]
        else:
            selected_setup = {
                "instrument": "ES",
                "direction": "long",
                "entry_price": 5320.0,
                "stop_loss": 5318.5,
                "take_profit": 5323.0,
            }

        paper = self.run_paper_trade_test(
            agent_id=resolved_agent_id,
            instrument=str(selected_setup.get("instrument") or "ES"),
            direction=str(selected_setup.get("direction") or "long"),
            entry_price=float(selected_setup.get("entry_price") or 5320.0),
            stop_loss=float(selected_setup.get("stop_loss") or 5318.5),
            take_profit=float(selected_setup.get("take_profit") or 5323.0),
            account_balance=50000,
            risk_percent=1.0,
        )
        performance = self.performance_summary(agent_id=resolved_agent_id, days=days)

        return {
            "success": True,
            "agent_id": resolved_agent_id,
            "ingest_status": ingest.get("status"),
            "scan_status": scan.get("status"),
            "setup_count": len(setups),
            "paper_status": paper.get("status"),
            "live_trades": performance.get("live_trades", {}),
            "paper_trades": performance.get("paper_trades", {}),
            "recommendations": performance.get("recommendations", []),
        }

    def _resolve_agent_id(self, requested_agent_id: str | None) -> str:
        if requested_agent_id and UUID_RE.match(requested_agent_id):
            return requested_agent_id

        rows = SupabaseService().fetch_all("agents")
        for row in rows:
            candidate = str(row.get("id") or "")
            if UUID_RE.match(candidate):
                return candidate

        raise ValueError("No valid agent UUID found. Create an agent first or provide a valid agent_id.")
