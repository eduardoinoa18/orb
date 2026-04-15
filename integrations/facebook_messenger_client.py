"""Facebook Messenger client for ORB Platform.

Handles inbound user messages via the Messenger Platform and lets agents
send replies, structured messages, and quick-reply buttons.

Agents can use Messenger to:
  - Respond to leads who message your Facebook Page
  - Send follow-up sequences after form submissions
  - Deliver property listings or service summaries as rich cards

Requires:
  FACEBOOK_PAGE_TOKEN  — Page Access Token with pages_messaging permission
  FACEBOOK_APP_SECRET  — App Secret for webhook signature verification

Docs: https://developers.facebook.com/docs/messenger-platform
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.facebook_messenger")

GRAPH_URL = "https://graph.facebook.com/v18.0"


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_messenger_available() -> bool:
    s = get_settings()
    return bool(s.resolve("facebook_page_token", default=""))


def _token() -> str:
    return get_settings().resolve("facebook_page_token", default="")


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 from Facebook webhook."""
    secret = get_settings().resolve("facebook_app_secret", default="").encode()
    if not secret:
        logger.warning("FACEBOOK_APP_SECRET not set — skipping signature check")
        return True  # Fail open for now; tighten in production

    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post(path: str, body: dict) -> dict:
    body["access_token"] = _token()
    url = f"{GRAPH_URL}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _get(path: str, params: dict | None = None) -> dict:
    p = dict(params or {})
    p["access_token"] = _token()
    qs = urllib.parse.urlencode(p)
    url = f"{GRAPH_URL}/{path}?{qs}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Sending messages
# ---------------------------------------------------------------------------

def send_text(recipient_id: str, text: str) -> dict[str, Any]:
    """Send a plain text message to a Messenger user.

    Args:
        recipient_id: Page-scoped user ID (from inbound webhook).
        text: Message text (max 2,000 chars).
    """
    return _post("me/messages", {
        "recipient": {"id": recipient_id},
        "message": {"text": text[:2000]},
        "messaging_type": "RESPONSE",
    })


def send_quick_replies(recipient_id: str, text: str, options: list[str]) -> dict[str, Any]:
    """Send a text message with quick-reply buttons.

    Args:
        recipient_id: User PSID.
        text: Message body.
        options: Button labels (max 13, each max 20 chars).
    """
    quick_replies = [
        {"content_type": "text", "title": opt[:20], "payload": opt.upper().replace(" ", "_")}
        for opt in options[:13]
    ]
    return _post("me/messages", {
        "recipient": {"id": recipient_id},
        "message": {"text": text[:2000], "quick_replies": quick_replies},
        "messaging_type": "RESPONSE",
    })


def send_generic_template(recipient_id: str, cards: list[dict]) -> dict[str, Any]:
    """Send a generic template (carousel of cards).

    Each card: {title, subtitle (opt), image_url (opt), buttons (opt)}
    Each button: {type: 'web_url'|'postback', title, url|payload}

    Args:
        recipient_id: User PSID.
        cards: List of card dicts (max 10).
    """
    elements = []
    for card in cards[:10]:
        el: dict[str, Any] = {
            "title": card.get("title", "")[:80],
            "subtitle": card.get("subtitle", "")[:80],
        }
        if card.get("image_url"):
            el["image_url"] = card["image_url"]
        if card.get("buttons"):
            el["buttons"] = card["buttons"][:3]
        elements.append(el)

    return _post("me/messages", {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {"template_type": "generic", "elements": elements},
            }
        },
        "messaging_type": "RESPONSE",
    })


def send_typing_indicator(recipient_id: str, on: bool = True) -> dict[str, Any]:
    """Show or hide typing indicator."""
    action = "typing_on" if on else "typing_off"
    return _post("me/messages", {
        "recipient": {"id": recipient_id},
        "sender_action": action,
    })


def mark_seen(recipient_id: str) -> dict[str, Any]:
    """Mark the last message as seen."""
    return _post("me/messages", {
        "recipient": {"id": recipient_id},
        "sender_action": "mark_seen",
    })


# ---------------------------------------------------------------------------
# Inbound webhook parsing
# ---------------------------------------------------------------------------

def parse_inbound_message(payload: dict) -> dict[str, Any] | None:
    """Parse a Messenger webhook payload into a normalized message.

    Returns: {sender_id, text, message_id, timestamp, postback} or None.
    """
    try:
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                result: dict[str, Any] = {
                    "sender_id": event["sender"]["id"],
                    "recipient_id": event["recipient"]["id"],
                    "timestamp": event.get("timestamp", 0),
                    "text": "",
                    "message_id": "",
                    "postback": None,
                }
                if "message" in event:
                    msg = event["message"]
                    result["text"] = msg.get("text", "")
                    result["message_id"] = msg.get("mid", "")
                elif "postback" in event:
                    pb = event["postback"]
                    result["text"] = pb.get("title", "")
                    result["postback"] = pb.get("payload", "")
                return result
    except Exception as e:
        logger.debug("Could not parse Messenger payload: %s", e)
    return None


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

def get_user_profile(user_id: str) -> dict[str, Any]:
    """Fetch a user's public profile (name, profile_pic).

    Requires pages_user_gender, pages_user_locale permissions for extra fields.
    """
    return _get(user_id, {"fields": "first_name,last_name,profile_pic,locale,timezone"})


# ---------------------------------------------------------------------------
# Page info
# ---------------------------------------------------------------------------

def get_page_info() -> dict[str, Any]:
    """Get the connected Facebook Page info."""
    return _get("me", {"fields": "id,name,fan_count,category"})


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test Messenger integration by fetching Page info."""
    try:
        page = get_page_info()
        return {"success": True, "page": page.get("name"), "fans": page.get("fan_count")}
    except Exception as e:
        return {"success": False, "error": str(e)}
