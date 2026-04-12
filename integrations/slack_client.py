"""Slack integration client for ORB Platform.

Allows Commander and agents to:
- Send messages to any channel or DM
- Read recent messages from a channel
- Post structured blocks (cards, alerts)
- Create scheduled messages
- Manage channel topics

Requires: SLACK_BOT_TOKEN (xoxb-...) in Railway env vars.
Free tier: 10,000 messages/month.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("orb.integrations.slack")


def _get_client() -> Any:
    """Build an authenticated Slack Web API client."""
    try:
        from slack_sdk import WebClient
    except ImportError as e:
        raise RuntimeError("slack-sdk not installed. Run: pip install slack-sdk") from e

    from config.settings import get_settings
    settings = get_settings()
    token = settings.resolve("slack_bot_token")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not configured.")
    return WebClient(token=token)


def is_slack_available() -> bool:
    """Check whether Slack is configured."""
    try:
        from config.settings import get_settings
        return get_settings().is_configured("slack_bot_token")
    except Exception:
        return False


def send_message(
    channel: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a plain-text or block-kit message to a channel or user.

    Args:
        channel: Channel name (#general), ID (C...), or user DM (U...).
        text: Fallback plain-text content.
        blocks: Optional Slack Block Kit payload for rich formatting.

    Returns:
        Slack API response dict.
    """
    client = _get_client()
    kwargs: dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        kwargs["blocks"] = blocks

    try:
        response = client.chat_postMessage(**kwargs)
        logger.info("Slack message sent to %s", channel)
        return {"ok": True, "ts": response["ts"], "channel": response["channel"]}
    except Exception as e:
        logger.error("Slack send_message failed: %s", e)
        raise RuntimeError(f"Slack error: {e}") from e


def send_alert(
    channel: str,
    title: str,
    body: str,
    level: str = "info",  # info | warning | danger | success
) -> dict[str, Any]:
    """Send a formatted alert card using Block Kit.

    Args:
        channel: Target channel or user.
        title: Bold title line.
        body: Body text.
        level: Color coding — info (blue), warning (yellow), danger (red), success (green).
    """
    COLOR_MAP = {
        "info": "#2196F3",
        "warning": "#FF9800",
        "danger": "#F44336",
        "success": "#4CAF50",
    }
    color = COLOR_MAP.get(level, "#2196F3")
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{title}*\n{body}"},
        },
        {"type": "divider"},
    ]
    attachments = [{"color": color, "blocks": blocks}]
    client = _get_client()
    try:
        response = client.chat_postMessage(
            channel=channel,
            text=title,
            attachments=attachments,
        )
        return {"ok": True, "ts": response["ts"]}
    except Exception as e:
        logger.error("Slack send_alert failed: %s", e)
        raise RuntimeError(f"Slack error: {e}") from e


def read_channel_messages(
    channel: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read the last N messages from a channel.

    Returns a simplified list: [{user, text, ts}, ...].
    """
    client = _get_client()
    try:
        response = client.conversations_history(channel=channel, limit=limit)
        messages = response.get("messages", [])
        return [
            {
                "user": msg.get("user", "bot"),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", ""),
                "bot": "bot_id" in msg,
            }
            for msg in messages
        ]
    except Exception as e:
        logger.error("Slack read_channel_messages failed: %s", e)
        raise RuntimeError(f"Slack error: {e}") from e


def list_channels() -> list[dict[str, str]]:
    """List all public channels the bot has access to.

    Returns: [{id, name, is_member}, ...]
    """
    client = _get_client()
    try:
        response = client.conversations_list(types="public_channel", limit=200)
        return [
            {
                "id": ch.get("id", ""),
                "name": ch.get("name", ""),
                "is_member": str(ch.get("is_member", False)),
            }
            for ch in response.get("channels", [])
        ]
    except Exception as e:
        logger.error("Slack list_channels failed: %s", e)
        raise RuntimeError(f"Slack error: {e}") from e


def set_channel_topic(channel: str, topic: str) -> bool:
    """Set the topic of a channel."""
    client = _get_client()
    try:
        client.conversations_setTopic(channel=channel, topic=topic)
        return True
    except Exception as e:
        logger.error("Slack set_channel_topic failed: %s", e)
        return False


def send_dm(user_id: str, text: str) -> dict[str, Any]:
    """Send a direct message to a user by their Slack user ID."""
    client = _get_client()
    try:
        # Open DM channel first
        im_response = client.conversations_open(users=[user_id])
        dm_channel = im_response["channel"]["id"]
        return send_message(dm_channel, text)
    except Exception as e:
        logger.error("Slack send_dm failed: %s", e)
        raise RuntimeError(f"Slack error: {e}") from e


def test_connection() -> tuple[bool, str]:
    """Verify bot token by calling auth.test."""
    try:
        client = _get_client()
        response = client.auth_test()
        bot_name = response.get("bot_id", "unknown")
        team = response.get("team", "unknown")
        return True, f"Connected as bot in team '{team}'"
    except Exception as e:
        return False, f"Slack connection failed: {e}"
