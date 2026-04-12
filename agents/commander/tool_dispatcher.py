"""Commander Tool Dispatcher — Autonomous multi-integration action engine.

When Commander receives a request, it:
1. Identifies what tools/integrations are needed
2. Checks permissions via PermissionGuard
3. Checks rate limits via RateLimiter
4. Executes the action using the appropriate client
5. Logs the result to the activity log
6. Returns a structured result for the AI to incorporate in its response

This is what makes the platform truly autonomous — Commander can ACT, not just talk.

Supported tool actions:
- slack_send        → Send a Slack message
- slack_alert       → Send a formatted Slack alert
- calendar_list     → List upcoming calendar events
- calendar_create   → Create a calendar event
- calendar_cancel   → Cancel an event
- calendar_check    → Check availability
- email_send        → Send an email (via Resend)
- sms_send          → Send an SMS (via Twilio)
- notion_create     → Create a Notion page
- notion_log        → Append log entry to a Notion page
- notion_search     → Search Notion workspace
- hubspot_contact   → Create/find a HubSpot contact
- hubspot_deal      → Create a HubSpot deal
- hubspot_note      → Log a note on a contact
- fub_contact       → Create a Follow Up Boss contact
- fub_note          → Add a Follow Up Boss note
- fub_search        → Search Follow Up Boss contacts
- github_issue      → Create a GitHub issue
- github_comment    → Comment on an issue
- github_commits    → Get recent commits
- voice_speak       → Text-to-speech via ElevenLabs
- web_search        → Search the web
- rate_status       → Get current rate limit status
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from integrations.permission_guard import Permission, PermissionGuard, PermissionDeniedError
from integrations.rate_limiter import get_rate_limiter, RateLimitExceededError

logger = logging.getLogger("orb.commander.tool_dispatcher")


class ToolResult:
    """Result of a tool execution."""

    def __init__(
        self,
        tool: str,
        success: bool,
        data: Any = None,
        error: str | None = None,
        needs_approval: bool = False,
    ) -> None:
        self.tool = tool
        self.success = success
        self.data = data
        self.error = error
        self.needs_approval = needs_approval
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "needs_approval": self.needs_approval,
            "timestamp": self.timestamp,
        }

    def to_context_string(self) -> str:
        """Format result for injection into Commander's AI prompt."""
        if self.needs_approval:
            return f"[{self.tool}] ⚠️ Requires owner approval before executing."
        if not self.success:
            return f"[{self.tool}] ❌ Failed: {self.error}"
        if isinstance(self.data, list):
            lines = [f"[{self.tool}] ✅ Result ({len(self.data)} items):"]
            for item in self.data[:10]:  # Limit to 10 for context window
                lines.append(f"  - {item}")
            return "\n".join(lines)
        return f"[{self.tool}] ✅ {self.data}"


