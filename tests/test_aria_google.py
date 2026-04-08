"""Tests for Google OAuth integration — email handler, calendar manager, briefing update."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app, raise_server_exceptions=False)


# ─── google_client ──────────────────────────────────────────────────────────────


class TestGoogleClient:
    def test_is_authorized_returns_false_when_no_token(self):
        """is_authorized() must return False when token file is absent."""
        with patch("integrations.google_client.TOKEN_PATH") as mock_path:
            mock_path.exists.return_value = False
            import integrations.google_client as gc
            # Patch at module level so get_credentials sees the mock path
            with patch.object(gc, "get_credentials", return_value=None):
                assert gc.is_authorized() is False

    def test_is_authorized_returns_true_when_credentials_valid(self):
        """is_authorized() returns True when get_credentials() returns a creds object."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        import integrations.google_client as gc
        with patch.object(gc, "get_credentials", return_value=mock_creds):
            assert gc.is_authorized() is True

    def test_exchange_code_returns_success_dict(self):
        """exchange_code() wraps the flow and returns success with email."""
        import integrations.google_client as gc

        mock_creds = MagicMock()
        mock_flow = MagicMock()
        mock_flow.credentials = mock_creds

        with patch("integrations.google_client.Flow.from_client_config", return_value=mock_flow):
            with patch.object(gc, "_save_credentials"):
                with patch.object(gc, "_get_authorized_email", return_value="owner@gmail.com"):
                    result = gc.exchange_code("fake-auth-code")

        assert result["success"] is True
        assert result["email"] == "owner@gmail.com"

    def test_exchange_code_returns_failure_on_exception(self):
        """exchange_code() catches exceptions and returns failure dict."""
        import integrations.google_client as gc

        with patch("integrations.google_client.Flow.from_client_config", side_effect=Exception("bad_code")):
            result = gc.exchange_code("bad_code")

        assert result["success"] is False
        assert "error" in result

    def test_get_gmail_service_returns_none_when_not_authorized(self):
        """get_gmail_service() returns None when no credentials exist."""
        import integrations.google_client as gc
        with patch.object(gc, "get_credentials", return_value=None):
            assert gc.get_gmail_service() is None

    def test_get_calendar_service_returns_none_when_not_authorized(self):
        """get_calendar_service() returns None when no credentials exist."""
        import integrations.google_client as gc
        with patch.object(gc, "get_credentials", return_value=None):
            assert gc.get_calendar_service() is None


# ─── AriaEmailHandler ──────────────────────────────────────────────────────────


