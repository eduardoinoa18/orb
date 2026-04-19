"""Minimal Resend email helper used by onboarding and trial lifecycle flows."""

from __future__ import annotations

import logging
from typing import Any

import resend

from config.settings import get_settings


logger = logging.getLogger("orb.integrations.resend")


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
    try:
        result = resend.Emails.send(
            {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )
        return {"sent": True, "provider": "resend", "result": result}
    except Exception as exc:
        # Email delivery must not block onboarding/account creation.
        logger.exception("Resend delivery failed", extra={"to_email": to_email, "subject": subject})
        return {
            "sent": False,
            "skipped": True,
            "reason": f"Resend send failed: {exc}",
        }


def send_email(to: str, subject: str, body: str, from_email: str = "ORB <onboarding@orb.local>") -> dict[str, Any]:
    """Backward-compatible alias used by older modules expecting send_email()."""
    # Keep plain-text callers working by wrapping body in a <pre> block.
    html = f"<pre style='font-family: inherit; white-space: pre-wrap'>{body}</pre>"
    return send_resend_email(to_email=to, subject=subject, html=html, from_email=from_email)
