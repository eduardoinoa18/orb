"""Tests for Level 3 trading foundations."""

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.trading.risk_manager import calculate_position_size, check_can_trade, get_daily_stats
from agents.trading.strategy_loader import list_strategies, load_strategy
from app.api.main import app
from integrations.tradingview_webhook import parse_tradingview_payload

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_load_strategy_returns_es_momentum() -> None:
    strategy = load_strategy("es_momentum")

    assert strategy["name"] == "ES Momentum Pullback"
    assert strategy["instrument"] == "ES"
    assert strategy["slug"] == "es_momentum"



def test_list_strategies_includes_es_momentum() -> None:
    strategies = list_strategies()

    assert any(item["slug"] == "es_momentum" for item in strategies)



def test_calculate_position_size_returns_contract_count() -> None:
    contracts = calculate_position_size(account_balance=50000, risk_percent=1, stop_distance=4)

    assert contracts == 2



def test_get_daily_stats_summarizes_trades() -> None:
    fake_trades = [
        {
            "agent_id": "agent-1",
            "created_at": "2026-03-27T14:00:00+00:00",
            "pnl_dollars": 100,
            "status": "closed",
        },
        {
            "agent_id": "agent-1",
            "created_at": "2026-03-27T15:00:00+00:00",
            "pnl_dollars": -50,
            "status": "closed",
        },
    ]

    with patch("agents.trading.risk_manager.SupabaseService") as mock_db:
        mock_db.return_value.fetch_all.return_value = fake_trades
        stats = get_daily_stats("agent-1", now=datetime(2026, 3, 27, 16, 0, tzinfo=timezone.utc))

    assert stats["trade_count"] == 2
    assert stats["total_pnl_dollars"] == 50.0
    assert stats["win_rate"] == 50.0



def test_check_can_trade_blocks_outside_session() -> None:
    with patch("agents.trading.risk_manager.get_daily_stats", return_value={
        "trade_count": 0,
        "win_rate": 0,
        "total_pnl_dollars": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "consecutive_losses": 0,
    }):
        with patch("agents.trading.risk_manager._get_active_strategy", return_value=load_strategy("es_momentum")):
            result = check_can_trade("agent-1", now=datetime(2026, 3, 27, 19, 0, tzinfo=timezone.utc))

    assert result["can_trade"] is False
    assert "Outside trading session" in result["reason"]



def test_parse_tradingview_payload_normalizes_fields() -> None:
    parsed = parse_tradingview_payload({
        "ticker": "ES1!",
        "interval": "5",
        "message": "Momentum pullback detected",
        "close": 5320.25,
        "volume": 12345,
        "owner_phone_number": "+19783909619",
    })

    assert parsed["symbol"] == "ES1!"
    assert parsed["timeframe"] == "5"
    assert parsed["price"] == 5320.25
    assert parsed["owner_phone_number"] == "+19783909619"



def test_tradingview_webhook_rejects_invalid_secret() -> None:
    response = client.post(
        "/webhooks/tradingview",
        headers={"x-tradingview-secret": "wrong-secret"},
        json={"symbol": "ES", "message": "test"},
    )

    assert response.status_code == 401



def test_twilio_sms_webhook_returns_twiml() -> None:
    with patch("app.api.routes.webhooks._is_valid_twilio_request", return_value=True), patch(
        "app.api.routes.webhooks.process_mobile_command", return_value=None
    ), patch("app.api.routes.webhooks.handle_trade_reply", return_value={"success": True, "decision": "YES"}):
        response = client.post(
            "/webhooks/twilio/sms",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": "test-signature",
            },
            data="From=%2B19783909619&To=%2B18889619713&Body=YES",
        )

    assert response.status_code == 200
    assert "Reply processed: YES" in response.text
