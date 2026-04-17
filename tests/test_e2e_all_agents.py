"""End-to-end smoke test for core ORB agent APIs.

Covers Aria, Rex, Nova, Orion, Sage, and Computer Use in one flow.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(
    app,
    raise_server_exceptions=False,
    headers={"Authorization": "Bearer orb-test-token"},
)


def test_all_agents_e2e_smoke_flow() -> None:
    """Exercises one representative endpoint per agent and validates responses."""

    # 1) Aria briefing
    with patch("app.api.routes.aria.briefing.generate_and_send_briefing") as mock_briefing:
        mock_briefing.return_value = {
            "success": True,
            "send_error": None,
            "sent_to": "+15551234567",
            "tasks_included": 2,
            "trading_summary": {"trade_count": 1, "winners": 1, "pnl": 120.0, "status": "paper trades closed"},
            "leads_summary": {"hot": 1, "warm": 2, "cold": 3},
            "daily_cost": 2.3,
            "briefing_text": "Good morning!",
        }
        aria_resp = client.post("/aria/briefing/send-now", json={})
    assert aria_resp.status_code == 200
    assert aria_resp.json()["status"] == "briefing_sent"

    # 2) Rex learn-owner and learn-outcomes
    rex_owner_payload = {
        "owner_id": "owner-1",
        "product_description": "We provide real estate brokerage services for families moving across Florida.",
        "ideal_customer_profile": "Home buyers and sellers needing local market expertise and guided transactions.",
        "common_objections": ["Need to think about it"],
        "successful_close_examples": ["Closed in 18 days after targeted pricing strategy"],
    }
    with patch("app.api.routes.rex.rex_brain.learn_from_owner") as mock_learn_owner:
        mock_learn_owner.return_value = {"status": "learned", "owner_id": "owner-1"}
        rex_owner_resp = client.post("/agents/rex/learn-owner", json=rex_owner_payload)
    assert rex_owner_resp.status_code == 200

    with patch("app.api.routes.rex.rex_brain.learn_from_outcomes") as mock_rex_outcomes:
        mock_rex_outcomes.return_value = {"status": "updated", "owner_id": "owner-1", "improvements_made": 1}
        rex_outcomes_resp = client.post("/agents/rex/learn-outcomes", json={"owner_id": "owner-1"})
    assert rex_outcomes_resp.status_code == 200

    # 3) Nova listing post
    nova_payload = {
        "owner_id": "owner-1",
        "property_data": {
            "address": "123 Main St",
            "city": "Tampa",
            "price": "$450,000",
            "beds": 3,
            "baths": 2,
            "sqft": 1850,
        },
        "platforms": ["instagram", "facebook", "linkedin"],
    }
    with patch("app.api.routes.content.creator.create_listing_post") as mock_listing:
        mock_listing.return_value = {"created": 3, "content": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]}
        nova_resp = client.post("/agents/nova/listing-post", json=nova_payload)
    assert nova_resp.status_code == 200
    assert nova_resp.json()["created"] == 3

    # 4) Orion smoke run
    with patch("app.api.routes.orion.orion_brain.smoke_run") as mock_orion:
        mock_orion.return_value = {
            "status": "ok",
            "strategy_name": "ORB Level 8 Momentum",
            "scan": {"setups": [{"symbol": "ES", "score": 7.2}]},
            "performance": {"win_rate": 56.0},
        }
        orion_resp = client.post(
            "/agents/orion/smoke-run",
            json={
                "agent_id": "orion-1",
                "strategy_name": "ORB Level 8 Momentum",
                "source_trader": "e2e-smoke",
                "notes": "End to end smoke run for agent validation.",
                "symbols": ["ES", "NQ"],
                "timeframe": "5m",
                "days": 14,
            },
        )
    assert orion_resp.status_code == 200

    # 5) Sage platform monitor
    with patch("app.api.routes.sage.sage_brain.run_platform_monitor") as mock_sage:
        mock_sage.return_value = {
            "status": "healthy",
            "severity": "normal",
            "metrics": {"api_response_ms": 210, "dependency_health": {}},
            "unhealthy_signals": [],
            "diagnosis": {"priority": "normal"},
        }
        sage_resp = client.post("/agents/sage/platform-monitor")
    assert sage_resp.status_code == 200
    assert sage_resp.json()["status"] in {"healthy", "attention_needed"}

    # 6) Computer-use safety check
    computer_resp = client.post(
        "/agents/computer-use/safety-check",
        json={"action": "open_website", "description": "Open analytics dashboard"},
    )
    assert computer_resp.status_code == 200
    assert "allowed" in computer_resp.json()
