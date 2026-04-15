"""Tests for Orion routes and paper-trading workflow endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_orion_status_route() -> None:
    response = client.get("/agents/orion/status")
    assert response.status_code == 200
    assert response.json()["status"] == "orion router ready"


def test_orion_ingest_route_returns_ingested_status() -> None:
    payload = {
        "agent_id": "agent-1",
        "strategy_name": "Morning Momentum",
        "notes": "Long only pullback entries after opening range breakout with strict stop.",
        "source_trader": "mentor-a",
    }
    with patch("app.api.routes.orion.orion_brain.ingest_strategy") as mock_ingest:
        mock_ingest.return_value = {"status": "ingested", "strategy": {"id": "s1"}}
        response = client.post("/agents/orion/ingest", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "ingested"


def test_orion_scan_route_returns_setups() -> None:
    payload = {
        "agent_id": "agent-1",
        "symbols": ["ES", "NQ"],
        "timeframe": "5m",
    }
    with patch("app.api.routes.orion.orion_brain.scan_market") as mock_scan:
        mock_scan.return_value = {
            "status": "ready",
            "setups": [{"instrument": "ES", "direction": "long"}],
            "market": {"quotes": []},
        }
        response = client.post("/agents/orion/scan", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["setups"]) == 1


def test_orion_scan_route_rejects_invalid_timeframe() -> None:
    payload = {
        "agent_id": "agent-1",
        "symbols": ["ES", "NQ"],
        "timeframe": "2m",
    }
    response = client.post("/agents/orion/scan", json=payload)

    assert response.status_code == 422
    assert "Invalid timeframe" in response.json()["detail"]


def test_orion_paper_trade_test_route_returns_opened() -> None:
    payload = {
        "agent_id": "agent-1",
        "instrument": "ES",
        "direction": "long",
        "entry_price": 5320.0,
        "stop_loss": 5318.5,
        "take_profit": 5323.0,
        "account_balance": 50000,
        "risk_percent": 1.0,
    }
    with patch("app.api.routes.orion.orion_brain.run_paper_trade_test") as mock_test:
        mock_test.return_value = {"status": "opened", "trade": {"id": "pt-1"}}
        response = client.post("/agents/orion/paper-trade/test", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "opened"


def test_orion_paper_trade_test_rejects_invalid_long_geometry() -> None:
    payload = {
        "agent_id": "agent-1",
        "instrument": "ES",
        "direction": "long",
        "entry_price": 5320.0,
        "stop_loss": 5321.0,
        "take_profit": 5323.0,
        "account_balance": 50000,
        "risk_percent": 1.0,
    }
    response = client.post("/agents/orion/paper-trade/test", json=payload)

    assert response.status_code == 422
    assert "stop_loss must be below entry_price" in response.json()["detail"]


def test_orion_paper_trade_test_rejects_invalid_short_geometry() -> None:
    payload = {
        "agent_id": "agent-1",
        "instrument": "NQ",
        "direction": "short",
        "entry_price": 18750.0,
        "stop_loss": 18749.0,
        "take_profit": 18745.0,
        "account_balance": 50000,
        "risk_percent": 1.0,
    }
    response = client.post("/agents/orion/paper-trade/test", json=payload)

    assert response.status_code == 422
    assert "stop_loss must be above entry_price" in response.json()["detail"]


def test_orion_performance_route_returns_recommendations() -> None:
    with patch("app.api.routes.orion.orion_brain.performance_summary") as mock_summary:
        mock_summary.return_value = {
            "lookback_days": 14,
            "live_trades": {"total_trades": 3},
            "paper_trades": {"total_rows": 5},
            "recommendations": ["Keep sample size growing."],
        }
        response = client.get("/agents/orion/performance?agent_id=agent-1&days=14")

    assert response.status_code == 200
    body = response.json()
    assert body["lookback_days"] == 14
    assert body["recommendations"]


def test_orion_performance_route_rejects_days_out_of_range() -> None:
    response = client.get("/agents/orion/performance?agent_id=agent-1&days=0")

    assert response.status_code == 422


def test_orion_smoke_run_route_returns_summary() -> None:
    payload = {
        "agent_id": "32e17c5d-ecb7-467f-8a32-b8cc8c3ddc21",
        "symbols": ["ES", "NQ"],
        "timeframe": "5m",
        "days": 14,
    }
    with patch("app.api.routes.orion.orion_brain.smoke_run") as mock_smoke:
        mock_smoke.return_value = {
            "success": True,
            "agent_id": payload["agent_id"],
            "ingest_status": "ingested",
            "scan_status": "ready",
            "setup_count": 2,
            "paper_status": "opened",
            "live_trades": {"total_trades": 1},
            "paper_trades": {"closed_trades": 1},
            "recommendations": ["Keep sample size growing."],
        }
        response = client.post("/agents/orion/smoke-run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["setup_count"] == 2


def test_orion_smoke_run_route_rejects_invalid_timeframe() -> None:
    payload = {
        "agent_id": "32e17c5d-ecb7-467f-8a32-b8cc8c3ddc21",
        "symbols": ["ES"],
        "timeframe": "2m",
    }
    response = client.post("/agents/orion/smoke-run", json=payload)

    assert response.status_code == 422
    assert "Invalid timeframe" in response.json()["detail"]


def test_orion_learn_outcomes_route() -> None:
    payload = {"owner_id": "owner-1"}
    with patch("app.api.routes.orion.orion_brain.learn_from_outcomes") as mock_learn:
        mock_learn.return_value = {
            "status": "updated",
            "owner_id": "owner-1",
            "improvements_made": 3,
            "plan": {},
        }
        response = client.post("/agents/orion/learn-outcomes", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
