"""Market scanner that converts quote data into candidate paper-trade setups."""

from __future__ import annotations

from typing import Any

from app.database.activity_log import log_activity
from agents.trading.risk_manager import check_can_trade
from integrations.market_data import get_market_snapshot


class OrionMarketScanner:
    """Finds simple momentum setups from free market data snapshots."""

    def scan(self, agent_id: str, symbols: list[str], timeframe: str = "5m") -> dict[str, Any]:
        if not symbols:
            symbols = ["ES", "NQ"]

        risk_result = check_can_trade(agent_id)
        market = get_market_snapshot(symbols)
        setups: list[dict[str, Any]] = []

        for quote in market.get("quotes", []):
            setup = self._build_setup(quote, timeframe)
            if setup is not None:
                setups.append(setup)

        log_activity(
            agent_id=agent_id,
            action_type="trade_scan",
            description=f"Orion scanned {len(market.get('quotes', []))} symbols and found {len(setups)} setup(s)",
            outcome="ready" if setups else "no_signal",
            cost_cents=0,
        )

        return {
            "status": "blocked" if not risk_result.get("can_trade") else "ready",
            "risk": risk_result,
            "market": market,
            "setups": setups,
            "timeframe": timeframe,
        }

    def _build_setup(self, quote: dict[str, Any], timeframe: str) -> dict[str, Any] | None:
        momentum = float(quote.get("momentum_pct") or 0)
        if abs(momentum) < 0.18:
            return None

        direction = "long" if momentum > 0 else "short"
        last_price = float(quote.get("last_price") or 0)
        if last_price <= 0:
            return None

        stop_distance = max(last_price * 0.002, 0.5)
        stop_loss = round(last_price - stop_distance, 4) if direction == "long" else round(last_price + stop_distance, 4)
        take_profit = round(last_price + (stop_distance * 2), 4) if direction == "long" else round(last_price - (stop_distance * 2), 4)

        confidence = min(95, int(55 + abs(momentum) * 20))

        return {
            "instrument": quote.get("symbol"),
            "direction": direction,
            "entry_price": round(last_price, 4),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "strategy_name": "Orion Momentum Snapshot",
            "setup_name": f"{quote.get('symbol')} {timeframe} momentum",
            "reasoning": f"{quote.get('symbol')} moved {momentum}% vs previous close.",
            "source": quote.get("source"),
        }
