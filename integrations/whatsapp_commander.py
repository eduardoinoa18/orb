"""WhatsApp inbound helper for Commander and trade approvals."""

from __future__ import annotations

from typing import Any

from app.api.routes.commander import process_mobile_command


def handle_incoming_whatsapp_message(from_number: str, message_body: str) -> dict[str, Any] | None:
    """Handles WhatsApp commands that should route to Commander first.

    Returns a response payload when handled, or None to allow other handlers
    (such as trade approval replies) to process the message.
    """
    message = (message_body or "").strip()
    if not message:
        return {"handled": True, "message": "Empty message received. Reply HELP for supported commands."}

    upper = message.upper()
    if upper == "HELP":
        return {
            "handled": True,
            "message": (
                "Commander commands: STATUS, APPROVE <token>, DECLINE <token>. "
                "Trade approvals: YES, NO, STOP."
            ),
        }

    # Keep trade decisions on the trade-reply path to prevent accidental chat fallback.
    if upper in {"YES", "NO", "STOP"}:
        return None

    mobile = process_mobile_command(from_number=from_number, message_body=message)
    if not mobile:
        return None

    return {
        "handled": True,
        "message": str(mobile.get("message") or "Command received."),
        "kind": mobile.get("kind"),
        "success": bool(mobile.get("success", True)),
    }
