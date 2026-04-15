"""Calendly v2 API client for ORB Platform.

Agents can use Calendly to:
  - Check upcoming scheduled meetings
  - Create single-use scheduling links for leads
  - Cancel scheduled events
  - Look up invitee details after a booking
  - Get event type info (meeting types available)

Requires:
  CALENDLY_API_KEY       — Personal Access Token from Calendly Settings
  CALENDLY_USER_URI      — Your Calendly user URI (auto-resolved if not set)

Docs: https://developer.calendly.com/api-docs
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.calendly")

BASE_URL = "https://api.calendly.com"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_calendly_available() -> bool:
    s = get_settings()
    return bool(s.resolve("calendly_api_key", default=""))


def _api_key() -> str:
    return get_settings().resolve("calendly_api_key", default="")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


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


def _delete(path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        try:
            return json.loads(resp.read())
        except Exception:
            return {"deleted": True}


# ---------------------------------------------------------------------------
# User / organization
# ---------------------------------------------------------------------------

def get_current_user() -> dict[str, Any]:
    """Get the authenticated Calendly user."""
    resp = _get("/users/me")
    return resp.get("resource", resp)


def _get_user_uri() -> str:
    """Resolve the user URI, using env var or API fallback."""
    s = get_settings()
    uri = s.resolve("calendly_user_uri", default="")
    if uri:
        return uri
    user = get_current_user()
    return user.get("uri", "")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

def list_event_types() -> list[dict[str, Any]]:
    """List all event types (meeting types) for the user.

    Returns: List of {uri, name, duration_minutes, scheduling_url, active}.
    """
    user_uri = _get_user_uri()
    resp = _get("/event_types", {"user": user_uri})
    items = resp.get("collection", [])
    return [
        {
            "uri": e.get("uri", ""),
            "name": e.get("name", ""),
            "duration_minutes": e.get("duration", 0),
            "scheduling_url": e.get("scheduling_url", ""),
            "active": e.get("active", False),
            "slug": e.get("slug", ""),
        }
        for e in items
    ]


# ---------------------------------------------------------------------------
# Scheduled events
# ---------------------------------------------------------------------------

def list_upcoming_events(count: int = 10) -> list[dict[str, Any]]:
    """Get upcoming scheduled meetings.

    Returns: List of {uri, name, start_time, end_time, status, invitees_count}.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    user_uri = _get_user_uri()
    resp = _get("/scheduled_events", {
        "user": user_uri,
        "min_start_time": now,
        "count": count,
        "status": "active",
        "sort": "start_time:asc",
    })
    items = resp.get("collection", [])
    return [
        {
            "uri": e.get("uri", ""),
            "name": e.get("name", ""),
            "start_time": e.get("start_time", ""),
            "end_time": e.get("end_time", ""),
            "status": e.get("status", ""),
            "invitees_count": e.get("invitees_counter", {}).get("total", 0),
            "location": e.get("location", {}).get("join_url", e.get("location", {}).get("location", "")),
        }
        for e in items
    ]


def get_event(event_uri: str) -> dict[str, Any]:
    """Get details of a specific scheduled event."""
    # event_uri is a full URI like https://api.calendly.com/scheduled_events/UUID
    uuid = event_uri.split("/")[-1]
    resp = _get(f"/scheduled_events/{uuid}")
    return resp.get("resource", resp)


def get_event_invitees(event_uri: str) -> list[dict[str, Any]]:
    """Get invitees for a scheduled event.

    Returns: List of {name, email, status, created_at, questions_and_answers}.
    """
    uuid = event_uri.split("/")[-1]
    resp = _get(f"/scheduled_events/{uuid}/invitees")
    items = resp.get("collection", [])
    return [
        {
            "name": i.get("name", ""),
            "email": i.get("email", ""),
            "status": i.get("status", ""),
            "created_at": i.get("created_at", ""),
            "uri": i.get("uri", ""),
            "questions": i.get("questions_and_answers", []),
        }
        for i in items
    ]


def cancel_event(event_uri: str, reason: str = "Cancelled by ORB Platform") -> bool:
    """Cancel a scheduled event.

    Args:
        event_uri: Full event URI or UUID.
        reason: Cancellation reason sent to invitees.
    """
    uuid = event_uri.split("/")[-1]
    try:
        _post(f"/scheduled_events/{uuid}/cancellation", {"reason": reason})
        return True
    except Exception as e:
        logger.warning("Failed to cancel Calendly event: %s", e)
        return False


# ---------------------------------------------------------------------------
# Scheduling links (single-use)
# ---------------------------------------------------------------------------

def create_scheduling_link(
    event_type_uri: str,
    max_uses: int = 1,
) -> dict[str, Any]:
    """Create a single-use or limited-use scheduling link for a lead.

    Args:
        event_type_uri: Full URI of the event type (from list_event_types).
        max_uses: How many times the link can be used (1 = single-use).

    Returns: {booking_url} — the link to send to the lead.
    """
    resp = _post("/scheduling_links", {
        "max_event_count": max_uses,
        "owner": event_type_uri,
        "owner_type": "EventType",
    })
    resource = resp.get("resource", resp)
    return {"booking_url": resource.get("booking_url", "")}


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the authenticated user's profile."""
    try:
        user = get_current_user()
        return {
            "success": True,
            "name": user.get("name"),
            "email": user.get("email"),
            "slug": user.get("slug"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
