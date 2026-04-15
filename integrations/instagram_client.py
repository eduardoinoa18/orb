"""Instagram Graph API client for ORB Platform.

Handles inbound DMs / story mentions / comment replies and lets agents
send messages back through the Instagram Messaging API.

Also provides tools for:
  - Publishing media (photo/reel/carousel)
  - Reading comments and replying
  - Fetching account insights

Requires:
  INSTAGRAM_ACCESS_TOKEN  — long-lived User or Page access token
  INSTAGRAM_BUSINESS_ID   — Instagram Business Account ID (numeric string)

Docs: https://developers.facebook.com/docs/instagram-api
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.instagram")

GRAPH_URL = "https://graph.facebook.com/v18.0"


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_instagram_available() -> bool:
    s = get_settings()
    return bool(
        s.resolve("instagram_access_token", default="")
        and s.resolve("instagram_business_id", default="")
    )


def _token() -> str:
    return get_settings().resolve("instagram_access_token", default="")


def _biz_id() -> str:
    return get_settings().resolve("instagram_business_id", default="")


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    p = params or {}
    p["access_token"] = _token()
    qs = urllib.parse.urlencode(p)
    url = f"{GRAPH_URL}/{path}?{qs}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    body["access_token"] = _token()
    url = f"{GRAPH_URL}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Messaging (DMs)
# ---------------------------------------------------------------------------

def send_dm(recipient_id: str, text: str) -> dict[str, Any]:
    """Send a direct message to an Instagram user.

    Args:
        recipient_id: Instagram-scoped user ID (from an inbound webhook).
        text: Message text (max 1,000 chars).

    Returns: API response with 'message_id'.
    """
    return _post(f"{_biz_id()}/messages", {
        "recipient": {"id": recipient_id},
        "message": {"text": text[:1000]},
        "messaging_type": "RESPONSE",
    })


def send_dm_template(recipient_id: str, text: str, buttons: list[str]) -> dict[str, Any]:
    """Send a DM with quick-reply buttons (max 3 buttons, 20 chars each).

    Args:
        recipient_id: Instagram-scoped user ID.
        text: Message body.
        buttons: Button labels (max 3).
    """
    quick_replies = [{"content_type": "text", "title": b[:20], "payload": b} for b in buttons[:3]]
    return _post(f"{_biz_id()}/messages", {
        "recipient": {"id": recipient_id},
        "message": {"text": text[:1000], "quick_replies": quick_replies},
        "messaging_type": "RESPONSE",
    })


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def get_media_comments(media_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get comments on a media post.

    Returns list of {id, text, username, timestamp}.
    """
    resp = _get(f"{media_id}/comments", {
        "fields": "id,text,username,timestamp",
        "limit": limit,
    })
    return resp.get("data", [])


def reply_to_comment(comment_id: str, text: str) -> dict[str, Any]:
    """Post a reply to a comment.

    Args:
        comment_id: Comment ID from get_media_comments().
        text: Reply text.
    """
    return _post(f"{comment_id}/replies", {"message": text[:1000]})


def hide_comment(comment_id: str) -> bool:
    """Hide a comment (sets hidden=true).

    Returns True on success.
    """
    try:
        data = json.dumps({"hide": True, "access_token": _token()}).encode()
        url = f"{GRAPH_URL}/{comment_id}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("success", False)
    except Exception as e:
        logger.warning("Failed to hide comment: %s", e)
        return False


# ---------------------------------------------------------------------------
# Media publishing
# ---------------------------------------------------------------------------

def publish_photo(image_url: str, caption: str) -> dict[str, Any]:
    """Publish a photo post to the Instagram Business account.

    Args:
        image_url: Publicly accessible URL of the image.
        caption: Post caption (supports hashtags).

    Returns: dict with 'id' of the published media.
    """
    # Step 1: Create media container
    container = _post(f"{_biz_id()}/media", {
        "image_url": image_url,
        "caption": caption[:2200],
    })
    container_id = container["id"]

    # Step 2: Publish the container
    return _post(f"{_biz_id()}/media_publish", {"creation_id": container_id})


def get_recent_media(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent media posts from the business account.

    Returns list of {id, caption, media_type, timestamp, permalink}.
    """
    resp = _get(f"{_biz_id()}/media", {
        "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count",
        "limit": limit,
    })
    return resp.get("data", [])


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def get_account_insights(metric: str = "reach", period: str = "day") -> list[dict[str, Any]]:
    """Get account-level insights.

    Args:
        metric: One of: reach, impressions, profile_views, follower_count, website_clicks
        period: 'day' | 'week' | 'month' | 'lifetime'
    """
    resp = _get(f"{_biz_id()}/insights", {
        "metric": metric,
        "period": period,
    })
    return resp.get("data", [])


def get_profile(fields: str = "id,name,username,followers_count,media_count") -> dict[str, Any]:
    """Get the business account profile."""
    return _get(_biz_id(), {"fields": fields})


# ---------------------------------------------------------------------------
# Inbound webhook parsing
# ---------------------------------------------------------------------------

def parse_inbound_message(payload: dict) -> dict[str, Any] | None:
    """Parse an Instagram webhook payload into a normalized message dict.

    Returns: {sender_id, text, message_id, timestamp} or None if not a DM.
    """
    try:
        for entry in payload.get("entry", []):
            for msg in entry.get("messaging", []):
                message = msg.get("message", {})
                if not message:
                    continue
                return {
                    "sender_id": msg["sender"]["id"],
                    "recipient_id": msg["recipient"]["id"],
                    "text": message.get("text", ""),
                    "message_id": message.get("mid", ""),
                    "timestamp": msg.get("timestamp", 0),
                    "attachments": message.get("attachments", []),
                }
    except Exception as e:
        logger.debug("Could not parse Instagram payload: %s", e)
    return None


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test the Instagram integration by fetching the account profile."""
    try:
        profile = get_profile()
        return {
            "success": True,
            "username": profile.get("username"),
            "followers": profile.get("followers_count"),
            "media_count": profile.get("media_count"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
