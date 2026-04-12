"""Google Calendar integration client for ORB Platform.

Allows Commander and agents to:
- Create, update, and cancel events
- List upcoming events
- Check availability (free/busy)
- Schedule meetings with attendees
- Set reminders

Requires: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in Railway env vars.
Free: unlimited via Google Calendar API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("orb.integrations.gcal")


def _get_service() -> Any:
    """Build an authenticated Google Calendar service."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client google-auth"
        ) from e

    from config.settings import get_settings
    settings = get_settings()

    client_id = settings.resolve("google_client_id")
    client_secret = settings.resolve("google_client_secret")
    refresh_token = settings.resolve("google_refresh_token")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Google Calendar not fully configured. "
            "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def is_gcal_available() -> bool:
    """Check whether Google Calendar is configured."""
    try:
        from config.settings import get_settings
        s = get_settings()
        return (
            s.is_configured("google_client_id")
            and s.is_configured("google_client_secret")
            and s.is_configured("google_refresh_token")
        )
    except Exception:
        return False


def list_upcoming_events(
    calendar_id: str = "primary",
    days: int = 7,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Return the next N events within the given number of days.

    Returns: [{id, summary, start, end, location, attendees, meeting_link}, ...]
    """
    service = _get_service()
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days)

    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception as e:
        logger.error("GCal list_upcoming_events failed: %s", e)
        raise RuntimeError(f"Google Calendar error: {e}") from e

    events = []
    for item in result.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})
        attendees = [a.get("email", "") for a in item.get("attendees", [])]
        meeting_link = (
            item.get("hangoutLink")
            or item.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "")
        )
        events.append({
            "id": item.get("id", ""),
            "summary": item.get("summary", "(No title)"),
            "description": item.get("description", ""),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "location": item.get("location", ""),
            "attendees": attendees,
            "meeting_link": meeting_link,
            "status": item.get("status", "confirmed"),
        })

    return events


def create_event(
    summary: str,
    start_datetime: datetime,
    end_datetime: datetime,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    add_google_meet: bool = False,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a calendar event.

    Args:
        summary: Event title.
        start_datetime: Start time (timezone-aware).
        end_datetime: End time (timezone-aware).
        description: Optional event body.
        location: Optional location string or video call URL.
        attendees: Optional list of email addresses.
        add_google_meet: If True, auto-generate a Google Meet link.
        calendar_id: Target calendar (default "primary").

    Returns: Created event dict with id, htmlLink, meetLink.
    """
    service = _get_service()

    event_body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": str(start_datetime.tzinfo or "UTC"),
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": str(end_datetime.tzinfo or "UTC"),
        },
    }

    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    if add_google_meet:
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": f"orb-{summary[:20].lower().replace(' ', '-')}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    try:
        created = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1 if add_google_meet else 0,
            sendUpdates="all" if attendees else "none",
        ).execute()

        meet_link = (
            created.get("hangoutLink")
            or created.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "")
        )
        logger.info("GCal event created: %s (%s)", summary, created.get("id"))
        return {
            "id": created.get("id"),
            "html_link": created.get("htmlLink"),
            "meet_link": meet_link,
            "summary": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
        }
    except Exception as e:
        logger.error("GCal create_event failed: %s", e)
        raise RuntimeError(f"Google Calendar error: {e}") from e


def update_event(
    event_id: str,
    updates: dict[str, Any],
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Update an existing event. Pass only the fields you want to change."""
    service = _get_service()
    try:
        existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        existing.update(updates)
        updated = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=existing,
            sendUpdates="all",
        ).execute()
        return {"id": updated.get("id"), "summary": updated.get("summary")}
    except Exception as e:
        logger.error("GCal update_event failed: %s", e)
        raise RuntimeError(f"Google Calendar error: {e}") from e


def cancel_event(event_id: str, calendar_id: str = "primary") -> bool:
    """Cancel (delete) an event."""
    service = _get_service()
    try:
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        logger.info("GCal event cancelled: %s", event_id)
        return True
    except Exception as e:
        logger.error("GCal cancel_event failed: %s", e)
        return False


def check_availability(
    emails: list[str],
    start_datetime: datetime,
    end_datetime: datetime,
) -> dict[str, Any]:
    """Check free/busy status for a list of emails in a time range.

    Returns: {email: [{start, end}]} for busy slots.
    """
    service = _get_service()
    try:
        body = {
            "timeMin": start_datetime.isoformat(),
            "timeMax": end_datetime.isoformat(),
            "items": [{"id": email} for email in emails],
        }
        result = service.freebusy().query(body=body).execute()
        calendars = result.get("calendars", {})
        busy_map = {
            email: [
                {"start": slot["start"], "end": slot["end"]}
                for slot in data.get("busy", [])
            ]
            for email, data in calendars.items()
        }
        return busy_map
    except Exception as e:
        logger.error("GCal check_availability failed: %s", e)
        raise RuntimeError(f"Google Calendar error: {e}") from e


def test_connection() -> tuple[bool, str]:
    """Verify Google Calendar connectivity."""
    try:
        events = list_upcoming_events(days=1, max_results=1)
        return True, f"Google Calendar connected — {len(events)} events today"
    except Exception as e:
        return False, f"Google Calendar error: {e}"