class TestAriaEmailHandler:
    def test_returns_empty_when_not_authorized(self):
        """get_unread_today() returns [] without Google auth."""
        from agents.aria.email_handler import AriaEmailHandler
        with patch("agents.aria.email_handler.is_authorized", return_value=False):
            handler = AriaEmailHandler()
            assert handler.get_unread_today() == []

    def test_returns_empty_when_service_unavailable(self):
        """get_unread_today() returns [] when Gmail service cannot be built."""
        from agents.aria.email_handler import AriaEmailHandler
        with patch("agents.aria.email_handler.is_authorized", return_value=True):
            with patch("agents.aria.email_handler.get_gmail_service", return_value=None):
                handler = AriaEmailHandler()
                assert handler.get_unread_today() == []

    def test_returns_email_list_from_gmail(self):
        """get_unread_today() maps Gmail API response to expected dict shape."""
        from agents.aria.email_handler import AriaEmailHandler

        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "abc123"}]
        }
        mock_service.users().messages().get().execute.return_value = {
            "snippet": "Hello from test",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Alice <alice@example.com>"},
                    {"name": "Subject", "value": "Test subject"},
                ]
            },
        }

        with patch("agents.aria.email_handler.is_authorized", return_value=True):
            with patch("agents.aria.email_handler.get_gmail_service", return_value=mock_service):
                handler = AriaEmailHandler()
                emails = handler.get_unread_today()

        assert len(emails) == 1
        assert emails[0]["from_name"] == "Alice"
        assert emails[0]["from_email"] == "alice@example.com"
        assert emails[0]["subject"] == "Test subject"

    def test_count_returns_zero_when_not_authorized(self):
        """get_unread_count_today() returns 0 without auth."""
        from agents.aria.email_handler import AriaEmailHandler
        with patch("agents.aria.email_handler.is_authorized", return_value=False):
            handler = AriaEmailHandler()
            assert handler.get_unread_count_today() == 0

    def test_parse_from_with_display_name(self):
        """_parse_from() splits 'Name <email>' correctly."""
        from agents.aria.email_handler import _parse_from
        name, email = _parse_from("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_parse_from_bare_email(self):
        """_parse_from() handles bare email with no display name."""
        from agents.aria.email_handler import _parse_from
        name, email = _parse_from("john@example.com")
        assert email == "john@example.com"

    def test_clean_snippet_strips_html_entities(self):
        """_clean_snippet() removes HTML entities and truncates."""
        from agents.aria.email_handler import _clean_snippet
        result = _clean_snippet("Hello &amp; welcome &nbsp; to the platform " + "x" * 200)
        assert "&amp;" not in result
        assert len(result) <= 120


# ─── AriaCalendarManager ──────────────────────────────────────────────────────


class TestAriaCalendarManager:
    def test_returns_empty_when_not_authorized(self):
        """get_todays_events() returns [] without Google auth."""
        from agents.aria.calendar_manager import AriaCalendarManager
        with patch("agents.aria.calendar_manager.is_authorized", return_value=False):
            mgr = AriaCalendarManager()
            assert mgr.get_todays_events() == []

    def test_returns_empty_when_service_unavailable(self):
        """get_todays_events() returns [] when Calendar service cannot be built."""
        from agents.aria.calendar_manager import AriaCalendarManager
        with patch("agents.aria.calendar_manager.is_authorized", return_value=True):
            with patch("agents.aria.calendar_manager.get_calendar_service", return_value=None):
                mgr = AriaCalendarManager()
                assert mgr.get_todays_events() == []

    def test_returns_event_list_from_calendar(self):
        """get_todays_events() maps Google Calendar API response to expected shape."""
        from agents.aria.calendar_manager import AriaCalendarManager

        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Team standup",
                    "start": {"dateTime": "2026-03-31T09:00:00+00:00"},
                    "end": {"dateTime": "2026-03-31T09:30:00+00:00"},
                    "attendees": [{"email": "a@b.com"}, {"email": "c@d.com"}],
                    "location": "Zoom",
                }
            ]
        }

        with patch("agents.aria.calendar_manager.is_authorized", return_value=True):
            with patch("agents.aria.calendar_manager.get_calendar_service", return_value=mock_service):
                mgr = AriaCalendarManager()
                events = mgr.get_todays_events()

        assert len(events) == 1
        assert events[0]["title"] == "Team standup"
        assert events[0]["attendee_count"] == 2
        assert events[0]["is_all_day"] is False

    def test_all_day_event_detected(self):
        """All-day events (with 'date' key) are flagged correctly."""
        from agents.aria.calendar_manager import AriaCalendarManager

        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Holiday",
                    "start": {"date": "2026-03-31"},
                    "end": {"date": "2026-04-01"},
                }
            ]
        }

        with patch("agents.aria.calendar_manager.is_authorized", return_value=True):
            with patch("agents.aria.calendar_manager.get_calendar_service", return_value=mock_service):
                mgr = AriaCalendarManager()
                events = mgr.get_todays_events()

        assert events[0]["is_all_day"] is True
        assert events[0]["start_time"] == "All day"

    def test_fmt_formats_time_correctly(self):
        """_fmt() converts ISO datetime to short human-readable time."""
        from agents.aria.calendar_manager import _fmt
        result = _fmt("2026-03-31T09:30:00+00:00", is_all_day=False)
        assert "9:30" in result
        assert "AM" in result


# ─── Briefing Engine with Google data ─────────────────────────────────────────


