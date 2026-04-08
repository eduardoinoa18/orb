"""Tests for Level 6 dashboard API endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from jose import jwt

from app.api.main import app
from app.database.connection import DatabaseConnectionError
from config.settings import get_settings

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    """Builds a valid bearer token for protected route tests."""
    settings = get_settings()
    token = jwt.encode({"sub": "test-owner"}, settings.jwt_secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_overview_returns_expected_shape() -> None:
    """Overview should include agents, feed, approvals, and stats."""
    with patch("app.api.routes.dashboard._safe_fetch") as mock_fetch:
        # order: agents, activity, leads, paper_trades
        mock_fetch.side_effect = [
            [{"id": "a1", "name": "Rex", "role": "sales", "status": "active"}],
            [
                {
                    "id": "act-1",
                    "agent_id": "a1",
                    "action_type": "call",
                    "description": "Called lead",
                    "created_at": "2026-03-27T10:00:00+00:00",
                    "needs_approval": True,
                    "cost_cents": 10,
                }
            ],
            [{"id": "l1", "created_at": "2026-03-27T08:00:00+00:00"}],
            [{"id": "p1", "created_at": "2026-03-27T09:00:00+00:00", "pnl_dollars": 12.5}],
        ]

        response = client.get("/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert "agents" in body
    assert "activity_feed" in body
    assert "approval_queue" in body
    assert "stats" in body


def test_dashboard_pipeline_groups_statuses() -> None:
    """Pipeline endpoint should return grouped lead buckets."""
    with patch("app.api.routes.dashboard._safe_fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": "l1", "status": "new"},
            {"id": "l2", "status": "qualified"},
            {"id": "l3", "status": "offer"},
        ]
        response = client.get("/dashboard/pipeline")

    assert response.status_code == 200
    body = response.json()
    assert "pipeline" in body
    assert "new" in body["pipeline"]
    assert len(body["pipeline"]["qualified"]) == 1


def test_dashboard_approvals_filters_pending_items() -> None:
    """Approvals endpoint should only return items needing approval."""
    with patch("app.api.routes.dashboard._safe_fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": "a1", "needs_approval": True, "created_at": "2026-03-27T10:00:00+00:00"},
            {"id": "a2", "needs_approval": False, "created_at": "2026-03-27T09:00:00+00:00"},
        ]
        response = client.get("/dashboard/approvals")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["approvals"][0]["id"] == "a1"


def test_dashboard_approve_returns_approved_status() -> None:
    """Approve endpoint should mark item approved."""
    with patch("app.api.routes.dashboard.SupabaseService") as mock_db:
        mock_db.return_value.update_many.return_value = [{"id": "act-1"}]
        response = client.post("/dashboard/approve/act-1", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_dashboard_reject_returns_rejected_status() -> None:
    """Reject endpoint should mark item rejected with reason."""
    with patch("app.api.routes.dashboard.SupabaseService") as mock_db:
        mock_db.return_value.update_many.return_value = [{"id": "act-2"}]
        response = client.post(
            "/dashboard/reject/act-2",
            json={"reason": "Needs rewrite"},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reason"] == "Needs rewrite"


def test_dashboard_integrations_returns_snapshot() -> None:
    """Integration snapshot endpoint should expose readiness counters and controls."""
    with patch("app.api.routes.dashboard._integration_snapshot") as mock_snapshot:
        mock_snapshot.return_value = {
            "integrations": [
                {"key": "supabase", "status": "ready", "configured": True, "details": {}},
                {"key": "openai", "status": "warning", "configured": True, "details": {}},
            ],
            "ui_controls": {
                "computer_use_enabled": False,
                "computer_use_screenshot_dir": "artifacts/screenshots",
                "token_cache_ttl_minutes": 1440,
            },
        }
        response = client.get("/dashboard/integrations")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["ready_count"] == 1
    assert "ui_controls" in body


def test_dashboard_integrations_live_check_returns_results() -> None:
    """Live-check endpoint should aggregate normalized check results."""
    with patch("app.api.routes.dashboard._run_live_check") as mock_live:
        mock_live.side_effect = [
            {"check": "supabase", "ok": True, "detail": "Connected"},
            {"check": "openai", "ok": False, "detail": "Invalid key"},
        ]
        response = client.post(
            "/dashboard/integrations/live-check",
            json={"checks": ["supabase", "openai"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["passed"] == 1
    assert body["failed"] == 1


def test_dashboard_command_center_returns_combined_payload() -> None:
    """Command center endpoint should combine overview, pipeline, approvals, and integrations."""
    with patch("app.api.routes.dashboard.dashboard_overview") as mock_overview:
        with patch("app.api.routes.dashboard.dashboard_pipeline") as mock_pipeline:
            with patch("app.api.routes.dashboard.dashboard_approvals") as mock_approvals:
                with patch("app.api.routes.dashboard.dashboard_integrations") as mock_integrations:
                    with patch("app.api.routes.dashboard.dashboard_ai_brains") as mock_brains:
                        with patch("app.api.routes.dashboard.dashboard_improvements") as mock_improvements:
                            with patch("app.api.routes.dashboard.dashboard_notifications") as mock_notifications:
                                with patch("app.api.routes.dashboard._build_setup_checklist") as mock_setup:
                                    mock_overview.return_value = {"stats": {"leads_today": 1}}
                                    mock_pipeline.return_value = {"pipeline": {"new": []}}
                                    mock_approvals.return_value = {"approvals": [], "count": 0}
                                    mock_integrations.return_value = {"integrations": [], "ready_count": 0, "total": 0}
                                    mock_brains.return_value = {"brains": [], "routing_modes": {}}
                                    mock_improvements.return_value = {"improvements": [], "proposed_count": 0}
                                    mock_notifications.return_value = {"notifications": [], "unread_count": 0}
                                    mock_setup.return_value = {"steps": [], "summary": {"ready": 0, "attention": 0, "total": 0}}
                                    response = client.get("/dashboard/command-center")

    assert response.status_code == 200
    body = response.json()
    assert "overview" in body
    assert "pipeline" in body
    assert "approvals" in body
    assert "integrations" in body
    assert "brains" in body
    assert "improvements" in body
    assert "notifications" in body
    assert "setup" in body
    assert "generated_at" in body


def test_dashboard_setup_checklist_returns_steps() -> None:
    """Setup checklist endpoint should return summary and step list for the wizard UI."""
    with patch("app.api.routes.dashboard._build_setup_checklist") as mock_setup:
        mock_setup.return_value = {
            "steps": [
                {"id": "dashboard-open", "title": "Open dashboard shell", "status": "ready"},
            ],
            "summary": {"ready": 1, "attention": 0, "total": 1},
        }
        response = client.get("/dashboard/setup-checklist")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 1
    assert body["steps"][0]["id"] == "dashboard-open"


def test_dashboard_ai_brains_returns_inventory() -> None:
    """AI brain endpoint should return provider cards and routing modes."""
    response = client.get("/dashboard/ai-brains", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert "brains" in body
    assert "routing_modes" in body
    assert len(body["brains"]) >= 5


def test_dashboard_improvements_returns_fallback_items() -> None:
    """Improvements endpoint should return proposals even if DB table is unavailable."""
    with patch("app.api.routes.dashboard.SupabaseService", side_effect=Exception("no table")):
        response = client.get("/dashboard/improvements", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert "improvements" in body
    assert body["proposed_count"] >= 1


def test_dashboard_improvement_approve_fallback() -> None:
    """Approve endpoint should work against fallback improvement data."""
    with patch("app.api.routes.dashboard.SupabaseService", side_effect=DatabaseConnectionError("db down")):
        response = client.post(
            "/dashboard/improvements/imp-rex-routing/approve",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_dashboard_improvement_reject_fallback() -> None:
    """Reject endpoint should work against fallback improvement data."""
    with patch("app.api.routes.dashboard.SupabaseService", side_effect=DatabaseConnectionError("db down")):
        response = client.post(
            "/dashboard/improvements/imp-atlas-security/reject",
            json={"reason": "Too aggressive for now"},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reason"] == "Too aggressive for now"


def test_dashboard_notifications_returns_drawer_payload() -> None:
    """Notification endpoint should return unread count and items."""
    with patch("app.api.routes.dashboard.dashboard_approvals", return_value={"approvals": [{"id": "a1"}] }):
        response = client.get("/dashboard/notifications", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert "notifications" in body
    assert body["unread_count"] >= 1