class ToolDispatcher:
    """Executes tool actions on behalf of Commander with full security enforcement.

    Usage:
        dispatcher = ToolDispatcher(owner_id="...", plan="professional")
        result = dispatcher.execute("slack_send", {"channel": "#general", "text": "Hello"})
    """

    def __init__(self, owner_id: str, plan: str = "starter") -> None:
        self.owner_id = owner_id
        self.plan = plan
        self._guard = PermissionGuard(owner_id=owner_id, agent_slug="commander")
        self._limiter = get_rate_limiter()

    def execute(self, tool: str, params: dict[str, Any]) -> ToolResult:
        """Execute a tool action with security enforcement.

        Args:
            tool: Tool identifier string.
            params: Tool-specific parameters.

        Returns: ToolResult with success/failure, data, and context string.
        """
        # Check agent-level API rate limit first
        allowed, reason = self._limiter.check_agent_api_call("commander", self.owner_id)
        if not allowed:
            return ToolResult(tool=tool, success=False, error=f"Rate limited: {reason}")

        try:
            result = self._dispatch(tool, params)
            # Record the call if successful
            if result.success:
                self._limiter.record_agent_api_call("commander", self.owner_id)
                self._log_action(tool, params, result)
            return result
        except PermissionDeniedError as e:
            logger.warning("Permission denied for tool '%s': %s", tool, e)
            return ToolResult(tool=tool, success=False, error=str(e))
        except RateLimitExceededError as e:
            return ToolResult(tool=tool, success=False, error=str(e))
        except Exception as e:
            logger.error("Tool '%s' execution failed: %s", tool, e)
            return ToolResult(tool=tool, success=False, error=str(e)[:300])

    def _dispatch(self, tool: str, params: dict[str, Any]) -> ToolResult:
        """Route to the correct handler."""
        handlers: dict[str, Any] = {
            # Slack
            "slack_send": self._slack_send,
            "slack_alert": self._slack_alert,
            "slack_list_channels": self._slack_list_channels,
            # Calendar
            "calendar_list": self._calendar_list,
            "calendar_create": self._calendar_create,
            "calendar_cancel": self._calendar_cancel,
            "calendar_check": self._calendar_check,
            # Email
            "email_send": self._email_send,
            # SMS
            "sms_send": self._sms_send,
            # Notion
            "notion_create": self._notion_create,
            "notion_log": self._notion_log,
            "notion_search": self._notion_search,
            # HubSpot
            "hubspot_contact": self._hubspot_contact,
            "hubspot_deal": self._hubspot_deal,
            "hubspot_note": self._hubspot_note,
            "hubspot_search": self._hubspot_search,
            # Follow Up Boss
            "fub_contact": self._fub_contact,
            "fub_note": self._fub_note,
            "fub_search": self._fub_search,
            # GitHub
            "github_issue": self._github_issue,
            "github_comment": self._github_comment,
            "github_commits": self._github_commits,
            # Voice
            "voice_speak": self._voice_speak,
            # Utility
            "rate_status": self._rate_status,
        }

        handler = handlers.get(tool)
        if not handler:
            return ToolResult(tool=tool, success=False, error=f"Unknown tool: '{tool}'")

        return handler(params)

    # ---------------------------------------------------------------------------
    # Slack handlers
    # ---------------------------------------------------------------------------

    def _slack_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SLACK, "slack_send")
        allowed, reason = self._limiter.check_communication("slack", self.owner_id, self.plan)
        if not allowed:
            return ToolResult("slack_send", False, error=reason)

        from integrations.slack_client import send_message, is_slack_available
        if not is_slack_available():
            return ToolResult("slack_send", False, error="Slack not configured. Add SLACK_BOT_TOKEN.")

        send_message(channel=p["channel"], text=p["text"])
        self._limiter.record_communication("slack", self.owner_id)
        return ToolResult("slack_send", True, data=f"Message sent to {p['channel']}")

    def _slack_alert(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SLACK, "slack_alert")
        from integrations.slack_client import send_alert, is_slack_available
        if not is_slack_available():
            return ToolResult("slack_alert", False, error="Slack not configured.")

        send_alert(
            channel=p.get("channel", "#general"),
            title=p.get("title", "Alert"),
            body=p.get("body", ""),
            level=p.get("level", "info"),
        )
        return ToolResult("slack_alert", True, data=f"Alert sent to {p.get('channel')}")

    def _slack_list_channels(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SLACK)
        from integrations.slack_client import list_channels, is_slack_available
        if not is_slack_available():
            return ToolResult("slack_list_channels", False, error="Slack not configured.")
        channels = list_channels()
        return ToolResult("slack_list_channels", True, data=[f"#{c['name']}" for c in channels])

    # ---------------------------------------------------------------------------
    # Google Calendar handlers
    # ---------------------------------------------------------------------------

    def _calendar_list(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CALENDAR, "calendar_list")
        from integrations.gcal_client import list_upcoming_events, is_gcal_available
        if not is_gcal_available():
            return ToolResult("calendar_list", False, error="Google Calendar not configured.")

        events = list_upcoming_events(days=p.get("days", 7), max_results=p.get("limit", 10))
        formatted = [
            f"{e['summary']} @ {e['start'][:16].replace('T', ' ')}"
            + (f" with {', '.join(e['attendees'][:2])}" if e.get("attendees") else "")
            for e in events
        ]
        return ToolResult("calendar_list", True, data=formatted)

    def _calendar_create(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_CALENDAR_EVENT, "calendar_create")
        from integrations.gcal_client import create_event, is_gcal_available
        if not is_gcal_available():
            return ToolResult("calendar_create", False, error="Google Calendar not configured.")

        from datetime import datetime as dt
        start = dt.fromisoformat(p["start"])
        end = dt.fromisoformat(p.get("end", p["start"]))

        event = create_event(
            summary=p["title"],
            start_datetime=start,
            end_datetime=end,
            description=p.get("description", ""),
            location=p.get("location", ""),
            attendees=p.get("attendees"),
            add_google_meet=p.get("google_meet", False),
        )
        return ToolResult(
            "calendar_create",
            True,
            data=f"Event '{p['title']}' created. Link: {event.get('html_link', 'N/A')}",
        )

    def _calendar_cancel(self, p: dict) -> ToolResult:
        if self._guard.requires_approval(Permission.CANCEL_CALENDAR_EVENT):
            return ToolResult("calendar_cancel", False, needs_approval=True,
                              error="Cancelling events requires owner approval.")

        from integrations.gcal_client import cancel_event, is_gcal_available
        if not is_gcal_available():
            return ToolResult("calendar_cancel", False, error="Google Calendar not configured.")

        ok = cancel_event(event_id=p["event_id"])
        return ToolResult("calendar_cancel", ok, data="Event cancelled." if ok else None,
                          error=None if ok else "Failed to cancel event.")

    def _calendar_check(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CALENDAR, "calendar_check")
        from integrations.gcal_client import check_availability, is_gcal_available
        if not is_gcal_available():
            return ToolResult("calendar_check", False, error="Google Calendar not configured.")

        from datetime import datetime as dt
        start = dt.fromisoformat(p["start"])
        end = dt.fromisoformat(p["end"])
        busy = check_availability(emails=p["emails"], start_datetime=start, end_datetime=end)
        lines = []
        for email, slots in busy.items():
            if slots:
                lines.append(f"{email}: BUSY during {len(slots)} slot(s)")
            else:
                lines.append(f"{email}: FREE")
        return ToolResult("calendar_check", True, data=lines)

    # ---------------------------------------------------------------------------
    # Email handler
    # ---------------------------------------------------------------------------

    def _email_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "email_send")
        allowed, reason = self._limiter.check_communication("email", self.owner_id, self.plan)
        if not allowed:
            return ToolResult("email_send", False, error=reason)

        try:
            from integrations.resend_client import send_email
            send_email(
                to=p["to"],
                subject=p["subject"],
                html=p.get("html", p.get("body", "")),
            )
            self._limiter.record_communication("email", self.owner_id)
            return ToolResult("email_send", True, data=f"Email sent to {p['to']}")
        except ImportError:
            return ToolResult("email_send", False, error="Resend client not available.")
        except Exception as e:
            return ToolResult("email_send", False, error=str(e))

    # ---------------------------------------------------------------------------
    # SMS handler
    # ---------------------------------------------------------------------------

    def _sms_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SMS, "sms_send")
        allowed, reason = self._limiter.check_communication("sms", self.owner_id, self.plan)
        if not allowed:
            return ToolResult("sms_send", False, error=reason)

        try:
            from integrations.twilio_client import send_sms
            send_sms(to=p["to"], body=p["message"])
            self._limiter.record_communication("sms", self.owner_id)
            return ToolResult("sms_send", True, data=f"SMS sent to {p['to']}")
        except ImportError:
            return ToolResult("sms_send", False, error="Twilio client not available.")
        except Exception as e:
            return ToolResult("sms_send", False, error=str(e))

    # ---------------------------------------------------------------------------
    # Notion handlers
    # ---------------------------------------------------------------------------

    def _notion_create(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_NOTION_PAGE, "notion_create")
        from integrations.notion_client import create_page, is_notion_available
        if not is_notion_available():
            return ToolResult("notion_create", False, error="Notion not configured. Add NOTION_API_KEY.")

        page = create_page(
            database_id=p["database_id"],
            title=p["title"],
            content_blocks=[{"object": "block", "type": "paragraph",
                             "paragraph": {"rich_text": [{"type": "text", "text": {"content": p.get("content", "")}}]}}]
            if p.get("content") else None,
        )
        return ToolResult("notion_create", True, data=f"Page '{p['title']}' created: {page.get('url')}")

    def _notion_log(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_NOTION_PAGE, "notion_log")
        from integrations.notion_client import log_event, is_notion_available
        if not is_notion_available():
            return ToolResult("notion_log", False, error="Notion not configured.")

        ok = log_event(page_id=p["page_id"], event=p["event"], details=p.get("details", ""))
        return ToolResult("notion_log", ok, data="Log entry appended." if ok else None)

    def _notion_search(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_FILES, "notion_search")
        from integrations.notion_client import search, is_notion_available
        if not is_notion_available():
            return ToolResult("notion_search", False, error="Notion not configured.")

        results = search(query=p["query"])
        return ToolResult("notion_search", True,
                          data=[f"{r['title']} — {r['url']}" for r in results[:5]])

    # ---------------------------------------------------------------------------
    # HubSpot handlers
    # ---------------------------------------------------------------------------

    def _hubspot_contact(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_CONTACT, "hubspot_contact")
        from integrations.hubspot_client import create_contact, get_contact_by_email, is_hubspot_available
        if not is_hubspot_available():
            return ToolResult("hubspot_contact", False, error="HubSpot not configured. Add HUBSPOT_API_KEY.")

        # Check if contact already exists
        existing = get_contact_by_email(p["email"])
        if existing:
            return ToolResult("hubspot_contact", True,
                              data=f"Contact found: {existing['email']} (ID: {existing['id']})")

        contact = create_contact(
            email=p["email"],
            firstname=p.get("firstname", ""),
            lastname=p.get("lastname", ""),
            company=p.get("company", ""),
            phone=p.get("phone", ""),
            lifecycle_stage=p.get("stage", "lead"),
        )
        return ToolResult("hubspot_contact", True,
                          data=f"Contact created: {contact['email']} — {contact['url']}")

    def _hubspot_deal(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_DEAL, "hubspot_deal")
        from integrations.hubspot_client import create_deal, is_hubspot_available
        if not is_hubspot_available():
            return ToolResult("hubspot_deal", False, error="HubSpot not configured.")

        deal = create_deal(
            deal_name=p["name"],
            amount=p.get("amount", 0),
            deal_stage=p.get("stage", "appointmentscheduled"),
            contact_ids=p.get("contact_ids"),
        )
        return ToolResult("hubspot_deal", True,
                          data=f"Deal '{p['name']}' created — {deal['url']}")

    def _hubspot_note(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_CONTACT, "hubspot_note")
        from integrations.hubspot_client import log_note, is_hubspot_available
        if not is_hubspot_available():
            return ToolResult("hubspot_note", False, error="HubSpot not configured.")

        log_note(contact_id=p["contact_id"], note_body=p["note"])
        return ToolResult("hubspot_note", True, data="Note logged to contact.")

    def _hubspot_search(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "hubspot_search")
        from integrations.hubspot_client import search_contacts, is_hubspot_available
        if not is_hubspot_available():
            return ToolResult("hubspot_search", False, error="HubSpot not configured.")

        contacts = search_contacts(query=p["query"])
        return ToolResult("hubspot_search", True,
                          data=[f"{c['firstname']} {c['lastname']} <{c['email']}>" for c in contacts])

    # ---------------------------------------------------------------------------
    # Follow Up Boss handlers
    # ---------------------------------------------------------------------------

    def _fub_contact(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_CONTACT, "fub_contact")
        from integrations.followupboss_client import create_person, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_contact", False, error="Follow Up Boss not configured. Add FOLLOWUPBOSS_API_KEY.")

        person = create_person(
            first_name=p["first_name"],
            last_name=p.get("last_name", ""),
            email=p["email"],
            phone=p.get("phone"),
        )
        return ToolResult("fub_contact", True, data=f"FUB contact created: {person['name']} ({person['email']})")

    def _fub_note(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_CONTACT, "fub_note")
        from integrations.followupboss_client import add_note, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_note", False, error="Follow Up Boss not configured.")

        note = add_note(person_id=p["person_id"], body=p["note"])
        return ToolResult("fub_note", True, data=f"FUB note added (id: {note.get('id')})")

    def _fub_search(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "fub_search")
        from integrations.followupboss_client import search_people, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_search", False, error="Follow Up Boss not configured.")

        people = search_people(query=p["query"], limit=p.get("limit", 10))
        return ToolResult(
            "fub_search",
            True,
            data=[f"{x['name']} <{x['email']}>" for x in people],
        )

    # ---------------------------------------------------------------------------
    # GitHub handlers
    # ---------------------------------------------------------------------------

    def _github_issue(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_GITHUB_ISSUE, "github_issue")
        from integrations.github_client import create_issue, is_github_available
        if not is_github_available():
            return ToolResult("github_issue", False, error="GitHub not configured. Add GITHUB_TOKEN.")

        owner_repo = p.get("repo", "").split("/")
        if len(owner_repo) != 2:
            return ToolResult("github_issue", False, error="Invalid repo format. Use 'owner/repo'.")

        issue = create_issue(
            owner=owner_repo[0],
            repo=owner_repo[1],
            title=p["title"],
            body=p.get("body", ""),
            labels=p.get("labels"),
        )
        return ToolResult("github_issue", True,
                          data=f"Issue #{issue['number']} created: {issue['url']}")

    def _github_comment(self, p: dict) -> ToolResult:
        self._guard.require(Permission.COMMENT_GITHUB, "github_comment")
        from integrations.github_client import comment_on_issue, is_github_available
        if not is_github_available():
            return ToolResult("github_comment", False, error="GitHub not configured.")

        owner_repo = p.get("repo", "").split("/")
        result = comment_on_issue(
            owner=owner_repo[0],
            repo=owner_repo[1],
            issue_number=p["issue_number"],
            comment=p["comment"],
        )
        return ToolResult("github_comment", True, data=f"Comment posted: {result.get('url')}")

    def _github_commits(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_GITHUB, "github_commits")
        from integrations.github_client import get_recent_commits, is_github_available
        if not is_github_available():
            return ToolResult("github_commits", False, error="GitHub not configured.")

        owner_repo = p.get("repo", "").split("/")
        commits = get_recent_commits(
            owner=owner_repo[0],
            repo=owner_repo[1],
            limit=p.get("limit", 5),
        )
        return ToolResult("github_commits", True,
                          data=[f"{c['sha']} — {c['message']}" for c in commits])

    # ---------------------------------------------------------------------------
    # Voice handler
    # ---------------------------------------------------------------------------

    def _voice_speak(self, p: dict) -> ToolResult:
        self._guard.require(Permission.USE_VOICE_SYNTHESIS, "voice_speak")
        from integrations.elevenlabs_client import text_to_speech_file, is_elevenlabs_available
        if not is_elevenlabs_available():
            return ToolResult("voice_speak", False, error="ElevenLabs not configured. Add ELEVENLABS_API_KEY.")

        path = p.get("output_path", "/tmp/orb_voice.mp3")
        text_to_speech_file(text=p["text"], output_path=path)
        return ToolResult("voice_speak", True, data=f"Audio saved to {path}")

    # ---------------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------------

    def _rate_status(self, p: dict) -> ToolResult:
        status = self._limiter.get_status(self.owner_id, self.plan)
        lines = [
            f"AI calls today: {status['ai_calls_today']}/{status['ai_calls_per_day_limit']}",
            f"AI calls this hour: {status['ai_calls_this_hour']}/{status['ai_calls_per_hour_limit']}",
            f"Daily AI cost: ${status['ai_cost_today_cents'] / 100:.2f} / ${status['ai_daily_cost_limit_cents'] / 100:.2f}",
            f"Emails today: {status['email_today']} | SMS today: {status['sms_today']}",
        ]
        return ToolResult("rate_status", True, data=lines)

    def _log_action(self, tool: str, params: dict, result: ToolResult) -> None:
        """Log tool execution to the activity log (non-fatal)."""
        try:
            from app.database.connection import SupabaseService
            db = SupabaseService()
            db.log_activity(
                agent_id="commander",
                owner_id=self.owner_id,
                action_type=f"tool:{tool}",
                description=f"Commander used '{tool}'",
                metadata={
                    "tool": tool,
                    "success": result.success,
                    "params_summary": {k: str(v)[:50] for k, v in params.items()},
                },
            )
        except Exception as e:
            logger.debug("Could not log tool action: %s", e)
