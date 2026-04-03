"""Trading market monitoring logic."""

from typing import Any

from app.database.activity_log import log_activity
from integrations.anthropic_client import analyze_trade_setup


def analyze_setup(webhook_data: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    """Uses Claude to decide whether an alert matches the current strategy."""
    result = analyze_trade_setup(strategy_rules=strategy, market_data=webhook_data)
    approval_required = bool(result.get("valid")) and int(result.get("confidence", 0)) > 75
    log_activity(
        agent_id=webhook_data.get("agent_id"),
        action_type="trade",
        description=f"Analyzed setup for {webhook_data.get('symbol', 'unknown symbol')}",
        outcome="valid" if result.get("valid") else "invalid",
        cost_cents=int(result.get("cost_cents", 0)),
    )
    return {**result, "approval_required": approval_required}
