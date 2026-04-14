"""Telegram integration for ORB Platform."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx

from app.api.routes.commander import process_mobile_command
from app.database.connection import SupabaseService
from config.settings import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"


def validate_telegram_webhook(data: dict[str, Any], bot_token: str) -> bool:
    """Validate Telegram webhook data."""
    try:
        # Telegram verification: hash(token + data) should match check_hash
        check_hash = data.get("hash", "")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if k != "hash")
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        verify_hash = hashlib.pbkdf2_hmac("sha256", data_check_string.encode(), secret_key, 1)
        
        return int(verify_hash.hex()[::-1], 16) == int(check_hash, 16)
    except Exception:
        return False


def send_telegram_message(chat_id: str | int, text: str) -> bool:
    """Send a Telegram message."""
    settings = get_settings()
    bot_token = settings.resolve("telegram_bot_token", default="").strip()
    if not bot_token:
        logger.warning("Telegram bot token not configured")
        return False

    try:
        url = f"{TELEGRAM_API_URL}/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        
        client = httpx.Client()
        response = client.post(url, json=payload)
        result = response.json()
        
        if result.get("ok"):
            logger.info(f"Telegram message sent to {chat_id}")
            return True
        
        logger.error(f"Telegram API error: {result.get('description')}")
        return False
    except Exception as error:
        logger.exception(f"Failed to send Telegram message: {error}")
        return False


def handle_incoming_telegram_message(chat_id: str | int, user_id: str | int, text: str) -> dict[str, Any] | None:
    """Handle inbound Telegram message and route to Commander if applicable."""
    try:
        db = SupabaseService()
        
        # Find owner by Telegram user_id
        results = db.fetch_all("owners", {"telegram_user_id": str(user_id)})
        if not results:
            logger.warning(f"No owner found for Telegram user {user_id}")
            return None

        owner_id = results[0]["id"]
        
        # Route to Commander if it looks like a command
        if text.upper() in ["YES", "NO", "STATUS", "LEADS", "COST", "STOP", "RESUME", "HELP"]:
            result = process_mobile_command(owner_id=owner_id, command=text.upper())
            
            # Send response back to Telegram
            if result:
                reply_text = result.get("reply", "Command processed")
                send_telegram_message(chat_id=chat_id, text=reply_text)
                return {"handled": True, "command": text.upper()}
        
        logger.info(f"Telegram message from {user_id}: {text[:100]}")
        return {"handled": False, "message_length": len(text)}
    
    except Exception as error:
        logger.exception(f"Error handling Telegram message: {error}")
        return None
