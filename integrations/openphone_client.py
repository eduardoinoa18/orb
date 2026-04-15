"""OpenPhone client for ORB Platform.

Agents can use OpenPhone to:
  - Send SMS messages from a business number
  - Make outbound calls (initiate via API)
  - Look up contacts
  - Get call and message history
  - Log notes on conversations

OpenPhone is the modern business phone for teams — great for real estate
agents, sales teams, and any business needing a professional phone presence.

Requires:
  OPENPHONE_API_KEY    — API key from OpenPhone Settings → Integrations → API

Docs: https://www.openphone.com/docs/api-reference
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.openphone")

BASE_URL = "https://api.openphone.com/v1"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_openphone_available() -> bool:
    return bool(get_settings().resolve("openphone_api_key", default=""))


def _api_key() -> str:
    return get_settings().resolve("openphone_api_key", default="")


def _headers() -> dict[str, str]:
    return {
        "Authorization": _api_key(),
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE_URL}/{path.lstrip('/')}{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

def list_phone_numbers() -> list[dict[str, Any]]:
    """Get all OpenPhone numbers on the account.

    Returns: List of {id, number, name, status}.
    """
    resp = _get("phone-numbers")
    return [
        {
            "id": p.get("id"),
            "number": p.get("number"),
            "name": p.get("name"),
            "status": p.get("status"),
        }
        for p in resp.get("data", [])
    ]


def _default_phone_number_id() -> str:
    """Get the first available phone number ID."""
    numbers = list_phone_numbers()
    if numbers:
        return numbers[0]["id"]
    return ""


# ---------------------------------------------------------------------------
# Messages (SMS/MMS)
# ---------------------------------------------------------------------------

def send_sms(
    to: str,
    text: str,
    from_number_id: str | None = None,
    media_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Send an SMS or MMS from an OpenPhone number.

    Args:
        to: Recipient phone number (E.164 format e.g. '+15551234567').
        text: Message text.
        from_number_id: OpenPhone number ID to send from (defaults to first number).
        media_urls: Optional list of image URLs for MMS.

    Returns: Created message resource.
    """
    phone_number_id = from_number_id or _default_phone_number_id()
    body: dict[str, Any] = {
        "to": [to],
        "text": text,
        "phoneNumberId": phone_number_id,
    }
    if media_urls:
        body["media"] = [{"url": u} for u in media_urls]
    resp = _post("messages", body)
    return resp.get("data", resp)


def get_messages(
    phone_number_id: str | None = None,
    contact_phone: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get message history from a phone number.

    Args:
        phone_number_id: OpenPhone number ID.
        contact_phone: Filter to messages with this contact.
        limit: Max messages to return.
    """
    pid = phone_number_id or _default_phone_number_id()
    params: dict[str, Any] = {"phoneNumberId": pid, "maxResults": limit}
    if contact_phone:
        params["participants"] = contact_phone
    resp = _get("messages", params)
    return [
        {
            "id": m.get("id"),
            "direction": m.get("direction"),
            "text": m.get("text", ""),
            "from": m.get("from"),
            "to": m.get("to", []),
            "created_at": m.get("createdAt"),
            "status": m.get("status"),
        }
        for m in resp.get("data", [])
    ]


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

def initiate_call(to: str, from_number_id: str | None = None) -> dict[str, Any]:
    """Initiate an outbound call.

    Args:
        to: Recipient phone number (E.164 format).
        from_number_id: OpenPhone number ID.

    Returns: Call resource with {id, status, direction}.
    """
    phone_number_id = from_number_id or _default_phone_number_id()
    resp = _post("calls", {
        "to": to,
        "phoneNumberId": phone_number_id,
    })
    return resp.get("data", resp)


def get_calls(phone_number_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Get call history for a phone number."""
    pid = phone_number_id or _default_phone_number_id()
    resp = _get("calls", {"phoneNumberId": pid, "maxResults": limit})
    return [
        {
            "id": c.get("id"),
            "direction": c.get("direction"),
            "status": c.get("status"),
            "duration_seconds": c.get("duration", 0),
            "from": c.get("from"),
            "to": c.get("to"),
            "created_at": c.get("createdAt"),
            "voicemail": bool(c.get("voicemail")),
        }
        for c in resp.get("data", [])
    ]


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def search_contacts(query: str) -> list[dict[str, Any]]:
    """Search OpenPhone contacts by name or phone."""
    resp = _get("contacts", {"query": query})
    return [
        {
            "id": c.get("id"),
            "name": f"{c.get('firstName', '')} {c.get('lastName', '')}".strip(),
            "phones": [p.get("phoneNumber", "") for p in c.get("phoneNumbers", [])],
            "emails": [e.get("email", "") for e in c.get("emails", [])],
        }
        for c in resp.get("data", [])
    ]


def create_contact(
    first_name: str,
    last_name: str = "",
    phone: str = "",
    email: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Create a new OpenPhone contact."""
    body: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
    }
    if phone:
        body["phoneNumbers"] = [{"phoneNumber": phone}]
    if email:
        body["emails"] = [{"email": email}]
    if company:
        body["company"] = company
    resp = _post("contacts", body)
    return resp.get("data", resp)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching phone numbers."""
    try:
        numbers = list_phone_numbers()
        return {
            "success": True,
            "phone_numbers": [n["number"] for n in numbers],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
