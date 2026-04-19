"""Investment memo writer — structured memos and portfolio thesis documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.vest.memo")


class MemoWriter:
    """Generates professional investment memos and portfolio theses."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def write_memo(self, ticker: str, research: dict[str, Any],
                   position_type: str = "long", owner_id: str = "") -> dict[str, Any]:
        """Generate a structured investment memo for a ticker."""
        price_data = research.get("price_data", {})
        fundamentals = research.get("fundamentals", {})

        memo_content = think(
            prompt=(
                f"Write a professional investment memo for {ticker} ({position_type} position).\n\n"
                f"Price: {price_data.get('price', 'N/A')}\n"
                f"52W Range: {price_data.get('week_52_low', 'N/A')} – {price_data.get('week_52_high', 'N/A')}\n"
                f"Market Cap: {fundamentals.get('market_cap', 'N/A')}\n"
                f"P/E: {fundamentals.get('pe_ratio', 'N/A')}\n\n"
                f"Research summary: {research.get('ai_analysis', '')[:500]}\n\n"
                "Structure the memo as:\n"
                "## Executive Summary (2 sentences)\n"
                "## Investment Thesis (3 bullet points)\n"
                "## Key Risks (3 bullet points)\n"
                "## Price Target & Catalysts (2-3 sentences)\n"
                "## Recommendation (Buy/Hold/Avoid with rationale — 2 sentences)\n\n"
                "Note at the end: This memo is for informational purposes only and does not constitute financial advice."
            ),
            task_type="report",
        )

        memo = {
            "ticker": ticker.upper(),
            "position_type": position_type,
            "content": memo_content,
            "price_at_writing": price_data.get("price"),
            "written_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist if owner_id provided
        if owner_id:
            try:
                self.db.client.table("investment_memos").insert({
                    "owner_id": owner_id,
                    **memo,
                }).execute()
            except Exception as e:
                logger.warning("Could not save memo: %s", e)

        return memo

    def write_portfolio_thesis(self, owner_id: str, portfolio: dict[str, Any]) -> dict[str, Any]:
        """Generate a holistic portfolio investment thesis."""
        holdings = portfolio.get("holdings", [])
        allocation = portfolio.get("allocation", {})
        total_value = portfolio.get("total_value", 0)
        ytd = portfolio.get("ytd_return_pct", 0)

        thesis = think(
            prompt=(
                f"Write a portfolio investment thesis document.\n\n"
                f"Portfolio value: ${total_value:,.2f}\n"
                f"YTD performance: {ytd:.1f}%\n"
                f"Holdings ({len(holdings)} positions): {[h.get('ticker') for h in holdings]}\n"
                f"Asset allocation: {allocation}\n\n"
                "Structure as:\n"
                "## Portfolio Philosophy (2-3 sentences)\n"
                "## Core Holdings Analysis (1 sentence per position)\n"
                "## Allocation Assessment (strengths and gaps, 3 bullet points)\n"
                "## Performance Context (benchmark comparison, 2 sentences)\n"
                "## Strategic Priorities (top 3 actions for next 90 days)\n\n"
                "Note: This is an analytical framework, not financial advice."
            ),
            task_type="strategy",
        )

        result = {
            "owner_id": owner_id,
            "thesis": thesis,
            "portfolio_value": total_value,
            "ytd_return_pct": ytd,
            "written_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self.db.client.table("investment_memos").insert({
                **result,
                "ticker": "PORTFOLIO",
                "content": thesis,
                "position_type": "overview",
            }).execute()
        except Exception as e:
            logger.warning("Could not save portfolio thesis: %s", e)

        return result
