"""Tests for Aria — Executive Assistant Agent (Level 4)."""

import pytest
from unittest.mock import patch
from agents.aria.briefing_engine import AriaBriefingEngine
from agents.aria.task_manager import AriaTaskManager


class TestAriaBriefingEngine:
    """Test briefing composition logic."""

    def test_compose_briefing_creates_string(self):
        """Test briefing composition with sample data."""
        engine = AriaBriefingEngine()
        tasks = [{"title": "Call customer", "due_at": "2026-03-27T14:00:00"}]
        trading = {"trade_count": 2, "winners": 1, "pnl": 150.0, "status": "paper trades closed"}
        leads = {"hot": 1, "warm": 2, "cold": 5}
        cost = 2.50
        
        briefing = engine.compose_briefing(tasks, trading, leads, cost)
        
        assert isinstance(briefing, str)
        assert "Good morning" in briefing
        assert "Call customer" in briefing
        assert "$2.50" in briefing

    def test_compose_briefing_handles_empty_data(self):
        """Test briefing composition with empty data."""
        engine = AriaBriefingEngine()
        briefing = engine.compose_briefing(
            tasks=[],
            trading={"trade_count": 0, "pnl": 0.0, "status": "no trades"},
            leads={"hot": 0, "warm": 0, "cold": 0},
            cost=0.0,
        )
        
        assert isinstance(briefing, str)
        assert "Good morning" in briefing
        assert "$0.00" in briefing

    def test_get_briefing_preview_returns_string(self):
        """Test that briefing preview returns a valid string."""
        engine = AriaBriefingEngine()
        with patch.object(engine, 'get_todays_tasks', return_value=[]):
            with patch.object(engine, 'get_trading_summary', return_value={"trade_count": 0, "pnl": 0}):
                with patch.object(engine, 'get_leads_summary', return_value={"hot": 0, "warm": 0, "cold": 0}):
                    with patch.object(engine, 'get_daily_cost', return_value=0.0):
                        preview = engine.get_briefing_preview()
                        assert isinstance(preview, str)
                        assert "Good morning" in preview


class TestAriaTaskManager:
    """Test task manager initialization."""

    def test_task_manager_initializes(self):
        """Test that task manager can be instantiated."""
        mgr = AriaTaskManager()
        assert mgr is not None
        assert hasattr(mgr, 'db')
        assert hasattr(mgr, 'settings')

    def test_complete_task_calls_update(self):
        """Test that complete_task properly delegates to update_task."""
        mgr = AriaTaskManager()
        with patch.object(mgr, 'update_task', return_value={"success": True}):
            result = mgr.complete_task(task_id="test-id")
            assert result["success"] is True

    def test_get_tasks_by_priority_structure(self):
        """Test get_tasks_by_priority returns proper structure."""
        mgr = AriaTaskManager()
        mock_tasks = [
            {"id": "1", "priority": "high", "status": "pending"},
            {"id": "2", "priority": "normal", "status": "pending"},
            {"id": "3", "priority": "low", "status": "pending"},
        ]
        with patch.object(mgr, 'get_tasks', return_value=mock_tasks):
            organized = mgr.get_tasks_by_priority()
            assert isinstance(organized, dict)
            assert "high" in organized
            assert "normal" in organized
            assert "low" in organized
            assert len(organized["high"]) == 1
            assert len(organized["normal"]) == 1
            assert len(organized["low"]) == 1


class TestAriaAPIEndpoints:
    """Test Aria API routes via FastAPI TestClient."""

    def test_briefing_preview_endpoint(self, client):
        """Test GET /aria/briefing/preview returns briefing text."""
        response = client.get("/aria/briefing/preview")
        assert response.status_code == 200
        data = response.json()
        assert "briefing_text" in data
        assert "status" in data

    def test_briefing_summary_endpoint(self, client):
        """Test GET /aria/briefing/summary returns components."""
        response = client.get("/aria/briefing/summary")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "trading" in data
        assert "leads" in data
        assert "daily_cost_dollars" in data

    def test_list_tasks_endpoint(self, client):
        """Test GET /aria/tasks returns task list."""
        response = client.get("/aria/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "tasks" in data
        assert "count" in data

    def test_list_tasks_by_priority_endpoint(self, client):
        """Test GET /aria/tasks/by-priority returns organized tasks."""
        response = client.get("/aria/tasks/by-priority")
        assert response.status_code == 200
        data = response.json()
        assert "by_priority" in data
        assert "total" in data

    def test_aria_learn_outcomes_endpoint(self, client):
        """Test POST /aria/learn-outcomes returns addendum learning summary."""
        with patch("app.api.routes.aria.aria_brain.learn_from_outcomes") as mock_learn:
            mock_learn.return_value = {
                "status": "updated",
                "owner_id": "owner-1",
                "improvements_made": 2,
                "plan": {},
            }
            response = client.post("/aria/learn-outcomes", json={"owner_id": "owner-1"})

        assert response.status_code == 200
        assert response.json()["status"] == "updated"

    def test_aria_learn_owner_style_endpoint(self, client):
        """Test POST /aria/learn-owner-style adapts owner communication hints."""
        with patch("app.api.routes.aria.aria_brain.learn_owner_style") as mock_style:
            mock_style.return_value = {
                "status": "adapted",
                "owner_id": "owner-1",
                "agent_id": "owner-1",
                "owner_style": {"tone": "direct"},
            }
            response = client.post("/aria/learn-owner-style", json={"owner_id": "owner-1"})

        assert response.status_code == 200
        assert response.json()["status"] == "adapted"
