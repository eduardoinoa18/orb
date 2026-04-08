"""Aria's daily briefing engine.

Compiles owner priorities, trading activity, lead pipeline, and costs
into a concise SMS sent each morning at configured time.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.twilio_client import send_sms
from config.settings import get_settings
from agents.aria.email_handler import AriaEmailHandler
from agents.aria.calendar_manager import AriaCalendarManager


class AriaBriefingEngine:
    """Generates and sends daily morning briefing to owner."""

    def __init__(self):
        self.db = SupabaseService()
        self.settings = get_settings()
        self.email_handler = AriaEmailHandler()
        self.calendar_manager = AriaCalendarManager()

    def get_todays_tasks(self) -> list[dict[str, Any]]:
        """Fetch all tasks for today that are not completed."""
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            tasks = self.db.client.table("tasks").select("*").execute()
            if not tasks.data:
                return []
            
            todays = [
                t for t in tasks.data
                if t.get("status") != "completed"
                and (not t.get("due_at") or t["due_at"][:10] == today)
            ]
            return todays[:5]  # Limit to 5 tasks in briefing
        except Exception as e:
            print(f"Error fetching tasks: {e}")
            return []

    def get_trading_summary(self) -> dict[str, Any]:
        """Get Orion's paper trading activity from yesterday."""
        try:
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            
            trades = self.db.client.table("paper_trades").select(
                "status, pnl_dollars, created_at"
            ).execute()
            
            if not trades.data:
                return {
                    "trade_count": 0,
                    "pnl": 0.0,
                    "status": "no trades yesterday",
                }
            
            yesterdays = [
                t for t in trades.data
                if t.get("created_at", "")[:10] == yesterday
            ]
            
            if not yesterdays:
                return {
                    "trade_count": 0,
                    "pnl": 0.0,
                    "status": "no trades yesterday",
                }
            
            total_pnl = sum(t.get("pnl_dollars", 0) or 0 for t in yesterdays)
            winners = len([t for t in yesterdays if (t.get("pnl_dollars") or 0) > 0])
            
            return {
                "trade_count": len(yesterdays),
                "winners": winners,
                "pnl": total_pnl,
                "status": "paper trades closed",
            }
        except Exception as e:
            print(f"Error fetching trading summary: {e}")
            return {"trade_count": 0, "pnl": 0.0, "status": "unavailable"}

    def get_leads_summary(self) -> dict[str, Any]:
        """Get Rex's lead pipeline status."""
        try:
            leads = self.db.client.table("leads").select(
                "status"
            ).execute()
            
            if not leads.data:
                return {"hot": 0, "warm": 0, "cold": 0}
            
            hot = len([l for l in leads.data if l.get("status") == "hot"])
            warm = len([l for l in leads.data if l.get("status") == "warm"])
            cold = len([l for l in leads.data if l.get("status") == "cold"])
            
            return {"hot": hot, "warm": warm, "cold": cold}
        except Exception as e:
            print(f"Error fetching leads summary: {e}")
            return {"hot": 0, "warm": 0, "cold": 0}

    def get_calendar_events(self) -> list[dict[str, Any]]:
        """Fetch today's Google Calendar events (empty list if not connected)."""
        try:
            return self.calendar_manager.get_todays_events()
        except Exception:
            return []

    def get_email_summary(self) -> list[dict[str, Any]]:
        """Fetch today's unread Gmail messages (empty list if not connected)."""
        try:
            return self.email_handler.get_unread_today()
        except Exception:
            return []

    def get_daily_cost(self) -> float:
        """Get yesterday's estimated API costs."""
        try:
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            
            logs = self.db.client.table("activity_log").select(
                "cost_cents"
            ).execute()
            
            if not logs.data:
                return 0.0
            
            yesterdays = [
                l for l in logs.data
                if l.get("created_at", "")[:10] == yesterday
            ]
            
            total_cents = sum(l.get("cost_cents", 0) or 0 for l in yesterdays)
            return total_cents / 100.0
        except Exception as e:
            print(f"Error fetching daily cost: {e}")
            return 0.0

    def compose_briefing(
        self,
        tasks: list,
        trading: dict,
        leads: dict,
        cost: float,
        calendar_events: list | None = None,
        emails: list | None = None,
    ) -> str:
        """Generate SMS-friendly briefing text."""
        
        task_text = ""
        if tasks:
            task_text = "\n\nTODAY'S PRIORITIES:\n"
            for i, t in enumerate(tasks, 1):
                due = ""
                if t.get("due_at"):
                    due_time = t["due_at"].split("T")[1][:5] if "T" in t["due_at"] else ""
                    due = f" ({due_time})" if due_time else ""
                task_text += f"{i}. {t.get('title', 'Task')}{due}\n"
        
        calendar_text = ""
        if calendar_events:
            calendar_text = "\n\nCALENDAR TODAY:\n"
            for ev in calendar_events[:4]:
                time_str = ev.get("start_time", "")
                guests = f" ({ev['attendee_count']} guests)" if ev.get("attendee_count") else ""
                calendar_text += f"• {time_str} — {ev['title']}{guests}\n"

        email_text = ""
        if emails:
            email_text = f"\n\nEMAIL ({len(emails)} unread):\n"
            for em in emails[:3]:
                sender = em.get("from_name") or em.get("from_email", "Unknown")
                email_text += f"• {sender}: {em['subject']}\n"

        trading_text = ""
        if trading["trade_count"] > 0:
            trading_text = f"\nPAPER TRADING (Orion):\n{trading['trade_count']} trades | {trading['winners']} wins | P&L: ${trading['pnl']:.2f}"
        
        leads_text = ""
        hot = leads.get("hot", 0)
        warm = leads.get("warm", 0)
        if hot > 0 or warm > 0:
            leads_text = f"\nLEADS (Rex):\n{hot} hot | {warm} warm"
        
        briefing = f"""Good morning! Here's your day:
{task_text}{calendar_text}{email_text}{leads_text}{trading_text}

COST: ${cost:.2f} yesterday

View all details: http://localhost:8000/dashboard"""
        
        return briefing

    def send_briefing(self, text: str, to_number: str | None = None) -> dict[str, Any]:
        """Send briefing SMS to owner or a provided test number."""
        try:
            if not self.settings.twilio_phone_number:
                print("ERROR: TWILIO_PHONE_NUMBER not configured")
                return {"success": False, "error": "TWILIO_PHONE_NUMBER not configured", "recipient": None}

            recipient = (
                (to_number or "").strip()
                or (self.settings.my_phone_number or "").strip()
                or (self.settings.twilio_phone_number or "").strip()
            )
            if not recipient:
                print("ERROR: No recipient number configured for briefing")
                return {"success": False, "error": "No recipient number configured", "recipient": None}
            
            send_sms(
                to=recipient,
                message=text,
                from_number=self.settings.twilio_phone_number,
            )
            
            # Log to activity
            self.db.log_activity(
                agent_id=None,
                owner_id=None,
                action_type="briefing_sent",
                description=f"Daily briefing SMS sent to {recipient}",
                cost_cents=10,
            )
            
            print(f"✓ Briefing sent successfully")
            return {"success": True, "error": None, "recipient": recipient}
        except Exception as e:
            print(f"ERROR sending briefing SMS: {e}")
            return {"success": False, "error": str(e), "recipient": recipient if 'recipient' in locals() else None}

    def generate_and_send_briefing(self, to_number: str | None = None) -> dict[str, Any]:
        """Main entry point: pull all data, compose, and send briefing."""
        tasks = self.get_todays_tasks()
        trading = self.get_trading_summary()
        leads = self.get_leads_summary()
        cost = self.get_daily_cost()
        calendar_events = self.get_calendar_events()
        emails = self.get_email_summary()
        
        briefing_text = self.compose_briefing(tasks, trading, leads, cost, calendar_events, emails)
        send_result = self.send_briefing(briefing_text, to_number=to_number)
        
        return {
            "success": send_result.get("success", False),
            "send_error": send_result.get("error"),
            "sent_to": send_result.get("recipient"),
            "tasks_included": len(tasks),
            "trading_summary": trading,
            "leads_summary": leads,
            "daily_cost": cost,
            "calendar_events": len(calendar_events),
            "emails_unread": len(emails),
            "briefing_text": briefing_text,
        }

    def get_briefing_preview(self) -> str:
        """Return what the briefing will say WITHOUT sending it."""
        tasks = self.get_todays_tasks()
        trading = self.get_trading_summary()
        leads = self.get_leads_summary()
        cost = self.get_daily_cost()
        calendar_events = self.get_calendar_events()
        emails = self.get_email_summary()
        
        return self.compose_briefing(tasks, trading, leads, cost, calendar_events, emails)
