"""Live no-mock smoke checks for core ORB routes.

These tests intentionally avoid patching/mocking to verify real route wiring.
"""

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_live_health_route_shape() -> None:
    """Health route returns expected top-level keys without mocks."""
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert "status" in body
    assert "platform" in body
    assert "version" in body
    assert "dependencies" in body


def test_live_agent_status_routes() -> None:
    """Core agent status routes are reachable without mocks."""
    paths = [
        "/agents/rex/status",
        "/agents/orion/status",
        "/agents/nova/status",
        "/agents/sage/status",
        "/agents/computer-use/status",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"Unexpected status for {path}"
        payload = response.json()
        assert isinstance(payload, dict)
        assert "status" in payload


def test_live_aria_briefing_preview_route() -> None:
    """Aria preview endpoint works end-to-end (degraded data is acceptable)."""
    response = client.get("/aria/briefing/preview")
    assert response.status_code == 200

    body = response.json()
    assert body.get("status") == "preview_ready"
    assert isinstance(body.get("briefing_text"), str)
    assert "Good morning" in body["briefing_text"]
