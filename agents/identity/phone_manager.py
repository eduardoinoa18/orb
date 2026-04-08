"""Phone number management helpers."""

from __future__ import annotations

from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings
from integrations.twilio_client import _get_client


def get_available_numbers(area_code: str | None = None) -> list[dict[str, Any]]:
    """Searches Twilio for available local numbers when credentials exist.

    Falls back to the configured platform number so provisioning still works
    in local development without buying a new number.
    """
    settings = get_settings()
    fallback_number = settings.twilio_phone_number.strip()

    try:
        client = _get_client()
        search_kwargs: dict[str, Any] = {"limit": 5}
        if area_code and area_code.isdigit():
            search_kwargs["area_code"] = area_code
        numbers = client.available_phone_numbers("US").local.list(**search_kwargs)
        if numbers:
            return [
                {
                    "phone_number": item.phone_number,
                    "friendly_name": item.friendly_name,
                    "capabilities": getattr(item, "capabilities", {}),
                    "monthly_cost_estimate": "$1.15/mo",
                    "source": "twilio_search",
                }
                for item in numbers
            ]
    except Exception:
        pass

    if fallback_number:
        return [
            {
                "phone_number": fallback_number,
                "friendly_name": "ORB shared development number",
                "capabilities": {"sms": True, "voice": True},
                "monthly_cost_estimate": "$0.00 extra",
                "source": "configured_platform_number",
            }
        ]

    return []


def assign_number(agent_id: str, phone_number: str) -> dict[str, Any]:
    """Assigns an already-selected number to an agent record."""
    db = SupabaseService()
    rows = db.update_many("agents", {"id": agent_id}, {"phone_number": phone_number})
    return rows[0] if rows else {"id": agent_id, "phone_number": phone_number}


def route_incoming_sms(from_number: str, to_number: str, body: str) -> dict[str, Any]:
    """Routes an incoming SMS to the agent that owns the destination number."""
    try:
        db = SupabaseService()
        agents = db.fetch_all("agents", {"phone_number": to_number})
    except DatabaseConnectionError:
        agents = []

    agent = agents[0] if agents else None
    return {
        "matched": bool(agent),
        "route": "agent_sms_handler" if agent else "unmatched",
        "agent_id": agent.get("id") if agent else None,
        "agent_name": agent.get("name") if agent else None,
        "from_number": from_number,
        "to_number": to_number,
        "body": body,
    }


def route_incoming_call(from_number: str, to_number: str) -> dict[str, Any]:
    """Routes an incoming call to the owning agent when one is found."""
    try:
        db = SupabaseService()
        agents = db.fetch_all("agents", {"phone_number": to_number})
    except DatabaseConnectionError:
        agents = []

    agent = agents[0] if agents else None
    return {
        "matched": bool(agent),
        "route": "agent_call_handler" if agent else "voicemail_fallback",
        "agent_id": agent.get("id") if agent else None,
        "agent_name": agent.get("name") if agent else None,
        "from_number": from_number,
        "to_number": to_number,
    }
