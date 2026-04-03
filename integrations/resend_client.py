"""Minimal Resend email helper used by onboarding and trial lifecycle flows."""

from __future__ import annotations

from typing import Any

import resend

from config.settings import get_settings


def send_resend_email(to_email: str, subject: str, html: str, from_email: str = "ORB <onboarding@orb.local>") -> dict[str, Any]:
    """Sends an email via Resend when configured; returns a skip payload otherwise."""
    settings = get_settings()
    api_key = str(settings.resend_api_key or "").strip()
    if not api_key:
        return {
            "sent": False,
            "skipped": True,
            "reason": "RESEND_API_KEY is not configured.",
        }

    resend.api_key = api_key
    result = resend.Emails.send(
        {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
    )
    return {"sent": True, "provider": "resend", "result": result}
