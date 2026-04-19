"""Vest — Investment & Portfolio Agent.

Vest is the sophisticated money mind for ORB owners who want to grow wealth:
  - Tracks investment portfolios across asset classes (stocks, crypto, real estate, alts)
  - Researches assets with fundamental + sentiment analysis
  - Writes investment memos and thesis documents
  - Monitors positions for rebalancing triggers
  - Generates weekly portfolio performance reports
  - Connects to market data APIs (Alpha Vantage, Yahoo Finance, CoinGecko)

Business rationale: Busy entrepreneurs often neglect personal investing.
Vest makes portfolio management as easy as asking a question. It bridges
Orion (trading algorithms) with personal wealth management.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.self_improvement import AgentSelfImprovement
from agents.skill_engine import AgentSkillEngine
from agents.vest.asset_researcher import AssetResearcher
from agents.vest.memo_writer import MemoWriter
from agents.vest.portfolio_tracker import PortfolioTracker
from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.vest")


class VestBrain(AgentSelfImprovement, AgentSkillEngine):
    """Investment and portfolio brain — analytical, disciplined, growth-oriented."""

    agent_slug = "vest"

    def __init__(self) -> None:
        AgentSelfImprovement.__init__(self)
        AgentSkillEngine.__init__(self)
        self.db = SupabaseService()
        self.portfolio = PortfolioTracker()
        self.researcher = AssetResearcher()
        self.memo = MemoWriter()

    # ── Core conversation handler ─────────────────────────────────────────

    def chat(self, owner_id: str, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route an investment question through Vest's analytical lens."""
        ctx = context or {}
        port_summary = self.portfolio.get_summary(owner_id)
        skill_ctx = self.build_skill_context(owner_id)

        system = (
            "You are Vest, ORB's Investment & Portfolio Agent. You are analytical, disciplined, "
            "and think in terms of risk-adjusted returns. You help business owners build and track "
            "their investment portfolios, research assets, and make informed decisions. "
            "You always distinguish between facts and opinions. You never give blind buy/sell "
            "recommendations — you present data and let the owner decide.\n\n"
            f"Portfolio overview:\n"
            f"  Total value: ${port_summary.get('total_value', 0):,.2f}\n"
            f"  Holdings: {port_summary.get('holding_count', 0)} positions\n"
            f"  YTD return: {port_summary.get('ytd_return_pct', 0):.1f}%\n"
            f"  Asset allocation: {json.dumps(port_summary.get('allocation', {}))}\n"
            f"{skill_ctx}"
        )

        prompt = f"Owner question: {message}\nContext: {json.dumps(ctx)}"
        response = think(prompt=prompt, task_type="strategy", system_override=system)

        return {
            "agent": "vest",
            "message": response,
            "portfolio_snapshot": port_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Portfolio management ──────────────────────────────────────────────

    def add_holding(self, owner_id: str, ticker: str, asset_type: str,
                    quantity: float, avg_cost: float, notes: str = "") -> dict[str, Any]:
        """Add a position to the portfolio."""
        return self.portfolio.add_holding(
            owner_id=owner_id, ticker=ticker, asset_type=asset_type,
            quantity=quantity, avg_cost=avg_cost, notes=notes,
        )

    def update_holding(self, owner_id: str, ticker: str, quantity: float,
                       avg_cost: float | None = None) -> dict[str, Any]:
        """Update a position (add shares, change average cost)."""
        return self.portfolio.update_holding(
            owner_id=owner_id, ticker=ticker, quantity=quantity, avg_cost=avg_cost,
        )

    def remove_holding(self, owner_id: str, ticker: str) -> dict[str, Any]:
        """Remove a position from the portfolio."""
        return self.portfolio.remove_holding(owner_id=owner_id, ticker=ticker)

    def get_portfolio(self, owner_id: str) -> dict[str, Any]:
        """Get full portfolio with current prices and P&L."""
        return self.portfolio.get_full_portfolio(owner_id)

    # ── Research ──────────────────────────────────────────────────────────

    def research_asset(self, ticker: str, asset_type: str = "stock") -> dict[str, Any]:
        """Deep research on a single asset."""
        return self.researcher.research(ticker=ticker, asset_type=asset_type)

    def compare_assets(self, tickers: list[str], asset_type: str = "stock") -> dict[str, Any]:
        """Compare multiple assets side by side."""
        return self.researcher.compare(tickers=tickers, asset_type=asset_type)

    def scan_opportunities(self, owner_id: str) -> dict[str, Any]:
        """Scan for investment opportunities matching owner's profile."""
        port = self.portfolio.get_full_portfolio(owner_id)
        return self.researcher.scan_opportunities(portfolio=port)

    # ── Memo writing ──────────────────────────────────────────────────────

    def write_investment_memo(self, owner_id: str, ticker: str,
                              position_type: str = "long") -> dict[str, Any]:
        """Generate a full investment memo for a ticker."""
        research = self.researcher.research(ticker=ticker)
        return self.memo.write_memo(
            ticker=ticker, research=research,
            position_type=position_type, owner_id=owner_id,
        )

    def write_portfolio_thesis(self, owner_id: str) -> dict[str, Any]:
        """Generate an overall portfolio investment thesis."""
        port = self.portfolio.get_full_portfolio(owner_id)
        return self.memo.write_portfolio_thesis(owner_id=owner_id, portfolio=port)

    # ── Performance reporting ─────────────────────────────────────────────

    def get_performance_report(self, owner_id: str) -> dict[str, Any]:
        """Generate a portfolio performance report with AI commentary."""
        port = self.portfolio.get_full_portfolio(owner_id)

        commentary = think(
            prompt=(
                f"Portfolio performance report:\n"
                f"Total value: ${port.get('total_value', 0):,.2f}\n"
                f"YTD return: {port.get('ytd_return_pct', 0):.1f}%\n"
                f"Holdings: {[h.get('ticker') for h in port.get('holdings', [])]}\n"
                f"Allocation: {json.dumps(port.get('allocation', {}))}\n\n"
                "Write 3 sentences: (1) overall performance, "
                "(2) top performer and laggard, (3) one rebalancing suggestion."
            ),
            task_type="report",
        )

        return {
            "portfolio": port,
            "commentary": commentary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_rebalancing_needs(self, owner_id: str) -> dict[str, Any]:
        """Check if any positions have drifted beyond target allocation."""
        return self.portfolio.check_rebalancing(owner_id)

    def run_weekly_portfolio_digest(self, owner_id: str) -> dict[str, Any]:
        """Generate and push weekly portfolio digest to Commander inbox."""
        report = self.get_performance_report(owner_id)
        rebalance = self.check_rebalancing_needs(owner_id)

        digest = (
            f"📈 Weekly Portfolio Digest\n\n"
            f"Total Value: ${report['portfolio'].get('total_value', 0):,.2f}\n"
            f"YTD Return: {report['portfolio'].get('ytd_return_pct', 0):.1f}%\n"
            f"Holdings: {report['portfolio'].get('holding_count', 0)} positions\n\n"
            f"💬 Vest's Take:\n{report['commentary']}\n\n"
            f"⚖️ Rebalancing Needed: {'Yes' if rebalance.get('needs_rebalancing') else 'No'}"
        )

        try:
            self.db.client.table("agent_messages").insert({
                "owner_id": owner_id,
                "agent": "vest",
                "role": "assistant",
                "content": digest,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.warning("Failed to push portfolio digest: %s", e)

        return {"digest": digest, "report": report, "rebalancing": rebalance}
