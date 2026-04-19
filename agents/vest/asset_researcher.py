"""Asset researcher — fundamental analysis, sentiment, opportunity scanning."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from integrations.ai_router import think

logger = logging.getLogger("orb.vest.researcher")


class AssetResearcher:
    """Research assets using market data and AI analysis."""

    def research(self, ticker: str, asset_type: str = "stock") -> dict[str, Any]:
        """Full research on a single asset."""
        ticker = ticker.upper()

        # Fetch market data
        price_data: dict[str, Any] = {}
        try:
            from integrations.market_data import get_price, get_fundamentals
            price_data = get_price(ticker) or {}
            fundamentals = get_fundamentals(ticker) or {}
        except Exception:
            fundamentals = {}

        # AI analysis
        analysis = think(
            prompt=(
                f"Research report for {ticker} ({asset_type}):\n"
                f"Current price: {price_data.get('price', 'N/A')}\n"
                f"52-week high: {price_data.get('week_52_high', 'N/A')}\n"
                f"52-week low: {price_data.get('week_52_low', 'N/A')}\n"
                f"Market cap: {fundamentals.get('market_cap', 'N/A')}\n"
                f"P/E ratio: {fundamentals.get('pe_ratio', 'N/A')}\n"
                f"Revenue (TTM): {fundamentals.get('revenue', 'N/A')}\n\n"
                "Provide: (1) 2-sentence business summary, "
                "(2) 3 key investment strengths, "
                "(3) 3 key risks, "
                "(4) overall sentiment: bullish/neutral/bearish with brief reason.\n"
                "Format as structured text."
            ),
            task_type="research",
        )

        return {
            "ticker": ticker,
            "asset_type": asset_type,
            "price_data": price_data,
            "fundamentals": fundamentals,
            "ai_analysis": analysis,
            "researched_at": datetime.now(timezone.utc).isoformat(),
        }

    def compare(self, tickers: list[str], asset_type: str = "stock") -> dict[str, Any]:
        """Compare multiple assets side by side."""
        tickers = [t.upper() for t in tickers]

        # Research each
        data = {}
        for ticker in tickers:
            try:
                from integrations.market_data import get_price
                price = get_price(ticker) or {}
                data[ticker] = {"price": price.get("price"), "change_pct": price.get("change_pct")}
            except Exception:
                data[ticker] = {}

        comparison = think(
            prompt=(
                f"Compare these {asset_type} assets for an investor:\n"
                f"{data}\n\n"
                "For each: (1) one-line assessment, (2) best use case for this investor. "
                "Then recommend which one looks most compelling right now and why (2 sentences)."
            ),
            task_type="research",
        )

        return {
            "tickers": tickers,
            "market_data": data,
            "comparison": comparison,
            "compared_at": datetime.now(timezone.utc).isoformat(),
        }

    def scan_opportunities(self, portfolio: dict[str, Any]) -> dict[str, Any]:
        """Scan for opportunities given a current portfolio."""
        holdings = [h.get("ticker") for h in portfolio.get("holdings", [])]
        allocation = portfolio.get("allocation", {})

        opportunities = think(
            prompt=(
                f"Investment opportunity scan:\n"
                f"Current holdings: {holdings}\n"
                f"Current allocation: {allocation}\n\n"
                "Suggest 3 specific investment opportunities that would:\n"
                "1. Diversify this portfolio\n"
                "2. Fill allocation gaps\n"
                "3. Add growth potential\n"
                "For each: ticker/asset, asset class, 1-sentence rationale. "
                "Be specific but note this is not financial advice."
            ),
            task_type="strategy",
        )

        return {
            "current_holdings": holdings,
            "opportunities": opportunities,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
