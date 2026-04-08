"""Trading risk management rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import floor
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agents.trading.strategy_loader import load_strategy
from app.database.connection import DatabaseConnectionError, SupabaseService


try:
    MARKET_TIMEZONE = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    MARKET_TIMEZONE = timezone.utc


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _get_active_strategy(agent_id: str) -> dict[str, Any]:
    try:
        db = SupabaseService()
        rows = db.fetch_all("strategies", {"agent_id": agent_id})
        active = next((row for row in rows if row.get("is_active") is True), None)
        if active and isinstance(active.get("rules_json"), dict) and active["rules_json"]:
            strategy = dict(active["rules_json"])
            strategy["name"] = active.get("name", strategy.get("name", "Custom Strategy"))
            return strategy
    except DatabaseConnectionError:
        pass
    return load_strategy("es_momentum")


def get_daily_stats(agent_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Returns today's trading stats based on rows in the trades table."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(MARKET_TIMEZONE).date()

    try:
        rows = SupabaseService().fetch_all("trades", {"agent_id": agent_id})
    except DatabaseConnectionError:
        rows = []

    todays_trades: list[dict[str, Any]] = []
    for trade in rows:
        created_at = _parse_timestamp(trade.get("created_at"))
        if created_at and created_at.astimezone(MARKET_TIMEZONE).date() == today:
            todays_trades.append(trade)

    todays_trades.sort(key=lambda row: row.get("created_at") or "")

    pnl_values = [float(trade.get("pnl_dollars") or 0) for trade in todays_trades if trade.get("pnl_dollars") is not None]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]

    consecutive_losses = 0
    for trade in reversed(todays_trades):
        pnl = trade.get("pnl_dollars")
        if pnl is None:
            continue
        if float(pnl) < 0:
            consecutive_losses += 1
        else:
            break

    trade_count = len(todays_trades)
    win_rate = round((len(wins) / trade_count) * 100, 2) if trade_count else 0.0

    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "total_pnl_dollars": round(sum(pnl_values), 2),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "consecutive_losses": consecutive_losses,
    }


def check_can_trade(
    agent_id: str,
    now: datetime | None = None,
    upcoming_news_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Checks whether the agent is allowed to take another trade right now."""
    now = now or datetime.now(timezone.utc)
    strategy = _get_active_strategy(agent_id)
    risk_rules = strategy.get("risk_rules", {})
    stats = get_daily_stats(agent_id, now=now)

    local_now = now.astimezone(MARKET_TIMEZONE)
    session_start = datetime.strptime(strategy.get("session_start", "09:30"), "%H:%M").time()
    session_end = datetime.strptime(strategy.get("session_end", "11:30"), "%H:%M").time()

    if stats["total_pnl_dollars"] <= -float(risk_rules.get("max_daily_loss_dollars", 150)):
        return {"can_trade": False, "reason": "Daily loss limit reached.", "stats": stats}

    if stats["trade_count"] >= int(risk_rules.get("max_daily_trades", 3)):
        return {"can_trade": False, "reason": "Maximum daily trades reached.", "stats": stats}

    if stats["consecutive_losses"] >= int(risk_rules.get("stop_after_consecutive_losses", 2)):
        return {"can_trade": False, "reason": "Consecutive loss limit reached.", "stats": stats}

    if not (session_start <= local_now.time() <= session_end):
        return {"can_trade": False, "reason": "Outside trading session hours.", "stats": stats}

    if upcoming_news_events:
        for event in upcoming_news_events:
            event_time = event.get("time")
            if isinstance(event_time, datetime) and timedelta(0) <= (event_time - now) <= timedelta(minutes=30):
                return {"can_trade": False, "reason": "Major news event within 30 minutes.", "stats": stats}

    return {"can_trade": True, "reason": "Risk checks passed.", "stats": stats}


def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    stop_distance: float,
    point_value: float = 50.0,
) -> int:
    """Returns the number of futures contracts allowed by the risk budget."""
    if account_balance <= 0 or risk_percent <= 0 or stop_distance <= 0 or point_value <= 0:
        return 0

    risk_dollars = account_balance * (risk_percent / 100)
    risk_per_contract = stop_distance * point_value
    if risk_per_contract <= 0:
        return 0
    return max(0, floor(risk_dollars / risk_per_contract))
