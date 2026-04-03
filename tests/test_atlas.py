"""Tests for Atlas developer agent — Module 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_claude_response(text: str) -> dict:
    return {"text": text, "usage": {"input_tokens": 10, "output_tokens": 20}}


# ---------------------------------------------------------------------------
# CodeGenerator
# ---------------------------------------------------------------------------

class TestCodeGenerator:

    def _make_brain(self, response_text: str):
        """Return an AtlasBrain whose _call_standard is mocked."""
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_standard = MagicMock(return_value=_mock_claude_response(response_text))
        brain._call_heavy = MagicMock(return_value=_mock_claude_response(response_text))
        return brain

    def test_generate_feature_success(self):
        from agents.atlas.code_generator import CodeGenerator
        response_json = '{"code": "def foo(): pass", "explanation": "A foo function.", "tests": "def test_foo(): pass"}'
        brain = self._make_brain(response_json)
        gen = CodeGenerator(brain=brain)
        result = gen.generate_feature("Add a foo function", "owner_1", [])
        assert result["code"] == "def foo(): pass"
        assert result["explanation"] == "A foo function."
        assert "model_used" in result

    def test_generate_feature_fallback_on_api_error(self):
        from agents.atlas.code_generator import CodeGenerator
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_standard = MagicMock(side_effect=RuntimeError("API error"))
        gen = CodeGenerator(brain=brain)
        result = gen.generate_feature("A failing feature request here", "owner_1", [])
        assert result["model_used"] == "fallback"
        assert "code" in result

    def test_generate_feature_bad_json_fallback(self):
        from agents.atlas.code_generator import CodeGenerator
        brain = self._make_brain("not valid json at all{{{")
        gen = CodeGenerator(brain=brain)
        result = gen.generate_feature("Add something interesting here", "owner_1", [])
        assert result["model_used"] == "fallback"

    def test_context_files_truncated(self):
        """Providing context files should be accepted without error."""
        from agents.atlas.code_generator import CodeGenerator
        response_json = '{"code": "x=1", "explanation": "sets x", "tests": ""}'
        brain = self._make_brain(response_json)
        gen = CodeGenerator(brain=brain)
        result = gen.generate_feature("Set x to 1", "owner_1", ["a" * 1000, "b" * 1000])
        assert result["code"] == "x=1"


# ---------------------------------------------------------------------------
# BugDetective
# ---------------------------------------------------------------------------

class TestBugDetective:

    def _make_brain(self, response_text: str):
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_standard = MagicMock(return_value=_mock_claude_response(response_text))
        return brain

    def test_diagnose_success(self):
        from agents.atlas.bug_detective import BugDetective
        response_json = '{"root_cause": "NullPointerException", "fix": "Check for None", "affected_files": ["main.py"], "confidence": "high"}'
        brain = self._make_brain(response_json)
        det = BugDetective(brain=brain)
        result = det.diagnose_error("NullPointerException", "traceback here", "", "rex")
        assert result["confidence"] == "high"
        assert "main.py" in result["affected_files"]

    def test_diagnose_fallback(self):
        from agents.atlas.bug_detective import BugDetective
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_standard = MagicMock(side_effect=RuntimeError("boom"))
        det = BugDetective(brain=brain)
        result = det.diagnose_error("Error X", "", "", "")
        assert result["model_used"] == "fallback"
        assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# ArchitectureAdvisor
# ---------------------------------------------------------------------------

class TestArchitectureAdvisor:

    def _make_brain(self, response_text: str):
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_heavy = MagicMock(return_value=_mock_claude_response(response_text))
        return brain

    def test_advise_success(self):
        from agents.atlas.architecture_advisor import ArchitectureAdvisor
        response_json = (
            '{"recommendation": "Use REST", "risks": ["latency"], '
            '"alternatives": ["GraphQL"], "effort_estimate": "days", '
            '"data_model_changes": [], "api_endpoints": ["/users"]}'
        )
        brain = self._make_brain(response_json)
        adv = ArchitectureAdvisor(brain=brain)
        result = adv.advise("Add user management", "owner_1")
        assert result["effort_estimate"] == "days"
        assert "/users" in result["api_endpoints"]

    def test_advise_fallback(self):
        from agents.atlas.architecture_advisor import ArchitectureAdvisor
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain.__new__(AtlasBrain)
        brain._call_heavy = MagicMock(side_effect=RuntimeError("boom"))
        adv = ArchitectureAdvisor(brain=brain)
        result = adv.advise("Something interesting to build", "owner_1")
        assert result["model_used"] == "fallback"


# ---------------------------------------------------------------------------
# AtlasBrain.security_scan
# ---------------------------------------------------------------------------

class TestAtlasBrainSecurityScan:

    @patch("agents.atlas.atlas_brain.ask_claude_smart")
    def test_security_scan_success(self, mock_claude):
        from agents.atlas.atlas_brain import AtlasBrain
        mock_claude.return_value = {
            "text": '{"findings": [], "overall_severity": "low", "recommendation": "Looks good"}',
            "usage": {},
        }
        brain = AtlasBrain.__new__(AtlasBrain)
        result = brain.security_scan("def hello(): return 'world'", "hello.py")
        assert result["overall_severity"] == "low"
        assert isinstance(result["findings"], list)

    @patch("agents.atlas.atlas_brain.ask_claude_smart")
    def test_security_scan_fallback_on_error(self, mock_claude):
        from agents.atlas.atlas_brain import AtlasBrain
        mock_claude.side_effect = RuntimeError("boom")
        brain = AtlasBrain.__new__(AtlasBrain)
        result = brain.security_scan("import os; os.system(input())")
        assert result["overall_severity"] == "unknown"
        assert "error" in result


# ---------------------------------------------------------------------------
# Atlas API routes
# ---------------------------------------------------------------------------

class TestAtlasRoutes:

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.api.routes.atlas import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_atlas_status(self, client):
        resp = client.get("/agents/atlas/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "Atlas"

    @patch("agents.atlas.atlas_brain.AtlasBrain.generate_feature")
    def test_generate_feature_route(self, mock_gf, client):
        mock_gf.return_value = {"code": "def foo(): pass", "explanation": "A function"}
        resp = client.post("/agents/atlas/generate", json={
            "feature_description": "Add a foo function here that does something",
            "owner_id": "owner_123",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == "def foo(): pass"

    @patch("agents.atlas.atlas_brain.AtlasBrain.diagnose_error")
    def test_diagnose_route(self, mock_diag, client):
        mock_diag.return_value = {"root_cause": "NullRef", "fix": "check None", "confidence": "high"}
        resp = client.post("/agents/atlas/diagnose", json={
            "error_message": "AttributeError: NoneType has no attribute x",
            "stack_trace": "Traceback ...",
        })
        assert resp.status_code == 200
        assert resp.json()["root_cause"] == "NullRef"

    @patch("agents.atlas.atlas_brain.AtlasBrain.advise_on_feature")
    def test_advise_route(self, mock_adv, client):
        mock_adv.return_value = {"recommendation": "Use REST API pattern for this", "effort_estimate": "days"}
        resp = client.post("/agents/atlas/advise", json={
            "feature_request": "Add user management with roles and permissions",
            "owner_id": "owner_123",
        })
        assert resp.status_code == 200
        assert "recommendation" in resp.json()

    @patch("agents.atlas.atlas_brain.AtlasBrain.security_scan")
    def test_security_scan_route(self, mock_scan, client):
        mock_scan.return_value = {"findings": [], "overall_severity": "low"}
        resp = client.post("/agents/atlas/security-scan", json={
            "code_snippet": "def safe_function():\n    return 'hello world'",
        })
        assert resp.status_code == 200

    def test_build_history_returns_dict(self, client):
        resp = client.get("/agents/atlas/build-history")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_generate_feature_too_short_fails(self, client):
        resp = client.post("/agents/atlas/generate", json={
            "feature_description": "short",
            "owner_id": "o",
        })
        assert resp.status_code == 422
