"""Inbound email helper for Commander command routing."""

from __future__ import annotations

from typing import Any

from app.api.routes.commander import process_owner_email_command


def handle_incoming_email_message(from_email: str, subject: str, text_body: str) -> dict[str, Any] | None:
    """Routes supported inbound email commands to Commander.

    Subject line commands are preferred. If no subject is provided, the body is
    used as the command text.
    """
    normalized_subject = (subject or "").strip()
    normalized_body = (text_body or "").strip()
    command_text = normalized_subject or normalized_body

    if not command_text:
        return {"handled": True, "message": "Empty email received. Reply with HELP for supported commands."}

    upper = command_text.upper()
    if upper == "HELP":
        return {
            "handled": True,
            "message": (
                "Commander email commands: STATUS, APPROVE <token>, DECLINE <token>. "
                "Use subject for fastest processing."
            ),
        }

    return process_owner_email_command(from_email=from_email, message_body=command_text)
