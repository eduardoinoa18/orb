"""Paper-trade test execution for Orion."""

from __future__ import annotations

from typing import Any

from app.database.activity_log import log_activity
from app.database.connection import SupabaseService
from agents.trading.risk_manager import calculate_position_size, check_can_trade


class OrionPaperTrader:
    """Runs risk-aware paper-trade simulation and stores the row."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def run_test_trade(
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
        risk_result = check_can_trade(agent_id)
        if not risk_result.get("can_trade"):
            return {"status": "blocked", "risk": risk_result}

        stop_distance = abs(entry_price - stop_loss)
        point_value = 50.0 if instrument.upper() in {"ES", "NQ", "YM", "RTY"} else 1.0
        quantity = calculate_position_size(
            account_balance=account_balance,
            risk_percent=risk_percent,
            stop_distance=stop_distance,
            point_value=point_value,
        )
        if quantity <= 0:
            return {
                "status": "rejected",
                "detail": "Calculated position size is zero. Increase balance or reduce stop distance.",
                "risk": risk_result,
            }

        risk_per_unit = abs(entry_price - stop_loss)
        reward_per_unit = abs(take_profit - entry_price)
        expected_rr = round(reward_per_unit / risk_per_unit, 2) if risk_per_unit > 0 else 0.0

        payload = {
            "agent_id": agent_id,
            "instrument": instrument.upper(),
            "direction": direction.lower(),
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "setup_name": "Orion Paper Test",
            "strategy_version": "v1",
            "confidence_score": 70,
            "entry_reason": "Manual Orion test route",
            "market_conditions": {
                "expected_rr": expected_rr,
                "risk_percent": risk_percent,
                "account_balance": account_balance,
            },
            "status": "open",
        }
        row = self.db.insert_one("paper_trades", payload)

        log_activity(
            agent_id=agent_id,
            action_type="paper_trade",
            description=f"Opened Orion paper trade on {instrument.upper()} qty={quantity}",
            outcome="opened",
            cost_cents=0,
            metadata={"expected_rr": expected_rr},
        )

        return {
            "status": "opened",
            "trade": row,
            "risk": risk_result,
            "position": {
                "quantity": quantity,
                "expected_rr": expected_rr,
            },
        }
