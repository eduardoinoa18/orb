"""Tests for InputValidator, settings store, and setup wizard routes — Modules 4 S3 + 2 Z1-Z2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# InputValidator
# ---------------------------------------------------------------------------

class TestSanitizeText:

    def test_strips_script_tags(self):
        from app.api.middleware.validation import sanitize_text
        result = sanitize_text('<script>alert("xss")</script>Hello')
        assert "<script>" not in result
        assert "Hello" in result

    def test_plain_text_passthrough(self):
        from app.api.middleware.validation import sanitize_text
        assert sanitize_text("Hello world") == "Hello world"

    def test_allow_html_keeps_safe_tags(self):
        from app.api.middleware.validation import sanitize_text
        result = sanitize_text("<b>bold</b><script>bad</script>", allow_html=True)
        assert "<b>" in result
        assert "<script>" not in result

    def test_non_string_raises(self):
        from app.api.middleware.validation import sanitize_text
        with pytest.raises((ValueError, TypeError)):
            sanitize_text(123)  # type: ignore


class TestValidateEmail:

    def test_valid_email(self):
        from app.api.middleware.validation import validate_email
        assert validate_email("Test@Example.COM") == "test@example.com"

    def test_invalid_email_raises(self):
        from app.api.middleware.validation import validate_email
        with pytest.raises(ValueError):
            validate_email("not-an-email")

    def test_missing_tld_raises(self):
        from app.api.middleware.validation import validate_email
        with pytest.raises(ValueError):
            validate_email("user@domain")


class TestValidatePhone:

    def test_valid_us_phone(self):
        from app.api.middleware.validation import validate_phone
        result = validate_phone("(202) 555-1234", "US")
        assert result == "+12025551234"

    def test_invalid_phone_raises(self):
        from app.api.middleware.validation import validate_phone
        with pytest.raises(ValueError):
            validate_phone("not-a-phone", "US")

    def test_e164_already_formatted(self):
        from app.api.middleware.validation import validate_phone
        result = validate_phone("+12025551234")
        assert result == "+12025551234"


class TestValidateUrl:

    def test_valid_https_url(self):
        from app.api.middleware.validation import validate_url
        result = validate_url("https://example.com/path")
        assert result == "https://example.com/path"

    def test_http_rejected_by_default(self):
        from app.api.middleware.validation import validate_url
        with pytest.raises(ValueError):
            validate_url("http://example.com")

    def test_http_allowed_when_flag_false(self):
        from app.api.middleware.validation import validate_url
        result = validate_url("http://example.com", https_only=False)
        assert result.startswith("http://")

    def test_invalid_url_raises(self):
        from app.api.middleware.validation import validate_url
        with pytest.raises(ValueError):
            validate_url("javascript:alert(1)")


class TestValidateApiKeyFormat:

    def test_valid_orb_key(self):
        from app.api.middleware.validation import validate_api_key_format
        result = validate_api_key_format("orb_abcdef12345678")
        assert result == "orb_abcdef12345678"

    def test_wrong_prefix_raises(self):
        from app.api.middleware.validation import validate_api_key_format
        with pytest.raises(ValueError):
            validate_api_key_format("sk-ant-my-key")

    def test_too_short_raises(self):
        from app.api.middleware.validation import validate_api_key_format
        with pytest.raises(ValueError):
            validate_api_key_format("orb_ab")


class TestInputValidatorSingleton:

    def test_singleton(self):
        from app.api.middleware.validation import get_input_validator
        a = get_input_validator()
        b = get_input_validator()
        assert a is b


# ---------------------------------------------------------------------------
# SettingsStore (mocked DB)
# ---------------------------------------------------------------------------

class TestSettingsStore:

    def _make_store(self):
        """Return a SettingsStore with a mocked Supabase client."""
        from app.database.settings_store import SettingsStore
        store = SettingsStore.__new__(SettingsStore)
        from integrations.encryption import EncryptionManager
        store._em = EncryptionManager("test-encryption-secret-for-unit-tests")
        store._db = MagicMock()
        return store

    def test_save_new_setting(self):
        store = self._make_store()
        store._get_row = MagicMock(return_value=None)
        mock_result = MagicMock()
        mock_result.data = [{"id": "abc", "key": "my_key"}]
        store._db.client.table.return_value.insert.return_value.execute.return_value = mock_result
        result = store.save("my_key", "my_value", category="ai")
        assert result["saved"] is True
        assert result["key_name"] == "my_key"

    def test_get_existing_setting(self):
        store = self._make_store()
        encrypted = store._em.encrypt("real-api-key")
        store._get_row = MagicMock(return_value={"key": "my_key", "value": encrypted})
        result = store.get("my_key")
        assert result == "real-api-key"

    def test_get_missing_returns_default(self):
        store = self._make_store()
        store._get_row = MagicMock(return_value=None)
        assert store.get("no_such_key", default="fallback") == "fallback"

    def test_delete_setting(self):
        store = self._make_store()
        mock_result = MagicMock()
        mock_result.data = [{"id": "abc"}]
        store._db.client.table.return_value.delete.return_value.eq.return_value.execute.return_value = mock_result
        assert store.delete("my_key") is True

    def test_list_settings_returns_list(self):
        store = self._make_store()
        mock_result = MagicMock()
        mock_result.data = [{"key": "k1", "category": "ai"}]
        (store._db.client.table.return_value
             .select.return_value
             .order.return_value
             .order.return_value
             .execute.return_value) = mock_result
        result = store.list_settings()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Setup wizard routes
# ---------------------------------------------------------------------------

class TestSetupRoutes:

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.api.routes.setup import router
        test_app = FastAPI()
        test_app.include_router(router)
        return TestClient(test_app)

    def test_setup_status_ok(self, client):
        with patch("app.api.routes.setup.SettingsStore") as MockStore:
            MockStore.return_value.get.return_value = ""
            resp = client.get("/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "setup_complete" in data
        assert "checklist" in data

    def test_setup_status_db_unavailable(self, client):
        with patch("app.api.routes.setup.SettingsStore", side_effect=Exception("db down")):
            resp = client.get("/setup/status")
        assert resp.status_code == 200  # graceful fallback
        assert resp.json()["setup_complete"] is False

    def test_list_categories(self, client):
        resp = client.get("/setup/categories")
        assert resp.status_code == 200
        cats = resp.json()["categories"]
        assert isinstance(cats, list)
        assert len(cats) >= 4

    def test_setup_schema_readiness_endpoint(self, client):
        with patch("app.api.routes.setup.schema_readiness_payload") as mock_payload:
            mock_payload.return_value = {
                "ready": False,
                "checks": [{"label": "activity_log.metadata", "ok": False, "detail": "missing", "fix_sql": "ALTER ..."}],
            }
            resp = client.get("/setup/schema-readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert isinstance(data["checks"], list)

    def test_setup_preflight_endpoint(self, client):
        with patch("app.api.routes.setup.build_preflight_report") as mock_report:
            mock_report.return_value = {
                "ready": False,
                "score": 64,
                "summary": {"blocker_count": 1, "warning_count": 2},
                "blockers": [{"code": "schema_not_ready"}],
                "warnings": [{"code": "warn_openai_api_key"}],
                "schema": {"ready": False, "checks": []},
            }
            resp = client.get("/setup/preflight")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["score"] == 64
        assert payload["summary"]["blocker_count"] == 1

    @patch("app.database.settings_store.SettingsStore.save")
    def test_save_key_route(self, mock_save, client):
        mock_save.return_value = {"saved": True, "key_name": "anthropic_api_key", "id": "xyz"}
        resp = client.post("/setup/save-key", json={
            "key_name": "anthropic_api_key",
            "value": "sk-ant-xxxxx",
            "category": "ai",
        })
        assert resp.status_code == 200
        assert resp.json()["saved"] is True

    def test_save_key_validation_error(self, client):
        resp = client.post("/setup/save-key", json={"key_name": "x", "value": "v"})
        assert resp.status_code == 422

    @patch("app.database.settings_store.SettingsStore.test_connection_to_ai")
    def test_test_key_stored(self, mock_test, client):
        mock_test.return_value = {"valid": True, "service": "anthropic", "error": None}
        resp = client.post("/setup/test-key", json={
            "key_name": "anthropic_api_key",
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    @patch("agents.identity.provisioner.provision_agent")
    def test_provision_first_agent(self, mock_prov, client):
        mock_prov.return_value = {"status": "provisioned", "agent_id": "agent_001"}
        resp = client.post("/setup/provision-first-agent", json={
            "owner_id": "owner_123",
            "agent_name": "Rex",
        })
        assert resp.status_code == 200
        assert resp.json()["provisioned"] is True


# ---------------------------------------------------------------------------
# Rate limiter module sanity
# ---------------------------------------------------------------------------

class TestRateLimitModule:

    def test_limiter_is_importable(self):
        from app.api.middleware.rate_limit import limiter, RATE_AUTH, RATE_AGENT
        assert limiter is not None
        assert RATE_AUTH == "10/minute"
        assert RATE_AGENT == "30/minute"
