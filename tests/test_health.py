"""Tests for the ORB health endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_health_endpoint_returns_platform_metadata() -> None:
    """Health endpoint should include platform and version info."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "ORB"
    assert "version" in data
    assert "status" in data
    assert "preflight" in data
    assert data["mode"] == "standard"
    assert "deployment" in data
    assert "commit" in data["deployment"]


def test_health_endpoint_includes_dependencies_section() -> None:
    """Health endpoint should report dependency status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "dependencies" in data
    assert "supabase" in data["dependencies"]
    assert "anthropic" in data["dependencies"]
    assert "openai" in data["dependencies"]
    assert "ready" in data["preflight"]
    assert "score" in data["preflight"]
    assert data["dependencies"]["openai"]["required"] is False


def test_health_endpoint_each_dependency_has_status_field() -> None:
    """Each dependency should report its own status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    for dep_name, dep_info in data["dependencies"].items():
        assert "status" in dep_info, f"{dep_name} missing status field"
        assert dep_info["status"] in ["healthy", "unhealthy"]


def test_health_endpoint_overall_status_reflects_dependencies() -> None:
    """Overall status should reflect only required dependencies."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    all_required_deps_healthy = all(
        dep["status"] == "healthy"
        for dep in data["dependencies"].values()
        if dep.get("required", True)
    )
    expected_status = "healthy" if all_required_deps_healthy else "degraded"
    assert data["status"] == expected_status


def test_health_endpoint_marks_missing_openai_as_optional() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["openai"]["required"] is False
    assert "configured" in data["dependencies"]["openai"]


def test_health_endpoint_supports_deep_mode_flag() -> None:
    response = client.get("/health?deep=true")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "deep"


def test_health_endpoint_uses_supabase_client_probe() -> None:
    table_query = MagicMock()
    table_query.select.return_value.limit.return_value.execute.return_value = {"data": []}
    fake_db = MagicMock()
    fake_db.client.table.return_value = table_query

    with patch("app.api.main.SupabaseService", return_value=fake_db):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["supabase"]["status"] == "healthy"
    fake_db.client.table.assert_called_once_with("activity_log")

