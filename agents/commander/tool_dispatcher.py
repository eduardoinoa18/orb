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
- dashboard_list    → Show the owner's current dashboard tabs and widgets
- dashboard_add_tab → Add a new tab to the owner's dashboard
- dashboard_remove_tab → Remove a tab (protected: overview, commander)
- dashboard_add_widget → Add a widget to a specific tab
- dashboard_remove_widget → Remove a widget from a tab
- dashboard_change_theme → Change accent color, card style, density, etc.
- dashboard_reorder_tabs → Re-order tabs by name
- instagram_send     → Send a DM to an Instagram user
- instagram_reply    → Reply to an Instagram comment
- instagram_post     → Publish a photo post to Instagram
- messenger_send     → Send a Facebook Messenger message
- messenger_buttons  → Send a Messenger message with quick-reply buttons
- teams_message      → Post a message to Microsoft Teams channel
- teams_alert        → Post a color-coded alert card to Teams
- airtable_read      → Read records from an Airtable table
- airtable_create    → Create a record in Airtable
- airtable_update    → Update an existing Airtable record
- airtable_search    → Search Airtable records by field value
- zapier_trigger     → Fire a Zapier webhook to trigger any Zap
- zapier_new_lead    → Zapier: fire 'new_lead' event
- zapier_deal_closed → Zapier: fire 'deal_closed' event
- calendly_list      → List upcoming Calendly meetings
- calendly_link      → Create a scheduling link to send to a lead
- calendly_cancel    → Cancel a Calendly event
- mailchimp_add      → Add / update a subscriber in Mailchimp
- mailchimp_tag      → Tag a Mailchimp subscriber for segmentation
- mailchimp_unsubscribe → Unsubscribe a contact from Mailchimp
- pipedrive_contact  → Create or search a Pipedrive person
- pipedrive_deal     → Create a Pipedrive deal
- pipedrive_note     → Add a note to a Pipedrive deal/person
- pipedrive_stage    → Move a Pipedrive deal to a different stage
- monday_item        → Create an item on a Monday.com board
- monday_update      → Post an update/comment on a Monday item
- monday_move        → Move a Monday item to a different group
- openphone_sms      → Send an SMS via OpenPhone
- openphone_call     → Initiate an outbound call via OpenPhone
- openphone_history  → Get call/message history from OpenPhone
- docusign_send      → Send a document for eSignature via DocuSign
- docusign_status    → Check signing status of a DocuSign envelope
- docusign_void      → Void / cancel a DocuSign envelope
- linkedin_post      → Post content to LinkedIn
- linkedin_post_link → Post a LinkedIn update with a link card
- twitter_post       → Post a tweet
- twitter_search     → Search recent tweets
- shopify_orders     → Get Shopify orders
- shopify_customer   → Search Shopify customers
- shopify_discount   → Create a Shopify discount code
- typeform_responses → Get form responses as structured leads
- typeform_forms     → List Typeform forms
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
            # Follow Up Boss CRM
            "fub_search": self._fub_search,
            "fub_contact": self._fub_contact,
            "fub_note": self._fub_note,
            "fub_deal": self._fub_deal,
            "fub_task": self._fub_task,
            "fub_stage": self._fub_stage,
            "fub_call": self._fub_call,
            "fub_smart_lists": self._fub_smart_lists,
            "fub_tasks_pending": self._fub_tasks_pending,
            # GitHub
            "github_issue": self._github_issue,
            "github_comment": self._github_comment,
            "github_commits": self._github_commits,
            # Voice
            "voice_speak": self._voice_speak,
            # Instagram
            "instagram_send": self._instagram_send,
            "instagram_reply": self._instagram_reply,
            "instagram_post": self._instagram_post,
            # Facebook Messenger
            "messenger_send": self._messenger_send,
            "messenger_buttons": self._messenger_buttons,
            # Microsoft Teams
            "teams_message": self._teams_message,
            "teams_alert": self._teams_alert,
            # Airtable
            "airtable_read": self._airtable_read,
            "airtable_create": self._airtable_create,
            "airtable_update": self._airtable_update,
            "airtable_search": self._airtable_search,
            # Zapier
            "zapier_trigger": self._zapier_trigger,
            "zapier_new_lead": self._zapier_new_lead,
            "zapier_deal_closed": self._zapier_deal_closed,
            # Calendly
            "calendly_list": self._calendly_list,
            "calendly_link": self._calendly_link,
            "calendly_cancel": self._calendly_cancel,
            # Mailchimp
            "mailchimp_add": self._mailchimp_add,
            "mailchimp_tag": self._mailchimp_tag,
            "mailchimp_unsubscribe": self._mailchimp_unsubscribe,
            # Pipedrive
            "pipedrive_contact": self._pipedrive_contact,
            "pipedrive_deal": self._pipedrive_deal,
            "pipedrive_note": self._pipedrive_note,
            "pipedrive_stage": self._pipedrive_stage,
            # Monday.com
            "monday_item": self._monday_item,
            "monday_update": self._monday_update,
            "monday_move": self._monday_move,
            # OpenPhone
            "openphone_sms": self._openphone_sms,
            "openphone_call": self._openphone_call,
            "openphone_history": self._openphone_history,
            # DocuSign
            "docusign_send": self._docusign_send,
            "docusign_status": self._docusign_status,
            "docusign_void": self._docusign_void,
            # LinkedIn
            "linkedin_post": self._linkedin_post,
            "linkedin_post_link": self._linkedin_post_link,
            # Twitter / X
            "twitter_post": self._twitter_post,
            "twitter_search": self._twitter_search,
            # Shopify
            "shopify_orders": self._shopify_orders,
            "shopify_customer": self._shopify_customer,
            "shopify_discount": self._shopify_discount,
            # Typeform
            "typeform_responses": self._typeform_responses,
            "typeform_forms": self._typeform_forms,
            # Dashboard customization
            "dashboard_list": self._dashboard_list,
            "dashboard_add_tab": self._dashboard_add_tab,
            "dashboard_remove_tab": self._dashboard_remove_tab,
            "dashboard_add_widget": self._dashboard_add_widget,
            "dashboard_remove_widget": self._dashboard_remove_widget,
            "dashboard_change_theme": self._dashboard_change_theme,
            "dashboard_reorder_tabs": self._dashboard_reorder_tabs,
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
            data=[
                f"{x['name']} | {', '.join(x.get('emails', [])[:1])} | Stage: {x.get('stage', 'N/A')} | Tags: {', '.join(x.get('tags', [])[:3])}"
                for x in people
            ],
        )

    def _fub_deal(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_DEAL, "fub_deal")
        from integrations.followupboss_client import create_deal, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_deal", False, error="Follow Up Boss not configured.")

        deal = create_deal(
            person_id=p["person_id"],
            name=p["name"],
            price=p.get("price", 0),
            stage=p.get("stage", "Pre-Approval"),
            deal_type=p.get("deal_type", "Buyer"),
            property_address=p.get("address", ""),
        )
        return ToolResult("fub_deal", True,
                          data=f"FUB deal '{p['name']}' created (ID: {deal.get('id')})")

    def _fub_task(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_CONTACT, "fub_task")
        from integrations.followupboss_client import create_task, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_task", False, error="Follow Up Boss not configured.")

        task = create_task(
            person_id=p["person_id"],
            name=p["name"],
            due_date=p["due_date"],
            description=p.get("description", ""),
            assigned_to=p.get("assigned_to"),
        )
        return ToolResult("fub_task", True,
                          data=f"FUB task '{p['name']}' created, due {p['due_date']}")

    def _fub_stage(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_CONTACT, "fub_stage")
        from integrations.followupboss_client import change_stage, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_stage", False, error="Follow Up Boss not configured.")

        ok = change_stage(person_id=p["person_id"], stage=p["stage"])
        return ToolResult("fub_stage", ok,
                          data=f"Contact {p['person_id']} moved to stage '{p['stage']}'")

    def _fub_call(self, p: dict) -> ToolResult:
        self._guard.require(Permission.MAKE_PHONE_CALL, "fub_call")
        from integrations.followupboss_client import log_call, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_call", False, error="Follow Up Boss not configured.")

        result = log_call(
            person_id=p["person_id"],
            outcome=p.get("outcome", "Connected"),
            duration_seconds=p.get("duration", 0),
            note=p.get("note", ""),
        )
        return ToolResult("fub_call", True,
                          data=f"Call logged for contact {p['person_id']} — {p.get('outcome', 'Connected')}")

    def _fub_smart_lists(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "fub_smart_lists")
        from integrations.followupboss_client import get_smart_lists, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_smart_lists", False, error="Follow Up Boss not configured.")

        lists = get_smart_lists()
        return ToolResult("fub_smart_lists", True,
                          data=[f"{sl['name']} ({sl['count']} contacts)" for sl in lists])

    def _fub_tasks_pending(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "fub_tasks_pending")
        from integrations.followupboss_client import get_tasks, is_followupboss_available
        if not is_followupboss_available():
            return ToolResult("fub_tasks_pending", False, error="Follow Up Boss not configured.")

        tasks = get_tasks(person_id=p.get("person_id"), status="pending", limit=p.get("limit", 15))
        return ToolResult("fub_tasks_pending", True,
                          data=[f"[{t['dueDate']}] {t['name']} (contact: {t['personId']})" for t in tasks])

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

    # ---------------------------------------------------------------------------
    # Instagram handlers
    # ---------------------------------------------------------------------------

    def _instagram_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "instagram_send")  # reuse comms permission
        from integrations.instagram_client import send_dm, is_instagram_available
        if not is_instagram_available():
            return ToolResult("instagram_send", False, error="Instagram not configured. Add INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_BUSINESS_ID.")
        send_dm(recipient_id=p["recipient_id"], text=p["text"])
        return ToolResult("instagram_send", True, data=f"Instagram DM sent to {p['recipient_id'][:10]}...")

    def _instagram_reply(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "instagram_reply")
        from integrations.instagram_client import reply_to_comment, is_instagram_available
        if not is_instagram_available():
            return ToolResult("instagram_reply", False, error="Instagram not configured.")
        reply_to_comment(comment_id=p["comment_id"], text=p["text"])
        return ToolResult("instagram_reply", True, data=f"Replied to comment {p['comment_id']}")

    def _instagram_post(self, p: dict) -> ToolResult:
        self._guard.require(Permission.POST_SOCIAL_MEDIA, "instagram_post")
        from integrations.instagram_client import publish_photo, is_instagram_available
        if not is_instagram_available():
            return ToolResult("instagram_post", False, error="Instagram not configured.")
        result = publish_photo(image_url=p["image_url"], caption=p.get("caption", ""))
        return ToolResult("instagram_post", True, data=f"Photo posted (ID: {result.get('id')})")

    # ---------------------------------------------------------------------------
    # Facebook Messenger handlers
    # ---------------------------------------------------------------------------

    def _messenger_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "messenger_send")
        from integrations.facebook_messenger_client import send_text, is_messenger_available
        if not is_messenger_available():
            return ToolResult("messenger_send", False, error="Facebook Messenger not configured. Add FACEBOOK_PAGE_TOKEN.")
        send_text(recipient_id=p["recipient_id"], text=p["text"])
        return ToolResult("messenger_send", True, data=f"Messenger message sent to {p['recipient_id'][:10]}...")

    def _messenger_buttons(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "messenger_buttons")
        from integrations.facebook_messenger_client import send_quick_replies, is_messenger_available
        if not is_messenger_available():
            return ToolResult("messenger_buttons", False, error="Facebook Messenger not configured.")
        send_quick_replies(
            recipient_id=p["recipient_id"],
            text=p["text"],
            options=p.get("options", []),
        )
        return ToolResult("messenger_buttons", True, data=f"Messenger message + {len(p.get('options', []))} buttons sent")

    # ---------------------------------------------------------------------------
    # Microsoft Teams handlers
    # ---------------------------------------------------------------------------

    def _teams_message(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SLACK, "teams_message")  # equivalent comms
        from integrations.teams_client import send_message, is_teams_available
        if not is_teams_available():
            return ToolResult("teams_message", False, error="Microsoft Teams not configured. Add TEAMS_WEBHOOK_URL.")
        send_message(text=p["text"], title=p.get("title"))
        return ToolResult("teams_message", True, data="Message posted to Teams channel.")

    def _teams_alert(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SLACK, "teams_alert")
        from integrations.teams_client import send_alert, is_teams_available
        if not is_teams_available():
            return ToolResult("teams_alert", False, error="Microsoft Teams not configured.")
        send_alert(
            title=p.get("title", "Alert"),
            summary=p.get("summary", ""),
            level=p.get("level", "info"),
            link_url=p.get("link_url"),
        )
        return ToolResult("teams_alert", True, data=f"Teams {p.get('level','info')} alert posted.")

    # ---------------------------------------------------------------------------
    # Airtable handlers
    # ---------------------------------------------------------------------------

    def _airtable_read(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_FILES, "airtable_read")
        from integrations.airtable_client import list_records, is_airtable_available
        if not is_airtable_available():
            return ToolResult("airtable_read", False, error="Airtable not configured. Add AIRTABLE_API_KEY + AIRTABLE_BASE_ID.")
        records = list_records(
            table=p["table"],
            view=p.get("view"),
            filter_formula=p.get("filter"),
            max_records=p.get("limit", 20),
        )
        lines = [f"[{r['id']}] {r.get('fields', {})}" for r in records[:10]]
        return ToolResult("airtable_read", True, data=lines)

    def _airtable_create(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "airtable_create")
        from integrations.airtable_client import create_record, is_airtable_available
        if not is_airtable_available():
            return ToolResult("airtable_create", False, error="Airtable not configured.")
        record = create_record(table=p["table"], fields=p["fields"])
        return ToolResult("airtable_create", True, data=f"Airtable record created (ID: {record.get('id')})")

    def _airtable_update(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "airtable_update")
        from integrations.airtable_client import update_record, is_airtable_available
        if not is_airtable_available():
            return ToolResult("airtable_update", False, error="Airtable not configured.")
        record = update_record(table=p["table"], record_id=p["record_id"], fields=p["fields"])
        return ToolResult("airtable_update", True, data=f"Airtable record {p['record_id']} updated.")

    def _airtable_search(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_FILES, "airtable_search")
        from integrations.airtable_client import search_records, is_airtable_available
        if not is_airtable_available():
            return ToolResult("airtable_search", False, error="Airtable not configured.")
        records = search_records(table=p["table"], field=p["field"], value=p["value"])
        return ToolResult("airtable_search", True,
                          data=[f"[{r['id']}] {r.get('fields', {})}" for r in records[:10]])

    # ---------------------------------------------------------------------------
    # Zapier handlers
    # ---------------------------------------------------------------------------

    def _zapier_trigger(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_WEBHOOK, "zapier_trigger")
        from integrations.zapier_client import trigger, is_zapier_available
        if not is_zapier_available():
            return ToolResult("zapier_trigger", False, error="Zapier not configured. Add ZAPIER_WEBHOOK_URL.")
        result = trigger(event=p["event"], data=p.get("data", {}), workflow=p.get("workflow"))
        return ToolResult("zapier_trigger", True, data=f"Zapier event '{p['event']}' triggered. Response: {result}")

    def _zapier_new_lead(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_WEBHOOK, "zapier_new_lead")
        from integrations.zapier_client import trigger_new_lead, is_zapier_available
        if not is_zapier_available():
            return ToolResult("zapier_new_lead", False, error="Zapier not configured.")
        result = trigger_new_lead(
            name=p.get("name", ""),
            email=p.get("email", ""),
            phone=p.get("phone", ""),
            source=p.get("source", "orb"),
            stage=p.get("stage", "New"),
            notes=p.get("notes", ""),
        )
        return ToolResult("zapier_new_lead", True, data=f"Zapier new_lead event fired for {p.get('name')}.")

    def _zapier_deal_closed(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_WEBHOOK, "zapier_deal_closed")
        from integrations.zapier_client import trigger_deal_closed, is_zapier_available
        if not is_zapier_available():
            return ToolResult("zapier_deal_closed", False, error="Zapier not configured.")
        result = trigger_deal_closed(
            contact_name=p.get("contact_name", ""),
            deal_name=p.get("deal_name", ""),
            amount=p.get("amount", 0),
            contact_email=p.get("email", ""),
            agent_name=p.get("agent", ""),
        )
        return ToolResult("zapier_deal_closed", True, data=f"Zapier deal_closed event fired: {p.get('deal_name')}.")

    # ---------------------------------------------------------------------------
    # Calendly handlers
    # ---------------------------------------------------------------------------

    def _calendly_list(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CALENDAR, "calendly_list")
        from integrations.calendly_client import list_upcoming_events, is_calendly_available
        if not is_calendly_available():
            return ToolResult("calendly_list", False, error="Calendly not configured. Add CALENDLY_API_KEY.")
        events = list_upcoming_events(count=p.get("limit", 10))
        return ToolResult("calendly_list", True, data=[
            f"{e['name']} @ {e['start_time'][:16].replace('T',' ')} ({e['invitees_count']} invitee(s))"
            for e in events
        ])

    def _calendly_link(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_CALENDAR_EVENT, "calendly_link")
        from integrations.calendly_client import create_scheduling_link, list_event_types, is_calendly_available
        if not is_calendly_available():
            return ToolResult("calendly_link", False, error="Calendly not configured.")
        # Find matching event type
        types = list_event_types()
        event_type_uri = p.get("event_type_uri")
        if not event_type_uri and types:
            # Auto-select the first active one, or match by name
            name_hint = p.get("event_type", "").lower()
            match = next((t for t in types if name_hint in t["name"].lower()), types[0])
            event_type_uri = match["uri"]
        if not event_type_uri:
            return ToolResult("calendly_link", False, error="No Calendly event types found.")
        result = create_scheduling_link(event_type_uri=event_type_uri, max_uses=p.get("max_uses", 1))
        return ToolResult("calendly_link", True, data=f"Scheduling link: {result['booking_url']}")

    def _calendly_cancel(self, p: dict) -> ToolResult:
        if self._guard.requires_approval(Permission.CANCEL_CALENDAR_EVENT):
            return ToolResult("calendly_cancel", False, needs_approval=True,
                              error="Cancelling events requires owner approval.")
        from integrations.calendly_client import cancel_event, is_calendly_available
        if not is_calendly_available():
            return ToolResult("calendly_cancel", False, error="Calendly not configured.")
        ok = cancel_event(event_uri=p["event_uri"], reason=p.get("reason", "Cancelled by ORB Platform"))
        return ToolResult("calendly_cancel", ok,
                          data="Event cancelled." if ok else None,
                          error=None if ok else "Failed to cancel Calendly event.")

    # ---------------------------------------------------------------------------
    # Mailchimp handlers
    # ---------------------------------------------------------------------------

    def _mailchimp_add(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "mailchimp_add")
        from integrations.mailchimp_client import add_subscriber, is_mailchimp_available
        if not is_mailchimp_available():
            return ToolResult("mailchimp_add", False, error="Mailchimp not configured. Add MAILCHIMP_API_KEY + MAILCHIMP_SERVER.")
        member = add_subscriber(
            email=p["email"],
            first_name=p.get("first_name", ""),
            last_name=p.get("last_name", ""),
            tags=p.get("tags"),
            list_id=p.get("list_id"),
        )
        return ToolResult("mailchimp_add", True,
                          data=f"Mailchimp: {p['email']} added (status: {member.get('status', 'subscribed')})")

    def _mailchimp_tag(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "mailchimp_tag")
        from integrations.mailchimp_client import add_tags, is_mailchimp_available
        if not is_mailchimp_available():
            return ToolResult("mailchimp_tag", False, error="Mailchimp not configured.")
        ok = add_tags(email=p["email"], tags=p["tags"], list_id=p.get("list_id"))
        return ToolResult("mailchimp_tag", ok, data=f"Tags {p['tags']} applied to {p['email']}.")

    def _mailchimp_unsubscribe(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_EMAIL, "mailchimp_unsubscribe")
        from integrations.mailchimp_client import unsubscribe, is_mailchimp_available
        if not is_mailchimp_available():
            return ToolResult("mailchimp_unsubscribe", False, error="Mailchimp not configured.")
        unsubscribe(email=p["email"], list_id=p.get("list_id"))
        return ToolResult("mailchimp_unsubscribe", True, data=f"{p['email']} unsubscribed from Mailchimp.")

    # ---------------------------------------------------------------------------
    # Pipedrive handlers
    # ---------------------------------------------------------------------------

    def _pipedrive_contact(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_CONTACT, "pipedrive_contact")
        from integrations.pipedrive_client import create_person, search_persons, is_pipedrive_available
        if not is_pipedrive_available():
            return ToolResult("pipedrive_contact", False, error="Pipedrive not configured. Add PIPEDRIVE_API_KEY.")
        if p.get("search"):
            results = search_persons(query=p["search"])
            return ToolResult("pipedrive_contact", True,
                              data=[f"{c['name']} | {c['email']} | {c['org']}" for c in results])
        person = create_person(name=p["name"], email=p.get("email", ""), phone=p.get("phone", ""))
        return ToolResult("pipedrive_contact", True, data=f"Pipedrive contact '{person.get('name')}' created (ID: {person.get('id')})")

    def _pipedrive_deal(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_DEAL, "pipedrive_deal")
        from integrations.pipedrive_client import create_deal, is_pipedrive_available
        if not is_pipedrive_available():
            return ToolResult("pipedrive_deal", False, error="Pipedrive not configured.")
        deal = create_deal(
            title=p["title"],
            person_id=p.get("person_id"),
            value=p.get("value", 0),
            stage_id=p.get("stage_id"),
        )
        return ToolResult("pipedrive_deal", True, data=f"Pipedrive deal '{p['title']}' created (ID: {deal.get('id')})")

    def _pipedrive_note(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_CONTACT, "pipedrive_note")
        from integrations.pipedrive_client import add_note, is_pipedrive_available
        if not is_pipedrive_available():
            return ToolResult("pipedrive_note", False, error="Pipedrive not configured.")
        add_note(deal_id=p.get("deal_id"), person_id=p.get("person_id"), content=p["note"])
        return ToolResult("pipedrive_note", True, data="Note added to Pipedrive.")

    def _pipedrive_stage(self, p: dict) -> ToolResult:
        self._guard.require(Permission.UPDATE_DEAL, "pipedrive_stage")
        from integrations.pipedrive_client import update_deal_stage, is_pipedrive_available
        if not is_pipedrive_available():
            return ToolResult("pipedrive_stage", False, error="Pipedrive not configured.")
        update_deal_stage(deal_id=p["deal_id"], stage_id=p["stage_id"])
        return ToolResult("pipedrive_stage", True,
                          data=f"Pipedrive deal {p['deal_id']} moved to stage {p['stage_id']}.")

    # ---------------------------------------------------------------------------
    # Monday.com handlers
    # ---------------------------------------------------------------------------

    def _monday_item(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "monday_item")
        from integrations.monday_client import create_item, is_monday_available
        if not is_monday_available():
            return ToolResult("monday_item", False, error="Monday.com not configured. Add MONDAY_API_KEY.")
        item = create_item(
            board_id=p["board_id"],
            item_name=p["name"],
            group_id=p.get("group_id"),
            column_values=p.get("columns"),
        )
        return ToolResult("monday_item", True,
                          data=f"Monday item '{p['name']}' created (ID: {item.get('id')})")

    def _monday_update(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "monday_update")
        from integrations.monday_client import post_update, is_monday_available
        if not is_monday_available():
            return ToolResult("monday_update", False, error="Monday.com not configured.")
        post_update(item_id=p["item_id"], body=p["body"])
        return ToolResult("monday_update", True, data=f"Update posted on Monday item {p['item_id']}.")

    def _monday_move(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "monday_move")
        from integrations.monday_client import move_item_to_group, is_monday_available
        if not is_monday_available():
            return ToolResult("monday_move", False, error="Monday.com not configured.")
        move_item_to_group(item_id=p["item_id"], group_id=p["group_id"])
        return ToolResult("monday_move", True,
                          data=f"Monday item {p['item_id']} moved to group {p['group_id']}.")

    # ---------------------------------------------------------------------------
    # OpenPhone handlers
    # ---------------------------------------------------------------------------

    def _openphone_sms(self, p: dict) -> ToolResult:
        self._guard.require(Permission.SEND_SMS, "openphone_sms")
        allowed, reason = self._limiter.check_communication("sms", self.owner_id, self.plan)
        if not allowed:
            return ToolResult("openphone_sms", False, error=reason)
        from integrations.openphone_client import send_sms, is_openphone_available
        if not is_openphone_available():
            return ToolResult("openphone_sms", False, error="OpenPhone not configured. Add OPENPHONE_API_KEY.")
        send_sms(to=p["to"], text=p["text"], from_number_id=p.get("from_number_id"))
        self._limiter.record_communication("sms", self.owner_id)
        return ToolResult("openphone_sms", True, data=f"OpenPhone SMS sent to {p['to']}.")

    def _openphone_call(self, p: dict) -> ToolResult:
        self._guard.require(Permission.MAKE_PHONE_CALL, "openphone_call")
        from integrations.openphone_client import initiate_call, is_openphone_available
        if not is_openphone_available():
            return ToolResult("openphone_call", False, error="OpenPhone not configured.")
        call = initiate_call(to=p["to"], from_number_id=p.get("from_number_id"))
        return ToolResult("openphone_call", True,
                          data=f"Outbound call initiated to {p['to']} (call ID: {call.get('id')})")

    def _openphone_history(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_ACTIVITY_LOG, "openphone_history")
        from integrations.openphone_client import get_calls, get_messages, is_openphone_available
        if not is_openphone_available():
            return ToolResult("openphone_history", False, error="OpenPhone not configured.")
        kind = p.get("type", "calls")
        if kind == "messages":
            records = get_messages(limit=p.get("limit", 10))
            lines = [f"[{r['direction']}] {r['text'][:60]} — {r['created_at'][:10]}" for r in records]
        else:
            records = get_calls(limit=p.get("limit", 10))
            lines = [f"[{r['direction']}] {r['duration_seconds']}s — {r['status']} — {r['created_at'][:10]}" for r in records]
        return ToolResult("openphone_history", True, data=lines)

    # ---------------------------------------------------------------------------
    # DocuSign handlers
    # ---------------------------------------------------------------------------

    def _docusign_send(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WRITE_FILES, "docusign_send")
        from integrations.docusign_client import send_envelope_from_template, is_docusign_available
        if not is_docusign_available():
            return ToolResult("docusign_send", False, error="DocuSign not configured. Add DOCUSIGN_ACCOUNT_ID + DOCUSIGN_ACCESS_TOKEN.")
        result = send_envelope_from_template(
            template_id=p["template_id"],
            signers=p["signers"],
            email_subject=p.get("subject", "Please sign this document"),
        )
        return ToolResult("docusign_send", True,
                          data=f"DocuSign envelope sent (ID: {result.get('envelope_id')}, status: {result.get('status')})")

    def _docusign_status(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_FILES, "docusign_status")
        from integrations.docusign_client import get_envelope_recipients, get_envelope, is_docusign_available
        if not is_docusign_available():
            return ToolResult("docusign_status", False, error="DocuSign not configured.")
        env = get_envelope(p["envelope_id"])
        recipients = get_envelope_recipients(p["envelope_id"])
        status_lines = [f"Envelope: {env.get('status')} | Subject: {env.get('subject', '')}"]
        for r in recipients:
            status_lines.append(f"  {r['name']} ({r['email']}): {r['status']}")
        return ToolResult("docusign_status", True, data=status_lines)

    def _docusign_void(self, p: dict) -> ToolResult:
        if self._guard.requires_approval(Permission.MODIFY_AGENT_SETTINGS):
            return ToolResult("docusign_void", False, needs_approval=True,
                              error="Voiding a signed document requires owner approval.")
        from integrations.docusign_client import void_envelope, is_docusign_available
        if not is_docusign_available():
            return ToolResult("docusign_void", False, error="DocuSign not configured.")
        ok = void_envelope(envelope_id=p["envelope_id"], reason=p.get("reason", "Voided by ORB"))
        return ToolResult("docusign_void", ok, data="Envelope voided." if ok else None,
                          error=None if ok else "Failed to void envelope.")

    # ---------------------------------------------------------------------------
    # LinkedIn handlers
    # ---------------------------------------------------------------------------

    def _linkedin_post(self, p: dict) -> ToolResult:
        self._guard.require(Permission.POST_SOCIAL_MEDIA, "linkedin_post")
        from integrations.linkedin_client import post_text, is_linkedin_available
        if not is_linkedin_available():
            return ToolResult("linkedin_post", False, error="LinkedIn not configured. Add LINKEDIN_ACCESS_TOKEN.")
        result = post_text(text=p["text"])
        return ToolResult("linkedin_post", True, data=f"LinkedIn post published (ID: {result.get('id')})")

    def _linkedin_post_link(self, p: dict) -> ToolResult:
        self._guard.require(Permission.POST_SOCIAL_MEDIA, "linkedin_post_link")
        from integrations.linkedin_client import post_with_link, is_linkedin_available
        if not is_linkedin_available():
            return ToolResult("linkedin_post_link", False, error="LinkedIn not configured.")
        result = post_with_link(
            text=p["text"], url=p["url"],
            title=p.get("title", ""), description=p.get("description", ""),
        )
        return ToolResult("linkedin_post_link", True, data=f"LinkedIn post with link published (ID: {result.get('id')})")

    # ---------------------------------------------------------------------------
    # Twitter/X handlers
    # ---------------------------------------------------------------------------

    def _twitter_post(self, p: dict) -> ToolResult:
        self._guard.require(Permission.POST_SOCIAL_MEDIA, "twitter_post")
        from integrations.twitter_client import post_tweet, is_twitter_available
        if not is_twitter_available():
            return ToolResult("twitter_post", False, error="Twitter/X not configured. Add TWITTER_API_KEY + TWITTER_ACCESS_TOKEN.")
        result = post_tweet(text=p["text"], reply_to_id=p.get("reply_to_id"))
        return ToolResult("twitter_post", True, data=f"Tweet posted (ID: {result.get('id')}): {p['text'][:60]}...")

    def _twitter_search(self, p: dict) -> ToolResult:
        self._guard.require(Permission.WEB_SEARCH, "twitter_search")
        from integrations.twitter_client import search_tweets, is_twitter_available
        if not is_twitter_available():
            return ToolResult("twitter_search", False, error="Twitter/X not configured. Add TWITTER_BEARER_TOKEN.")
        tweets = search_tweets(query=p["query"], max_results=p.get("limit", 10))
        return ToolResult("twitter_search", True,
                          data=[f"[{t['likes']}❤] {t['text'][:100]}" for t in tweets])

    # ---------------------------------------------------------------------------
    # Shopify handlers
    # ---------------------------------------------------------------------------

    def _shopify_orders(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_PAYMENTS, "shopify_orders")
        from integrations.shopify_client import list_orders, is_shopify_available
        if not is_shopify_available():
            return ToolResult("shopify_orders", False, error="Shopify not configured. Add SHOPIFY_STORE_DOMAIN + SHOPIFY_ACCESS_TOKEN.")
        orders = list_orders(
            status=p.get("status", "any"),
            limit=p.get("limit", 10),
            financial_status=p.get("financial_status"),
        )
        return ToolResult("shopify_orders", True,
                          data=[f"#{o['order_number']} {o['customer_name']} — ${o['total_price']} ({o['financial_status']})" for o in orders])

    def _shopify_customer(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "shopify_customer")
        from integrations.shopify_client import search_customers, is_shopify_available
        if not is_shopify_available():
            return ToolResult("shopify_customer", False, error="Shopify not configured.")
        customers = search_customers(query=p["query"], limit=p.get("limit", 10))
        return ToolResult("shopify_customer", True,
                          data=[f"{c['name']} | {c['email']} | {c['orders_count']} orders | ${c['total_spent']}" for c in customers])

    def _shopify_discount(self, p: dict) -> ToolResult:
        self._guard.require(Permission.CREATE_INVOICE, "shopify_discount")
        from integrations.shopify_client import create_discount_code, is_shopify_available
        if not is_shopify_available():
            return ToolResult("shopify_discount", False, error="Shopify not configured.")
        result = create_discount_code(
            code=p["code"],
            discount_type=p.get("type", "percentage"),
            value=p.get("value", 10.0),
            minimum_order_amount=p.get("min_order", 0),
            usage_limit=p.get("usage_limit"),
        )
        return ToolResult("shopify_discount", True,
                          data=f"Discount code '{p['code']}' created ({p.get('value',10)}% off)")

    # ---------------------------------------------------------------------------
    # Typeform handlers
    # ---------------------------------------------------------------------------

    def _typeform_responses(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_CONTACTS, "typeform_responses")
        from integrations.typeform_client import get_latest_responses, is_typeform_available
        if not is_typeform_available():
            return ToolResult("typeform_responses", False, error="Typeform not configured. Add TYPEFORM_API_KEY.")
        responses = get_latest_responses(form_id=p["form_id"], count=p.get("limit", 10))
        lines = []
        for r in responses:
            ans_preview = ", ".join(f"{k}: {v}" for k, v in list(r.get("answers", {}).items())[:3])
            lines.append(f"[{r['submitted_at'][:10]}] {ans_preview}")
        return ToolResult("typeform_responses", True, data=lines)

    def _typeform_forms(self, p: dict) -> ToolResult:
        self._guard.require(Permission.READ_FILES, "typeform_forms")
        from integrations.typeform_client import list_forms, is_typeform_available
        if not is_typeform_available():
            return ToolResult("typeform_forms", False, error="Typeform not configured.")
        forms = list_forms(page_size=p.get("limit", 20))
        return ToolResult("typeform_forms", True,
                          data=[f"[{f['id']}] {f['title']}" for f in forms])

    # ---------------------------------------------------------------------------
    # Dashboard customization handlers
    # — Commander can reshape any owner's dashboard via conversation.
    # ---------------------------------------------------------------------------

    def _dashboard_list(self, p: dict) -> ToolResult:
        """Read the owner's current dashboard layout."""
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_list")
        from app.api.routes.dashboard_config import _load_config
        config = _load_config(self.owner_id)
        lines = [f"Dashboard has {len(config.tabs)} tab(s):"]
        for tab in sorted(config.tabs, key=lambda t: t.position):
            vis = "👁" if tab.visible else "🙈"
            lines.append(
                f"  {vis} [{tab.id}] '{tab.label}' — {len(tab.widgets)} widget(s)"
            )
        lines.append(
            f"Theme: {config.theme.accent_color} | {config.theme.card_style} cards | "
            f"{config.theme.density} density | Commander: {config.commander_position}"
        )
        return ToolResult("dashboard_list", True, data=lines)

    def _dashboard_add_tab(self, p: dict) -> ToolResult:
        """Add a new tab to the owner's dashboard.

        Params: label (str), icon (str, optional, default 'layout')
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_add_tab")
        from app.api.routes.dashboard_config import _load_config, _save_config, TabConfig

        config = _load_config(self.owner_id)
        label = p.get("label", "").strip()
        if not label:
            return ToolResult("dashboard_add_tab", False, error="'label' is required.")

        # Build unique slug ID from label
        tab_id = label.lower().replace(" ", "_").replace("-", "_")
        existing_ids = {t.id for t in config.tabs}
        if tab_id in existing_ids:
            tab_id = f"{tab_id}_{len(config.tabs)}"

        new_tab = TabConfig(
            id=tab_id,
            label=label,
            icon=p.get("icon", "layout"),
            position=len(config.tabs),
        )
        config.tabs.append(new_tab)
        _save_config(self.owner_id, config)
        return ToolResult(
            "dashboard_add_tab", True,
            data=f"Tab '{label}' (id: {tab_id}) added. Dashboard now has {len(config.tabs)} tabs."
        )

    def _dashboard_remove_tab(self, p: dict) -> ToolResult:
        """Remove a tab from the owner's dashboard.

        Params: tab_id (str)
        Protected tabs: 'overview', 'commander'
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_remove_tab")
        from app.api.routes.dashboard_config import _load_config, _save_config

        tab_id = p.get("tab_id", "").strip()
        if not tab_id:
            return ToolResult("dashboard_remove_tab", False, error="'tab_id' is required.")

        protected = {"overview", "commander"}
        if tab_id in protected:
            return ToolResult(
                "dashboard_remove_tab", False,
                error=f"The '{tab_id}' tab is protected and cannot be removed."
            )

        config = _load_config(self.owner_id)
        before = len(config.tabs)
        config.tabs = [t for t in config.tabs if t.id != tab_id]
        if len(config.tabs) == before:
            return ToolResult("dashboard_remove_tab", False,
                              error=f"Tab '{tab_id}' not found. Available: {[t.id for t in config.tabs]}")

        for i, tab in enumerate(config.tabs):
            tab.position = i
        _save_config(self.owner_id, config)
        return ToolResult(
            "dashboard_remove_tab", True,
            data=f"Tab '{tab_id}' removed. Dashboard now has {len(config.tabs)} tabs."
        )

    def _dashboard_add_widget(self, p: dict) -> ToolResult:
        """Add a widget to a specific tab.

        Params:
          tab_id (str)         — which tab to add to
          widget_type (str)    — stat | activity | chat | agents | calendar | crm | chart | list | custom
          title (str)          — display title
          size (str, optional) — sm | md | lg | full (default 'md')
          config (dict, opt)   — widget-specific settings
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_add_widget")
        from app.api.routes.dashboard_config import _load_config, _save_config, WidgetConfig
        import uuid

        tab_id = p.get("tab_id", "").strip()
        widget_type = p.get("widget_type", "").strip()
        title = p.get("title", "").strip()

        if not tab_id:
            return ToolResult("dashboard_add_widget", False, error="'tab_id' is required.")
        if not widget_type:
            return ToolResult("dashboard_add_widget", False,
                              error="'widget_type' is required. Options: stat, activity, chat, agents, calendar, crm, chart, list, custom")

        valid_types = {"stat", "activity", "chat", "agents", "calendar", "crm", "chart", "list", "custom"}
        if widget_type not in valid_types:
            return ToolResult("dashboard_add_widget", False,
                              error=f"Invalid widget type '{widget_type}'. Valid: {sorted(valid_types)}")

        config = _load_config(self.owner_id)
        tab = next((t for t in config.tabs if t.id == tab_id), None)
        if not tab:
            available = [t.id for t in config.tabs]
            return ToolResult("dashboard_add_widget", False,
                              error=f"Tab '{tab_id}' not found. Available tabs: {available}")

        widget_id = f"w-{widget_type}-{uuid.uuid4().hex[:6]}"
        widget = WidgetConfig(
            id=widget_id,
            type=widget_type,
            title=title or widget_type.capitalize(),
            size=p.get("size", "md"),
            position=len(tab.widgets),
            config=p.get("config", {}),
        )
        tab.widgets.append(widget)
        _save_config(self.owner_id, config)
        return ToolResult(
            "dashboard_add_widget", True,
            data=f"Widget '{widget.title}' (type: {widget_type}, id: {widget_id}) added to tab '{tab_id}'."
        )

    def _dashboard_remove_widget(self, p: dict) -> ToolResult:
        """Remove a widget from a tab.

        Params: tab_id (str), widget_id (str)
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_remove_widget")
        from app.api.routes.dashboard_config import _load_config, _save_config

        tab_id = p.get("tab_id", "").strip()
        widget_id = p.get("widget_id", "").strip()

        if not tab_id or not widget_id:
            return ToolResult("dashboard_remove_widget", False,
                              error="Both 'tab_id' and 'widget_id' are required.")

        config = _load_config(self.owner_id)
        tab = next((t for t in config.tabs if t.id == tab_id), None)
        if not tab:
            return ToolResult("dashboard_remove_widget", False,
                              error=f"Tab '{tab_id}' not found.")

        before = len(tab.widgets)
        tab.widgets = [w for w in tab.widgets if w.id != widget_id]
        if len(tab.widgets) == before:
            return ToolResult("dashboard_remove_widget", False,
                              error=f"Widget '{widget_id}' not found in tab '{tab_id}'.")

        for i, w in enumerate(tab.widgets):
            w.position = i
        _save_config(self.owner_id, config)
        return ToolResult(
            "dashboard_remove_widget", True,
            data=f"Widget '{widget_id}' removed from tab '{tab_id}'."
        )

    def _dashboard_change_theme(self, p: dict) -> ToolResult:
        """Update the owner's dashboard theme/visual settings.

        Params (all optional):
          accent_color (str)   — hex color e.g. '#8B5CF6' (purple), '#3B82F6' (blue), '#10B981' (green)
          card_style (str)     — bordered | filled | glass
          density (str)        — compact | comfortable | spacious
          sidebar_style (str)  — dark | light | glass
          font (str)           — system | inter | mono
          commander_position (str) — sidebar | tab | floating | hidden
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_change_theme")
        from app.api.routes.dashboard_config import _load_config, _save_config

        config = _load_config(self.owner_id)
        changes = []

        if "accent_color" in p:
            config.theme.accent_color = p["accent_color"]
            changes.append(f"accent → {p['accent_color']}")

        if "card_style" in p:
            valid = {"bordered", "filled", "glass"}
            if p["card_style"] not in valid:
                return ToolResult("dashboard_change_theme", False,
                                  error=f"card_style must be one of: {valid}")
            config.theme.card_style = p["card_style"]
            changes.append(f"cards → {p['card_style']}")

        if "density" in p:
            valid = {"compact", "comfortable", "spacious"}
            if p["density"] not in valid:
                return ToolResult("dashboard_change_theme", False,
                                  error=f"density must be one of: {valid}")
            config.theme.density = p["density"]
            changes.append(f"density → {p['density']}")

        if "sidebar_style" in p:
            valid = {"dark", "light", "glass"}
            if p["sidebar_style"] not in valid:
                return ToolResult("dashboard_change_theme", False,
                                  error=f"sidebar_style must be one of: {valid}")
            config.theme.sidebar_style = p["sidebar_style"]
            changes.append(f"sidebar → {p['sidebar_style']}")

        if "font" in p:
            config.theme.font_preference = p["font"]
            changes.append(f"font → {p['font']}")

        if "commander_position" in p:
            valid = {"sidebar", "tab", "floating", "hidden"}
            if p["commander_position"] not in valid:
                return ToolResult("dashboard_change_theme", False,
                                  error=f"commander_position must be one of: {valid}")
            config.commander_position = p["commander_position"]
            changes.append(f"commander → {p['commander_position']}")

        if not changes:
            return ToolResult("dashboard_change_theme", False,
                              error="No theme fields provided. Options: accent_color, card_style, density, sidebar_style, font, commander_position")

        _save_config(self.owner_id, config)
        return ToolResult(
            "dashboard_change_theme", True,
            data=f"Theme updated: {', '.join(changes)}"
        )

    def _dashboard_reorder_tabs(self, p: dict) -> ToolResult:
        """Reorder the owner's dashboard tabs.

        Params: tab_order (list[str]) — tab IDs in the desired left-to-right order.
        Example: {"tab_order": ["overview", "crm", "calendar", "commander", "agents"]}
        """
        self._guard.require(Permission.CUSTOMIZE_DASHBOARD, "dashboard_reorder_tabs")
        from app.api.routes.dashboard_config import _load_config, _save_config

        tab_order = p.get("tab_order")
        if not tab_order or not isinstance(tab_order, list):
            return ToolResult("dashboard_reorder_tabs", False,
                              error="'tab_order' must be a list of tab IDs.")

        config = _load_config(self.owner_id)
        tab_map = {t.id: t for t in config.tabs}
        reordered = []
        for i, tid in enumerate(tab_order):
            if tid in tab_map:
                tab_map[tid].position = i
                reordered.append(tab_map[tid])

        # Append any tabs not in the order list at the end
        ordered_set = set(tab_order)
        for tab in config.tabs:
            if tab.id not in ordered_set:
                tab.position = len(reordered)
                reordered.append(tab)

        config.tabs = reordered
        _save_config(self.owner_id, config)
        final_order = [t.label for t in reordered]
        return ToolResult(
            "dashboard_reorder_tabs", True,
            data=f"Tabs reordered: {' → '.join(final_order)}"
        )

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