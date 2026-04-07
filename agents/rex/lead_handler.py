"""Rex lead management and capture workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService


class RexLeadHandler:
    """Manages lead capture, storage, and lifecycle tracking."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def capture_lead(
        self,
        owner_id: str,
        contact_name: str,
        phone: str,
        email: str,
        source: str,
        property_address: str,
        city: str,
        state: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """
        Captures a new lead into the database.

        Returns the inserted lead dict with id, created_at, etc.
        Falls back to a synthetic dict if database fails.
        """
        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "contact_name": contact_name,
            "phone": phone,
            "email": email,
            "source": source,
            "property_address": property_address,
            "city": city,
            "state": state,
            "notes": notes,
            "status": "new",
            "call_count": 0,
            "last_contact": None,
            "motivation_score": 0,
            "next_followup": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            return self.db.insert_one("leads", payload)
        except DatabaseConnectionError:
            # Fallback: return the payload with a synthetic ID
            payload["id"] = f"synthetic_{phone.replace('+', '').replace('-', '')}"
            return payload

    def get_active_leads(self, owner_id: str) -> list[dict[str, Any]]:
        """
        Fetches all leads with status not in (closed, lost).

        Returns empty list if database fails.
        """
        try:
            leads = self.db.fetch_all("leads", {"owner_id": owner_id})
            return [l for l in leads if l.get("status") not in ("closed", "lost")]
        except DatabaseConnectionError:
            return []

    def update_lead_status(
        self,
        lead_id: str,
        new_status: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """
        Updates lead status and optionally appends notes.

        new_status: one of: new, contacted, qualified, negotiating, closed, lost
        """
        payload: dict[str, Any] = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if notes:
            payload["notes"] = notes

        try:
            result = self.db.update("leads", lead_id, payload)
            return result
        except DatabaseConnectionError:
            # Fallback: return the update payload with the ID
            result = {"id": lead_id, **payload}
            return result

    def get_lead_by_phone(self, phone: str) -> dict[str, Any] | None:
        """
        Looks up a lead by phone number for inbound SMS matching.

        Returns None if not found or database fails.
        """
        try:
            results = self.db.fetch_all("leads", {"phone": phone})
            return results[0] if results else None
        except DatabaseConnectionError:
            return None

    def mark_contacted(
        self,
        lead_id: str,
        transcript_snippet: str = "",
    ) -> dict[str, Any]:
        """
        Updates lead contact tracking: call_count++, last_contact timestamp, transcript.

        Returns the updated lead dict.
        """
        try:
            # Fetch current lead to increment call_count
            leads = self.db.fetch_all("leads", {"id": lead_id})
            current_lead = leads[0] if leads else {}
        except DatabaseConnectionError:
            current_lead = {}

        current_call_count = int(current_lead.get("call_count", 0))
        payload: dict[str, Any] = {
            "call_count": current_call_count + 1,
            "last_contact": datetime.now(timezone.utc).isoformat(),
        }
        if transcript_snippet:
            payload["last_transcript"] = transcript_snippet

        try:
            return self.db.update("leads", lead_id, payload)
        except DatabaseConnectionError:
            payload["id"] = lead_id
            return payload

    def get_hot_leads(
        self,
        owner_id: str,
        threshold: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Fetches leads with motivation_score >= threshold (0-10 scale).

        Returns empty list if database fails.
        """
        try:
            leads = self.db.fetch_all("leads", {"owner_id": owner_id})
            return [
                l for l in leads
                if l.get("status") not in ("closed", "lost")
                and int(l.get("motivation_score", 0)) >= threshold
            ]
        except DatabaseConnectionError:
            return []

    def get_followup_due(self, owner_id: str) -> list[dict[str, Any]]:
        """
        Fetches leads where next_followup <= now.

        Returns empty list if database fails.
        """
        try:
            leads = self.db.fetch_all("leads", {"owner_id": owner_id})
            now = datetime.now(timezone.utc)
            return [
                l for l in leads
                if l.get("next_followup") and datetime.fromisoformat(str(l["next_followup"])) <= now
            ]
        except (DatabaseConnectionError, ValueError):
            return []
