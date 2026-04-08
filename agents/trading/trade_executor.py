"""Trading approval and execution helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database.activity_log import log_activity
from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.twilio_client import send_sms


def _build_approval_sms(agent_name: str, trade_setup: dict[str, Any]) -> str:
    direction = str(trade_setup.get("direction", "LONG")).upper()
    instrument = trade_setup.get("instrument", "UNKNOWN")
    entry = trade_setup.get("entry_price")
    stop = trade_setup.get("stop_loss")
    target = trade_setup.get("take_profit")
    confidence = trade_setup.get("confidence", 0)
    reasoning = trade_setup.get("reasoning", "No reasoning supplied.")
    strategy_name = trade_setup.get("setup_name", trade_setup.get("strategy_name", "Unspecified setup"))
    risk_amount = trade_setup.get("risk_amount_dollars", "?")
    reward_amount = trade_setup.get("reward_amount_dollars", "?")

    return (
        "ORB TRADE ALERT\n"
        f"Agent: {agent_name}\n"
        f"Setup: {strategy_name}\n"
        f"{direction} {instrument}\n"
        f"Entry: {entry}\n"
        f"Stop: {stop} (-${risk_amount})\n"
        f"Target: {target} (+${reward_amount})\n"
        f"Confidence: {confidence}%\n"
        f"Reason: {reasoning}\n\n"
        "Reply YES to approve\n"
        "Reply NO to skip\n"
        "Reply STOP to pause agent"
    )


def request_trade_approval(trade_setup: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """Saves a pending trade and sends an approval SMS when possible."""
    db = SupabaseService()
    agent_rows = db.fetch_all("agents", {"id": agent_id})
    agent = agent_rows[0] if agent_rows else {}

    trade_payload = {
        "agent_id": agent_id,
        "instrument": trade_setup.get("instrument", trade_setup.get("symbol", "ES")),
        "direction": trade_setup.get("direction", "long"),
        "entry_price": trade_setup.get("entry_price"),
        "setup_name": trade_setup.get("setup_name", trade_setup.get("strategy_name", "Unknown setup")),
        "confidence_score": trade_setup.get("confidence"),
        "status": "pending_approval",
        "approved_by_human": False,
        "stop_loss": trade_setup.get("stop_loss"),
        "take_profit": trade_setup.get("take_profit"),
    }
    trade_row = db.insert_one("trades", trade_payload)

    owner_phone_number = trade_setup.get("owner_phone_number")
    sms_result: dict[str, Any] | None = None
    if owner_phone_number:
        sms_body = _build_approval_sms(agent.get("name", "ORB Trader"), trade_setup)
        sms_result = send_sms(to=owner_phone_number, message=sms_body)

    log_activity(
        agent_id=agent_id,
        action_type="trade",
        description=f"Created pending trade approval for {trade_payload['instrument']}",
        outcome="pending_approval",
        cost_cents=int((sms_result or {}).get("cost_cents", 0)),
        needs_approval=True,
    )

    return {
        "trade": trade_row,
        "sms_sent": bool(sms_result),
        "sms_result": sms_result,
        "sms_preview": _build_approval_sms(agent.get("name", "ORB Trader"), trade_setup),
    }


def handle_trade_reply(message_body: str, to_number: str, from_number: str) -> dict[str, Any]:
    """Parses YES/NO/STOP replies and updates the latest pending trade for the agent."""
    decision = message_body.strip().upper()
    db = SupabaseService()
    agent_rows = db.fetch_all("agents", {"phone_number": to_number})
    if not agent_rows:
        return {"success": False, "detail": "No agent found for this Twilio number."}

    agent = agent_rows[0]
    trades = db.fetch_all("trades", {"agent_id": agent["id"]})
    pending = [trade for trade in trades if trade.get("status") == "pending_approval"]
    pending.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    latest = pending[0] if pending else None
    if not latest:
        return {"success": False, "detail": "No pending trade found for this agent."}

    if decision == "YES":
        updated = db.update_many(
            "trades",
            {"id": latest["id"]},
            {"status": "active", "approved_by_human": True},
        )
        log_activity(agent["id"], "trade", f"Trade {latest['id']} approved by SMS", "approved", 0)
        return {"success": True, "decision": "YES", "trade": updated[0] if updated else latest}

    if decision == "NO":
        updated = db.update_many(
            "trades",
            {"id": latest["id"]},
            {"status": "closed", "approved_by_human": False, "closed_at": datetime.now(timezone.utc).isoformat()},
        )
        log_activity(agent["id"], "trade", f"Trade {latest['id']} rejected by SMS", "rejected", 0)
        return {"success": True, "decision": "NO", "trade": updated[0] if updated else latest}

    if decision == "STOP":
        db.update_many("agents", {"id": agent["id"]}, {"status": "paused"})
        db.update_many(
            "trades",
            {"id": latest["id"]},
            {"status": "closed", "approved_by_human": False, "closed_at": datetime.now(timezone.utc).isoformat()},
        )
        log_activity(agent["id"], "trade", f"Agent {agent['id']} paused by SMS", "paused", 0)
        return {"success": True, "decision": "STOP", "agent_status": "paused"}

    return {"success": False, "detail": f"Unsupported reply '{message_body}'."}
