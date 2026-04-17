"""Tests for agent-skills routes."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.api.main import app
from fastapi.testclient import TestClient


client = TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


def test_get_agent_skills_returns_profile_payload() -> None:
    fake_profile = SimpleNamespace(
        core_skills=["lead_qualify"],
        expanded_skills=["report_writing"],
        pending_skills=["voice_briefing"],
        skill_scores={"lead_qualify": 0.9},
        business_adaptations=["Focus on short qualifying questions."],
        last_review=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )

    with patch("app.api.routes.agent_skills.AgentSkillEngine.load_skill_profile", return_value=fake_profile), \
         patch("app.api.routes.agent_skills.AgentSkillEngine.build_skill_context", return_value="CTX"):
        response = client.get("/agent-skills/rex")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_slug"] == "rex"
    assert payload["core_skills"] == ["lead_qualify"]
    assert payload["expanded_skills"] == ["report_writing"]
    assert payload["pending_skills"] == ["voice_briefing"]
    assert payload["skill_context"] == "CTX"


def test_get_agent_skills_rejects_unknown_slug() -> None:
    response = client.get("/agent-skills/not-a-real-agent")
    assert response.status_code == 404


def test_run_agent_skill_review_returns_result() -> None:
    fake_result = {
        "status": "completed",
        "new_skills_expanded": ["report_writing"],
        "skills_requested": [],
    }

    with patch("app.api.routes.agent_skills.AgentSkillEngine.run_skill_review", return_value=fake_result):
        response = client.post("/agent-skills/rex/review", json={"lookback_days": 14})

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_slug"] == "rex"
    assert payload["lookback_days"] == 14
    assert payload["result"]["status"] == "completed"


def test_run_agent_skill_review_validates_lookback_days() -> None:
    response = client.post("/agent-skills/rex/review", json={"lookback_days": 0})
    assert response.status_code == 422
