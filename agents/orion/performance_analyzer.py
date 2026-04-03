"""Performance summary helpers for Orion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agents.trading.trade_logger import get_performance_summary
from app.database.connection import DatabaseConnectionError, SupabaseService


class OrionPerformanceAnalyzer:
    """Combines existing trade stats with paper-trade specific metrics."""

    def summarize(self, agent_id: str, days: int = 14) -> dict[str, Any]:
        live_summary = get_performance_summary(agent_id=agent_id, days=days)
        paper_summary = self._paper_trade_summary(agent_id=agent_id, days=days)

        return {
            "lookback_days": days,
            "live_trades": live_summary,
            "paper_trades": paper_summary,
        }

    def _paper_trade_summary(self, agent_id: str, days: int) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            rows = SupabaseService().fetch_all("paper_trades", {"agent_id": agent_id})
        except DatabaseConnectionError:
            rows = []

        relevant: list[dict[str, Any]] = []
        for row in rows:
            created_at = str(row.get("created_at") or "")
            if not created_at:
                continue
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if timestamp >= cutoff:
                relevant.append(row)

        closed = [row for row in relevant if row.get("status") == "closed" and row.get("pnl_dollars") is not None]
        open_count = sum(1 for row in relevant if row.get("status") == "open")

        pnl_values = [float(row.get("pnl_dollars") or 0) for row in closed]
        wins = [value for value in pnl_values if value > 0]

        return {
            "total_rows": len(relevant),
            "open_trades": open_count,
            "closed_trades": len(closed),
            "total_pnl": round(sum(pnl_values), 2),
            "win_rate": round((len(wins) / len(closed)) * 100, 2) if closed else 0.0,
        }
