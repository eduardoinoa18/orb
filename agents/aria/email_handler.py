"""Aria email handler — reads Gmail for the owner's morning briefing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from integrations.google_client import get_gmail_service, is_authorized


class AriaEmailHandler:
	"""Reads owner's Gmail inbox to surface important emails in the morning briefing."""

	def get_unread_today(self, max_results: int = 5) -> list[dict[str, Any]]:
		"""
		Fetch metadata for unread emails received today.

		Returns:
			List of dicts: {from_name, from_email, subject, snippet}
			Empty list when not authorized or Gmail is unavailable.
		"""
		if not is_authorized():
			return []

		service = get_gmail_service()
		if not service:
			return []

		try:
			today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
			results = (
				service.users()
				.messages()
				.list(userId="me", q=f"is:unread after:{today}", maxResults=max_results)
				.execute()
			)
			messages = results.get("messages", [])

			emails: list[dict[str, Any]] = []
			for msg in messages[:max_results]:
				meta = (
					service.users()
					.messages()
					.get(
						userId="me",
						id=msg["id"],
						format="metadata",
						metadataHeaders=["From", "Subject"],
					)
					.execute()
				)
				headers = {
					h["name"].lower(): h["value"]
					for h in meta.get("payload", {}).get("headers", [])
				}
				from_name, from_email = _parse_from(headers.get("from", ""))
				emails.append(
					{
						"from_name": from_name,
						"from_email": from_email,
						"subject": headers.get("subject", "(no subject)"),
						"snippet": _clean_snippet(meta.get("snippet", "")),
					}
				)
			return emails

		except Exception as exc:
			print(f"[AriaEmailHandler] Gmail error: {exc}")
			return []

	def get_unread_count_today(self) -> int:
		"""Return the count of today's unread emails without fetching full details."""
		if not is_authorized():
			return 0

		service = get_gmail_service()
		if not service:
			return 0

		try:
			today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
			results = (
				service.users()
				.messages()
				.list(userId="me", q=f"is:unread after:{today}", maxResults=50)
				.execute()
			)
			return results.get("resultSizeEstimate", 0)
		except Exception:
			return 0


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_from(from_header: str) -> tuple[str, str]:
	"""Split a From header into (display_name, email_address)."""
	m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', from_header.strip())
	if m:
		return m.group(1).strip(), m.group(2).strip()
	return "", from_header.strip()


def _clean_snippet(snippet: str) -> str:
	"""Strip HTML entities, collapse whitespace, truncate to 120 chars."""
	text = re.sub(r"&#?[a-z0-9]+;", " ", snippet)
	text = re.sub(r"\s+", " ", text).strip()
	return text[:120]
