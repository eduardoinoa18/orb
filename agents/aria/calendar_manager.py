"""Aria calendar manager — reads Google Calendar for the owner's daily schedule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from integrations.google_client import get_calendar_service, is_authorized


class AriaCalendarManager:
	"""Reads the owner's primary Google Calendar for the morning briefing."""

	def get_todays_events(self) -> list[dict[str, Any]]:
		"""
		Fetch all events scheduled for today (midnight to midnight UTC).

		Returns:
			List of dicts: {title, start_time, end_time, is_all_day, attendee_count, location}
			Empty list when not authorized or Calendar is unavailable.
		"""
		if not is_authorized():
			return []

		service = get_calendar_service()
		if not service:
			return []

		try:
			now = datetime.now(timezone.utc)
			day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
			day_end = day_start + timedelta(days=1)

			result = (
				service.events()
				.list(
					calendarId="primary",
					timeMin=day_start.isoformat(),
					timeMax=day_end.isoformat(),
					maxResults=10,
					singleEvents=True,
					orderBy="startTime",
				)
				.execute()
			)

			events: list[dict[str, Any]] = []
			for item in result.get("items", []):
				start = item.get("start", {})
				end = item.get("end", {})
				is_all_day = "date" in start

				events.append(
					{
						"title": item.get("summary", "Untitled"),
						"start_time": _fmt(start.get("dateTime") or start.get("date", ""), is_all_day),
						"end_time": _fmt(end.get("dateTime") or end.get("date", ""), is_all_day),
						"is_all_day": is_all_day,
						"attendee_count": len(item.get("attendees", [])),
						"location": item.get("location", ""),
					}
				)
			return events

		except Exception as exc:
			print(f"[AriaCalendarManager] Calendar error: {exc}")
			return []

	def get_next_event(self) -> dict[str, Any] | None:
		"""Return the next upcoming event within 24 hours, or None."""
		if not is_authorized():
			return None

		service = get_calendar_service()
		if not service:
			return None

		try:
			now = datetime.now(timezone.utc)
			end = now + timedelta(hours=24)
			result = (
				service.events()
				.list(
					calendarId="primary",
					timeMin=now.isoformat(),
					timeMax=end.isoformat(),
					maxResults=1,
					singleEvents=True,
					orderBy="startTime",
				)
				.execute()
			)
			items = result.get("items", [])
			if not items:
				return None
			item = items[0]
			start = item.get("start", {})
			is_all_day = "date" in start
			return {
				"title": item.get("summary", "Untitled"),
				"start_time": _fmt(start.get("dateTime") or start.get("date", ""), is_all_day),
				"is_all_day": is_all_day,
			}
		except Exception:
			return None


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt(dt_str: str, is_all_day: bool) -> str:
	"""Format an ISO 8601 datetime string to a readable short time (e.g. '9:30 AM')."""
	if not dt_str:
		return ""
	if is_all_day:
		return "All day"
	try:
		dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
		# strftime("%I") gives zero-padded hour — lstrip removes leading zero
		return dt.strftime("%I:%M %p").lstrip("0") or "12:00 AM"
	except Exception:
		return dt_str[:5]