class TestBriefingWithGoogle:
    def test_compose_briefing_includes_calendar(self):
        """Calendar events appear in the briefing when provided."""
        from agents.aria.briefing_engine import AriaBriefingEngine
        engine = AriaBriefingEngine()
        events = [{"title": "Board meeting", "start_time": "9:00 AM", "attendee_count": 4, "end_time": "10:00 AM", "is_all_day": False, "location": ""}]
        text = engine.compose_briefing(
            tasks=[], trading={"trade_count": 0, "pnl": 0.0, "status": "no trades"},
            leads={"hot": 0, "warm": 0}, cost=0.0,
            calendar_events=events,
        )
        assert "Board meeting" in text
        assert "9:00 AM" in text

    def test_compose_briefing_includes_emails(self):
        """Unread emails appear in the briefing when provided."""
        from agents.aria.briefing_engine import AriaBriefingEngine
        engine = AriaBriefingEngine()
        emails = [{"from_name": "Alice", "from_email": "alice@ex.com", "subject": "Urgent deal", "snippet": ""}]
        text = engine.compose_briefing(
            tasks=[], trading={"trade_count": 0, "pnl": 0.0, "status": "no trades"},
            leads={"hot": 0, "warm": 0}, cost=0.0,
            emails=emails,
        )
        assert "Alice" in text
        assert "Urgent deal" in text

    def test_compose_briefing_backward_compatible(self):
        """compose_briefing() still works with only 4 original args (no Google args)."""
        from agents.aria.briefing_engine import AriaBriefingEngine
        engine = AriaBriefingEngine()
        text = engine.compose_briefing(
            tasks=[],
            trading={"trade_count": 0, "pnl": 0.0, "status": "no trades"},
            leads={"hot": 0, "warm": 0},
            cost=1.25,
        )
        assert "Good morning" in text
        assert "$1.25" in text


# ─── OAuth API routes ──────────────────────────────────────────────────────────


class TestAriaGoogleRoutes:
    def test_status_returns_not_authorized(self):
        """GET /aria/google/status returns authorized=False when no token file."""
        import integrations.google_client as gc
        with patch.object(gc, "is_authorized", return_value=False):
            r = client.get("/aria/google/status")
        assert r.status_code == 200
        assert r.json()["authorized"] is False

    def test_status_returns_authorized(self):
        """GET /aria/google/status returns authorized=True when token exists."""
        import integrations.google_client as gc
        with patch.object(gc, "is_authorized", return_value=True):
            r = client.get("/aria/google/status")
        assert r.status_code == 200
        assert r.json()["authorized"] is True

    def test_authorize_returns_auth_url(self):
        """GET /aria/google/authorize returns a Google auth URL."""
        import integrations.google_client as gc
        with patch.object(gc, "get_auth_url", return_value="https://accounts.google.com/o/oauth2/auth?client_id=test"):
            r = client.get("/aria/google/authorize")
        assert r.status_code == 200
        assert "auth_url" in r.json()
        assert "accounts.google.com" in r.json()["auth_url"]

    def test_connect_accepts_valid_code(self):
        """POST /aria/google/connect exchanges a valid code and returns connected status."""
        import integrations.google_client as gc
        with patch.object(gc, "exchange_code", return_value={"success": True, "email": "owner@gmail.com"}):
            r = client.post("/aria/google/connect", json={"code": "4/abc123"})
        assert r.status_code == 200
        assert r.json()["status"] == "connected"
        assert r.json()["email"] == "owner@gmail.com"

    def test_connect_rejects_empty_code(self):
        """POST /aria/google/connect returns 400 for empty code."""
        r = client.post("/aria/google/connect", json={"code": "   "})
        assert r.status_code == 400

    def test_connect_returns_400_on_exchange_failure(self):
        """POST /aria/google/connect returns 400 when Google rejects the code."""
        import integrations.google_client as gc
        with patch.object(gc, "exchange_code", return_value={"success": False, "error": "invalid_grant"}):
            r = client.post("/aria/google/connect", json={"code": "expired-code"})
        assert r.status_code == 400

    def test_disconnect_returns_not_connected_when_no_token(self):
        """DELETE /aria/google/disconnect returns not_connected when no token file."""
        import integrations.google_client as gc
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch.object(gc, "TOKEN_PATH", mock_path):
            r = client.delete("/aria/google/disconnect")
        assert r.status_code == 200
        assert r.json()["status"] == "not_connected"

    def test_disconnect_removes_token_when_present(self):
        """DELETE /aria/google/disconnect deletes token file when it exists."""
        import integrations.google_client as gc
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        with patch.object(gc, "TOKEN_PATH", mock_path):
            r = client.delete("/aria/google/disconnect")
        assert r.status_code == 200
        assert r.json()["status"] == "disconnected"
        mock_path.unlink.assert_called_once()
