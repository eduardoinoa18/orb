"""Rex follow-up orchestration and SMS drip campaigns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.twilio_client import send_sms


class RexFollowupEngine:
    """Manages follow-up scheduling, SMS drips, and automated outreach."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def schedule_followup(
        self,
        lead_id: str,
        owner_id: str,
        followup_type: str,
        delay_hours: int,
    ) -> dict[str, Any]:
        """
        Schedules a follow-up by setting next_followup timestamp.

        followup_type: descriptive label (e.g., "warm_contact", "objection_handling", "final_call")
        delay_hours: hours from now until follow-up should happen
        """
        next_followup = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
        payload: dict[str, Any] = {
            "next_followup": next_followup.isoformat(),
            "followup_type": followup_type,
        }

        try:
            return self.db.update("leads", lead_id, payload)
        except DatabaseConnectionError:
            # Fallback: return synthetic update
            return {"id": lead_id, **payload}

    def get_due_followups(self, owner_id: str) -> list[dict[str, Any]]:
        """
        Fetches leads where next_followup <= now + 1 hour.

        Provides a 1-hour window for batch processing.
        Returns empty list if database fails.
        """
        try:
            leads = self.db.fetch_all("leads", {"owner_id": owner_id})
            now = datetime.now(timezone.utc)
            window = now + timedelta(hours=1)
            result = []
            for lead in leads:
                followup_str = lead.get("next_followup")
                if followup_str:
                    try:
                        followup_time = datetime.fromisoformat(str(followup_str))
                        if followup_time <= window:
                            result.append(lead)
                    except (ValueError, TypeError):
                        pass
            return result
        except DatabaseConnectionError:
            return []

    def send_sms_followup(
        self,
        lead_id: str,
        message_text: str,
    ) -> dict[str, Any]:
        """
        Sends an SMS follow-up and logs to activity_log.

        Returns dict with: success, sid, status, or error message.
        """
        # Fetch lead to get phone number
        try:
            leads = self.db.fetch_all("leads", {"id": lead_id})
            lead = leads[0] if leads else None
        except DatabaseConnectionError:
            lead = None

        if not lead or not lead.get("phone"):
            return {
                "success": False,
                "error": "Lead not found or missing phone number",
                "lead_id": lead_id,
            }

        phone = str(lead["phone"])
        try:
            result = send_sms(to=phone, message=message_text)
            # Log successful send
            self.db.log_activity(
                agent_id=None,
                owner_id=lead.get("owner_id"),
                action_type="sms_followup",
                description=f"Sent follow-up SMS to lead {lead_id}",
                cost_cents=result.get("cost_cents", 1),
                outcome="success",
                metadata={"lead_id": lead_id, "phone": phone},
            )
            return {
                "success": True,
                "sid": result.get("sid"),
                "status": result.get("status"),
                "lead_id": lead_id,
            }
        except Exception as error:
            # Log failed send
            try:
                self.db.log_activity(
                    agent_id=None,
                    owner_id=lead.get("owner_id"),
                    action_type="sms_followup",
                    description=f"Failed SMS to lead {lead_id}",
                    cost_cents=0,
                    outcome=f"error: {error}",
                    metadata={"lead_id": lead_id},
                )
            except Exception:
                pass
            return {
                "success": False,
                "error": str(error),
                "lead_id": lead_id,
            }

    def run_followup_sequence(self, owner_id: str) -> dict[str, Any]:
        """
        Orchestrates the complete follow-up workflow.

        Gets due leads, sends SMS, updates lead status, logs activity.
        Returns: {sent_count, skipped_count, errors}
        """
        due_leads = self.get_due_followups(owner_id)
        sent_count = 0
        skipped_count = 0
        errors: list[str] = []

        for lead in due_leads:
            lead_id = lead.get("id")
            if not lead_id:
                skipped_count += 1
                continue

            phone = lead.get("phone")
            if not phone:
                skipped_count += 1
                continue

            # Build a generic follow-up message
            lead_name = lead.get("contact_name", "there")
            message = f"Hi {lead_name}, just following up on your interest in {lead.get('property_address', 'properties')}. Call me back when you get a chance!"

            # Truncate to SMS limit
            if len(message) > 160:
                message = message[:157] + "..."

            # Send SMS
            sms_result = self.send_sms_followup(lead_id, message)
            if sms_result.get("success"):
                sent_count += 1
                # Update lead to mark it as contacted and reschedule next follow-up
                try:
                    self.db.update(
                        "leads",
                        lead_id,
                        {
                            "status": "contacted",
                            "call_count": int(lead.get("call_count", 0)) + 1,
                            "last_contact": datetime.now(timezone.utc).isoformat(),
                            "next_followup": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                        },
                    )
                except DatabaseConnectionError:
                    pass
            else:
                skipped_count += 1
                errors.append(f"{lead_id}: {sms_result.get('error', 'Unknown error')}")

        # Log overall sequence completion
        try:
            self.db.log_activity(
                agent_id=None,
                owner_id=owner_id,
                action_type="followup_sequence",
                description=f"Completed follow-up sequence: {sent_count} sent, {skipped_count} skipped",
                outcome="success" if errors == [] else f"partial: {len(errors)} errors",
                metadata={
                    "sent_count": sent_count,
                    "skipped_count": skipped_count,
                    "error_count": len(errors),
                },
            )
        except DatabaseConnectionError:
            pass

        return {
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    def generate_drip_sequence(
        self,
        lead_id: str,
        sequence_type: str,
    ) -> list[dict[str, Any]]:
        """
        Generates a drip campaign sequence.

        sequence_type: one of: new_lead, warm_lead, long_term_nurture
        Returns: list of {day, message} dicts representing a drip campaign schedule.
        """
        if sequence_type == "new_lead":
            return [
                {
                    "day": 0,
                    "message": "Hi! Thanks for reaching out. I'm excited to help you find the right property. Let's chat soon!",
                },
                {
                    "day": 1,
                    "message": "Quick follow-up: I found a couple properties that might be perfect for you. Call me to discuss?",
                },
                {
                    "day": 3,
                    "message": "Still interested in moving forward? I have some great options to show you.",
                },
                {
                    "day": 7,
                    "message": "Last message: Let's schedule a viewing. I'm confident we can find something perfect for you!",
                },
            ]
        elif sequence_type == "warm_lead":
            return [
                {
                    "day": 0,
                    "message": "Hi! Wanted to check in on your interest. Are you ready to move forward?",
                },
                {
                    "day": 2,
                    "message": "I have market updates that might interest you. Call me to discuss?",
                },
                {
                    "day": 5,
                    "message": "Last chance: Let's finalize your search. Ready to see some properties?",
                },
            ]
        elif sequence_type == "long_term_nurture":
            return [
                {
                    "day": 0,
                    "message": "Market update for your area: Prices are trending up. Ready to discuss your options?",
                },
                {
                    "day": 7,
                    "message": "New listing just hit the market in your area. Thought of you immediately. Interested?",
                },
                {
                    "day": 14,
                    "message": "Continuing to think about your real estate goals? Happy to help anytime.",
                },
                {
                    "day": 30,
                    "message": "Month check-in: Any changes to your timeline? Let's reconnect.",
                },
            ]
        else:
            # Fallback generic drip
            return [
                {"day": 0, "message": "Hi! Thanks for your interest. Let's connect soon."},
                {"day": 3, "message": "Still interested? Would love to follow up."},
                {"day": 7, "message": "Final message: Ready to move forward together?"},
            ]
