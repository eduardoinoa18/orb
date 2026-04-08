"""WhatsApp inbound handler and outbound sender for Commander and agents."""

from __future__ import annotations

from typing import Any

from app.api.routes.commander import process_mobile_command
from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings

HELP_TEXT = """*ORB Commands*

YES/NO — approve/reject pending
STATUS — platform summary
LEADS — today's hot leads
COST — AI spend today
STOP — pause all agents
RESUME — restart agents
HELP — show this menu

Or just ask me anything."""

WHATSAPP_FROM = "whatsapp:+14155238886"  # Twilio sandbox; override with TWILIO_FROM_NUMBER


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


def send_whatsapp_message(to_phone: str, message: str) -> bool:
    """Send a WhatsApp message via Twilio.

    ``to_phone`` should be a plain E.164 number like ``+15555551234``.
    Returns True when the API call succeeds.
    """
    from integrations.twilio_client import get_twilio_client  # local import to avoid circular

    settings = get_settings()
    from_number = str(settings.resolve("twilio_from_number", default=WHATSAPP_FROM)).strip()
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    to_wa = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
    try:
        client = get_twilio_client()
        client.messages.create(body=message, from_=from_number, to=to_wa)
        return True
    except Exception:
        return False


def format_hot_lead_alert(lead_name: str, address: str, score: int, insight: str, price: str) -> str:
    """Return a formatted WhatsApp hot-lead notification string."""
    return (
        f"*HOT LEAD — Rex*\n"
        f"━━━━━━━━━━━━\n"
        f"*{lead_name}*\n"
        f"{address}\n\n"
        f"Score: {score}/10\n"
        f"Reason: {insight}\n"
        f"Asking: {price}\n\n"
        f"Reply *YES* to book appointment\n"
        f"Reply *CALL* to get their number\n"
        f"Reply *NO* to skip"
    )


def format_morning_briefing(
    owner_name: str,
    commander_name: str,
    lead_count: int,
    hot_count: int,
    meeting_count: int,
    pending_content: int,
    cost_yesterday: float,
    top_priority: str,
) -> str:
    """Return a formatted morning briefing WhatsApp message."""
    return (
        f"*Good morning, {owner_name}* ☀️\n\n"
        f"{commander_name} here. Here's your day:\n\n"
        f"*Rex:* {lead_count} leads, {hot_count} hot\n"
        f"*Aria:* {meeting_count} meetings today\n"
        f"*Nova:* {pending_content} posts ready for review\n"
        f"*Costs:* ${cost_yesterday:.2f} yesterday\n\n"
        f"{top_priority}\n\n"
        f"Reply *STATUS* for more or ask me anything."
    )


# ---------------------------------------------------------------------------
# Inbound helpers
# ---------------------------------------------------------------------------


def _find_owner_by_phone(phone: str) -> dict[str, Any] | None:
    try:
        db = SupabaseService()
        rows = db.fetch_all("owners", {"phone": phone})
        return rows[0] if rows else None
    except DatabaseConnectionError:
        return None


def _get_status_summary(owner_id: str) -> str:
    try:
        db = SupabaseService()
        agents = db.fetch_all("agents", {"owner_id": owner_id})
        agent_lines = "\n".join(
            f"• {row.get('name', 'Agent')}: {row.get('status', 'unknown')}"
            for row in agents
        )
        return f"*ORB Status*\n{agent_lines or 'No agents found.'}"
    except DatabaseConnectionError:
        return "Status unavailable right now."


def _get_hot_leads_summary(owner_id: str) -> str:
    try:
        db = SupabaseService()
        leads = db.fetch_all("leads", {"owner_id": owner_id})
        hot = [l for l in leads if int((l.get("score") or 0)) >= 7]
        if not hot:
            return "No hot leads right now. Rex is working on it."
        lines = "\n".join(f"• {l.get('name', 'Unknown')} — Score {l.get('score', '?')}/10" for l in hot[:5])
        return f"*Hot Leads ({len(hot)})*\n{lines}"
    except DatabaseConnectionError:
        return "Lead data unavailable right now."


def _get_cost_today(owner_id: str) -> str:
    from datetime import date

    try:
        db = SupabaseService()
        rows = db.fetch_all("activity_log", {"owner_id": owner_id})
        today_str = date.today().isoformat()
        spent_cents = sum(
            int(r.get("cost_cents") or 0)
            for r in rows
            if str(r.get("created_at", "")).startswith(today_str)
        )
        return f"*AI Spend Today:* ${spent_cents / 100:.2f}"
    except DatabaseConnectionError:
        return "Cost data unavailable right now."


