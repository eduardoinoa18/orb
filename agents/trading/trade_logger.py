"""Trading performance logging helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.database.activity_log import log_activity
from app.database.connection import SupabaseService


def log_trade_result(trade_id: str, exit_price: float, notes: str) -> dict:
    """Closes a trade, calculates P&L, and saves the result to the database."""
    db = SupabaseService()
    rows = db.fetch_all("trades", {"id": trade_id})
    if not rows:
        raise ValueError(f"Trade not found: {trade_id}")

    trade = rows[0]
    entry_price = float(trade.get("entry_price") or 0)
    direction = str(trade.get("direction") or "long").lower()
    pnl_dollars = round((exit_price - entry_price), 2) if direction == "long" else round((entry_price - exit_price), 2)

    updated = db.update_many(
        "trades",
        {"id": trade_id},
        {
            "exit_price": exit_price,
            "pnl_dollars": pnl_dollars,
            "status": "closed",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    log_activity(trade.get("agent_id"), "trade", f"Closed trade {trade_id}: {notes}", "closed", 0)
    return updated[0] if updated else {**trade, "exit_price": exit_price, "pnl_dollars": pnl_dollars}


def get_performance_summary(agent_id: str, days: int) -> dict:
    """Returns rolling performance stats for the specified lookback period."""
    db = SupabaseService()
    rows = db.fetch_all("trades", {"agent_id": agent_id})
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []
    for trade in rows:
        created_at = trade.get("created_at")
        if not created_at:
            continue
        timestamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if timestamp >= cutoff:
            filtered.append(trade)

    closed = [trade for trade in filtered if trade.get("status") == "closed" and trade.get("pnl_dollars") is not None]
    total_pnl = round(sum(float(trade.get("pnl_dollars") or 0) for trade in closed), 2)
    wins = [trade for trade in closed if float(trade.get("pnl_dollars") or 0) > 0]
    win_rate = round((len(wins) / len(closed)) * 100, 2) if closed else 0.0

    by_setup: dict[str, list[float]] = defaultdict(list)
    by_day: dict[str, float] = defaultdict(float)
    for trade in closed:
        by_setup[str(trade.get("setup_name") or "unknown")].append(float(trade.get("pnl_dollars") or 0))
        closed_at = str(trade.get("closed_at") or trade.get("created_at"))[:10]
        by_day[closed_at] += float(trade.get("pnl_dollars") or 0)

    best_setup = max(by_setup.items(), key=lambda item: sum(item[1]) / len(item[1]), default=("n/a", []))[0]
    best_day = max(by_day.items(), key=lambda item: item[1], default=("n/a", 0))
    worst_day = min(by_day.items(), key=lambda item: item[1], default=("n/a", 0))

    return {
        "total_trades": len(closed),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "best_setup": best_setup,
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)},
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)},
    }
