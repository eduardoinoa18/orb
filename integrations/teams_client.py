"""Microsoft Teams client for ORB Platform.

Lets Commander and agents:
  - Send messages and adaptive cards to Teams channels or users
  - Receive and route inbound messages from Teams Bot Framework
  - Post notifications, alerts, and structured summaries

Two connection modes:
  1. Incoming Webhook (simple, no auth needed per message) — for one-way alerts
  2. Bot Framework (full two-way conversation) — for interactive agent chat

Requires:
  TEAMS_WEBHOOK_URL   — Incoming Webhook URL for a specific channel (mode 1)
  TEAMS_BOT_TOKEN     — Bot Framework token for two-way (mode 2, optional)

Docs: https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.teams")

BOT_FRAMEWORK_URL = "https://smba.trafficmanager.net/amer/v3"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_teams_available() -> bool:
    s = get_settings()
    return bool(s.resolve("teams_webhook_url", default=""))


def _webhook_url() -> str:
    return get_settings().resolve("teams_webhook_url", default="")


def _bot_token() -> str:
    return get_settings().resolve("teams_bot_token", default="")


# ---------------------------------------------------------------------------
# Incoming Webhook (mode 1 — one-way alerts to a fixed channel)
# ---------------------------------------------------------------------------

def send_message(text: str, title: str | None = None) -> bool:
    """Send a plain text message via Incoming Webhook.

    Args:
        text: Message body (Markdown supported).
        title: Optional bold title line.

    Returns: True on success.
    """
    body: dict[str, Any] = {"text": text}
    if title:
        body["title"] = title

    data = json.dumps(body).encode()
    url = _webhook_url()
    if not url:
        raise ValueError("TEAMS_WEBHOOK_URL not configured.")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status == 200


def send_adaptive_card(title: str, body_items: list[str], actions: list[dict] | None = None) -> bool:
    """Send an Adaptive Card via Incoming Webhook.

    Args:
        title: Card title (bold header).
        body_items: List of text strings to show as card body rows.
        actions: Optional list of action buttons: [{type: 'Action.OpenUrl', title: '...', url: '...'}]
    """
    card_body = [{"type": "TextBlock", "text": title, "size": "Large", "weight": "Bolder"}]
    for item in body_items:
        card_body.append({"type": "TextBlock", "text": item, "wrap": True})

    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": card_body,
    }
    if actions:
        card["actions"] = actions

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }

    data = json.dumps(payload).encode()
    url = _webhook_url()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status in (200, 202)


def send_alert(title: str, summary: str, level: str = "info", link_url: str | None = None) -> bool:
    """Send a color-coded alert card.

    Args:
        title: Alert headline.
        summary: Alert body text.
        level: 'info' | 'warning' | 'error' | 'success'
        link_url: Optional "View Details" URL.
    """
    color_map = {"info": "accent", "warning": "warning", "error": "attention", "success": "good"}
    color = color_map.get(level, "accent")

    card_body = [
        {"type": "TextBlock", "text": title, "size": "Medium", "weight": "Bolder", "color": color},
        {"type": "TextBlock", "text": summary, "wrap": True},
    ]

    actions = []
    if link_url:
        actions.append({"type": "Action.OpenUrl", "title": "View Details", "url": link_url})

    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": card_body,
    }
    if actions:
        card["actions"] = actions

    payload = {
        "type": "message",
        "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _webhook_url(), data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status in (200, 202)


# ---------------------------------------------------------------------------
# Bot Framework replies (mode 2 — two-way conversation)
# ---------------------------------------------------------------------------

def reply_to_activity(service_url: str, conversation_id: str, activity_id: str, text: str) -> dict[str, Any]:
    """Send a reply to a Bot Framework message activity.

    Args:
        service_url: The serviceUrl from the inbound activity payload.
        conversation_id: Conversation ID from the activity.
        activity_id: ID of the activity to reply to.
        text: Reply text (Markdown supported).

    Requires: TEAMS_BOT_TOKEN
    """
    token = _bot_token()
    if not token:
        raise ValueError("TEAMS_BOT_TOKEN required for Bot Framework replies.")

    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}"
    body = json.dumps({
        "type": "message",
        "text": text,
        "textFormat": "markdown",
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Inbound Bot Framework parsing
# ---------------------------------------------------------------------------

def parse_bot_activity(payload: dict) -> dict[str, Any] | None:
    """Normalize a Teams Bot Framework activity payload.

    Returns: {sender_id, sender_name, text, conversation_id, activity_id, service_url}
    """
    try:
        if payload.get("type") != "message":
            return None
        return {
            "sender_id": payload["from"]["id"],
            "sender_name": payload["from"].get("name", ""),
            "text": payload.get("text", ""),
            "conversation_id": payload["conversation"]["id"],
            "activity_id": payload.get("id", ""),
            "service_url": payload.get("serviceUrl", BOT_FRAMEWORK_URL),
            "channel_id": payload.get("channelId", "msteams"),
        }
    except Exception as e:
        logger.debug("Could not parse Teams activity: %s", e)
    return None


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test Teams connection by sending a silent ping card."""
    try:
        ok = send_message("🤖 ORB Platform connected to Microsoft Teams successfully.")
        return {"success": ok, "mode": "incoming_webhook"}
    except Exception as e:
        return {"success": False, "error": str(e)}