def _pause_all_agents(owner_id: str) -> None:
    try:
        db = SupabaseService()
        db.update_many("agents", {"owner_id": owner_id}, {"status": "paused"})
    except DatabaseConnectionError:
        pass


def _resume_all_agents(owner_id: str) -> None:
    try:
        db = SupabaseService()
        db.update_many("agents", {"owner_id": owner_id}, {"status": "active"})
    except DatabaseConnectionError:
        pass


def _approve_pending_item(owner_id: str) -> str:
    try:
        db = SupabaseService()
        rows = db.fetch_all("approval_queue", {"owner_id": owner_id, "status": "pending"})
        if not rows:
            return "No pending approvals right now."
        item = rows[0]
        item_id = str(item.get("id") or "")
        if item_id:
            db.update_many("approval_queue", {"id": item_id}, {"status": "approved"})
        return f"Approved: {item.get('description', 'item')}."
    except DatabaseConnectionError:
        return "Could not process approval right now."


def _reject_pending_item(owner_id: str) -> str:
    try:
        db = SupabaseService()
        rows = db.fetch_all("approval_queue", {"owner_id": owner_id, "status": "pending"})
        if not rows:
            return "No pending approvals right now."
        item = rows[0]
        item_id = str(item.get("id") or "")
        if item_id:
            db.update_many("approval_queue", {"id": item_id}, {"status": "rejected"})
        return f"Rejected: {item.get('description', 'item')}."
    except DatabaseConnectionError:
        return "Could not process rejection right now."


# ---------------------------------------------------------------------------
# Main inbound handler
# ---------------------------------------------------------------------------


class WhatsAppCommander:
    """Handles inbound and outbound WhatsApp messages for Commander."""

    @staticmethod
    def send_message(to_phone: str, message: str) -> bool:
        """Send a WhatsApp message to an owner's phone number."""
        return send_whatsapp_message(to_phone=to_phone, message=message)

    @staticmethod
    def handle_incoming(from_number: str, body: str, media_url: str | None = None) -> str:
        """Route an inbound WhatsApp message and return the reply text."""
        clean_number = from_number.replace("whatsapp:", "").strip()
        message = (body or "").strip()

        if not message:
            return "Empty message received. Reply HELP for supported commands."

        upper = message.upper()

        owner = _find_owner_by_phone(clean_number)
        if not owner:
            settings = get_settings()
            domain = str(settings.resolve("platform_domain", default="app.yourplatform.com")).strip()
            return f"Hi! You're not registered with ORB. Sign up at {domain}"

        owner_id = str(owner.get("id") or "")

        if upper == "HELP":
            return HELP_TEXT

        if upper in {"YES", "Y", "APPROVE"}:
            return _approve_pending_item(owner_id)

        if upper in {"NO", "N", "REJECT"}:
            return _reject_pending_item(owner_id)

        if upper == "STOP":
            _pause_all_agents(owner_id)
            return "All agents paused. Text RESUME to restart."

        if upper == "RESUME":
            _resume_all_agents(owner_id)
            return "Agents restarted. Your team is back online."

        if upper == "STATUS":
            return _get_status_summary(owner_id)

        if upper == "LEADS":
            return _get_hot_leads_summary(owner_id)

        if upper == "COST":
            return _get_cost_today(owner_id)

        # Fallback: route to Commander brain via mobile command handler
        mobile = process_mobile_command(from_number=clean_number, message_body=message)
        if mobile:
            return str(mobile.get("message") or "Command received.")

        return "Got it. Your team is on it."


# ---------------------------------------------------------------------------
# Backward-compatible function (used by webhooks.py)
# ---------------------------------------------------------------------------


def handle_incoming_whatsapp_message(from_number: str, message_body: str) -> dict[str, Any] | None:
    """Handles WhatsApp commands that should route to Commander first.

    Returns a response payload when handled, or None to allow other handlers
    (such as trade approval replies) to process the message.
    """
    message = (message_body or "").strip()
    if not message:
        return {"handled": True, "message": "Empty message received. Reply HELP for supported commands."}

    upper = message.upper()
    if upper == "HELP":
        return {"handled": True, "message": HELP_TEXT}

    # Keep trade decisions on the trade-reply path to prevent accidental chat fallback.
    if upper in {"YES", "NO", "STOP"}:
        return None

    mobile = process_mobile_command(from_number=from_number, message_body=message)
    if not mobile:
        return None

    return {
        "handled": True,
        "message": str(mobile.get("message") or "Command received."),
        "kind": mobile.get("kind"),
        "success": bool(mobile.get("success", True)),
    }
