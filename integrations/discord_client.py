"""Discord integration for ORB Platform."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from app.api.routes.commander import process_mobile_command
from app.database.connection import SupabaseService
from config.settings import get_settings

logger = logging.getLogger(__name__)

DISCORD_API_URL = "https://discord.com/api/v10"


def validate_discord_signature(timestamp: str, body: str, signature: str) -> bool:
    """Validate Discord interaction signature (Ed25519)."""
    settings = get_settings()
    public_key = settings.resolve("discord_public_key", default="").strip()
    if not public_key:
        return False

    try:
        import nacl.signing
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(public_key))
        verify_key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
        return True
    except Exception:
        return False


def send_discord_message(channel_id: str, content: str, embeds: list[dict[str, Any]] | None = None) -> bool:
    """Send a Discord message."""
    settings = get_settings()
    bot_token = settings.resolve("discord_bot_token", default="").strip()
    if not bot_token:
        logger.warning("Discord bot token not configured")
        return False

    try:
        headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        client = httpx.Client()
        response = client.post(f"{DISCORD_API_URL}/channels/{channel_id}/messages", json=payload, headers=headers)
        
        if response.status_code in (200, 201):
            logger.info(f"Discord message sent to channel {channel_id}")
            return True
        
        logger.error(f"Discord API error: {response.status_code} - {response.text}")
        return False
    except Exception as error:
        logger.exception(f"Failed to send Discord message: {error}")
        return False


def format_discord_embed(title: str, description: str, color: int = 0x36A64F) -> dict[str, Any]:
    """Return a formatted Discord embed."""
    return {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": None,
    }


def handle_incoming_discord_message(user_id: str, channel_id: str, text: str) -> dict[str, Any] | None:
    """Handle inbound Discord message and route to Commander if applicable."""
    try:
        db = SupabaseService()
        
        # Find owner by Discord user_id
        results = db.fetch_all("owners", {"discord_user_id": user_id})
        if not results:
            logger.warning(f"No owner found for Discord user {user_id}")
            return None

        owner_id = results[0]["id"]
        
        # Route to Commander if it looks like a command
        if text.upper() in ["YES", "NO", "STATUS", "LEADS", "COST", "STOP", "RESUME", "HELP"]:
            result = process_mobile_command(owner_id=owner_id, command=text.upper())
            
            # Send response back to Discord
            if result:
                reply_text = result.get("reply", "Command processed")
                send_discord_message(channel_id=channel_id, content=reply_text)
                return {"handled": True, "command": text.upper()}
        
        logger.info(f"Discord message from {user_id}: {text[:100]}")
        return {"handled": False, "message_length": len(text)}
    
    except Exception as error:
        logger.exception(f"Error handling Discord message: {error}")
        return None
