"""Telegram integration for ORB Platform.

Uses the Bot API webhook model:
  - Telegram POSTs updates to /webhooks/telegram/updates
  - Optionally validated via X-Telegram-Bot-Api-Secret-Token header
    (set when registering the webhook via setWebhook API)
  - Outbound messages sent via Bot API sendMessage endpoint

Note on validation: The login widget hash method (SHA-256 of sorted fields)
is for Telegram Login Widget only. Bot API webhooks should be secured using
the secret_token parameter of setWebhook, which Telegram sends back in the
X-Telegram-Bot-Api-Secret-Token header.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.database.connection import SupabaseService
from config.settings import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"


# ── Webhook validation ────────────────────────────────────────────────────────

def validate_telegram_webhook(
    secret_token_header: str | None,
    bot_token: str,
) -> bool:
    """Validate a Bot API webhook using the X-Telegram-Bot-Api-Secret-Token header.

    When you call setWebhook with a secret_token, Telegram will include that
    token verbatim in the X-Telegram-Bot-Api-Secret-Token header on every update.

    If no secret_token was configured (header is None or empty), we allow the
    request through but log a warning — this is valid for dev environments.
    """
    if not secret_token_header:
        logger.warning("Telegram webhook received without secret token header — consider configuring TELEGRAM_WEBHOOK_SECRET")
        return True  # Permissive fallback; tighten in production

    # Retrieve the expected secret from settings
    settings = get_settings()
    expected_secret = settings.resolve("telegram_webhook_secret", default="").strip()

    if not expected_secret:
        # No secret configured — we can't validate, allow through
        logger.warning("TELEGRAM_WEBHOOK_SECRET not set; skipping Telegram webhook validation")
        return True

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(secret_token_header, expected_secret)


def validate_telegram_login_widget(data: dict[str, Any], bot_token: str) -> bool:
    """Validate data from the Telegram Login Widget (separate from Bot API webhooks).

    Uses the SHA-256 hash of the bot token as the HMAC-SHA256 key over
    the sorted data-check-string.
    """
    try:
        check_hash = data.get("hash", "")
        if not check_hash:
            return False
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, check_hash)
    except Exception:
        return False


# ── Register webhook with Telegram ────────────────────────────────────────────

def register_webhook(webhook_url: str, secret_token: str | None = None) -> bool:
    """Register (or update) the bot webhook URL with Telegram.

    Call this once after deployment to point Telegram at your endpoint.
    """
    settings = get_settings()
    bot_token = settings.resolve("telegram_bot_token", default="").strip()
    if not bot_token:
        logger.error("Cannot register Telegram webhook: TELEGRAM_BOT_TOKEN not set")
        return False

    payload: dict[str, Any] = {"url": webhook_url}
    if secret_token:
        payload["secret_token"] = secret_token

    try:
        url = f"{TELEGRAM_API_URL}/bot{bot_token}/setWebhook"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            result = resp.json()
            if result.get("ok"):
                logger.info("Telegram webhook registered: %s", webhook_url)
                return True
            logger.error("Telegram setWebhook failed: %s", result.get("description"))
            return False
    except Exception as e:
        logger.exception("Failed to register Telegram webhook: %s", e)
        return False


# ── Outbound messaging ────────────────────────────────────────────────────────

def send_telegram_message(chat_id: str | int, text: str, parse_mode: str = "Markdown") -> bool:
    """Send a text message to a Telegram chat."""
    settings = get_settings()
    bot_token = settings.resolve("telegram_bot_token", default="").strip()
    if not bot_token:
        logger.warning("Telegram bot token not configured")
        return False

    try:
        url = f"{TELEGRAM_API_URL}/bot{bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],  # Telegram message limit
            "parse_mode": parse_mode,
        }
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
            result = response.json()
            if result.get("ok"):
                logger.info("Telegram message sent to %s", chat_id)
                return True
            logger.error("Telegram API error: %s", result.get("description"))
            return False
    except Exception as error:
        logger.exception("Failed to send Telegram message: %s", error)
        return False


def send_telegram_photo(chat_id: str | int, photo_url: str, caption: str = "") -> bool:
    """Send a photo to a Telegram chat."""
    settings = get_settings()
    bot_token = settings.resolve("telegram_bot_token", default="").strip()
    if not bot_token:
        return False
    try:
        url = f"{TELEGRAM_API_URL}/bot{bot_token}/sendPhoto"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json={"chat_id": chat_id, "photo": photo_url, "caption": caption})
            return resp.json().get("ok", False)
    except Exception:
        return False


def is_telegram_available() -> bool:
    """Check if Telegram integration is configured."""
    try:
        settings = get_settings()
        token = settings.resolve("telegram_bot_token", default="").strip()
        return bool(token)
    except Exception:
        return False


# ── Inbound message handler ────────────────────────────────────────────────────

def handle_incoming_telegram_message(
    chat_id: str | int,
    user_id: str | int,
    text: str,
    username: str = "",
) -> dict[str, Any] | None:
    """Handle inbound Telegram message and route to Commander."""
    try:
        db = SupabaseService()

        # Check channel_mappings first (preferred — supports multiple owners)
        mappings = db.fetch_all("channel_mappings", {
            "platform": "telegram",
            "external_id": str(user_id),
        })

        if mappings:
            owner_id = mappings[0]["owner_id"]
        else:
            # Fallback: check owner profiles with telegram_user_id
            results = db.fetch_all("owner_profiles", {"telegram_user_id": str(user_id)})
            if not results:
                logger.info("No owner mapped for Telegram user %s", user_id)
                # Optionally send a help message
                send_telegram_message(
                    chat_id=chat_id,
                    text="👋 Hello! To connect your ORB account, visit your dashboard → Connect → Telegram.",
                )
                return {"handled": False, "reason": "no_owner_mapping"}
            owner_id = results[0]["owner_id"]

        # Route through Commander
        from app.api.routes.commander import process_owner_channel_message
        result = process_owner_channel_message(owner_id=owner_id, message_body=text)

        if result and result.get("message"):
            reply = str(result["message"])[:4096]
            send_telegram_message(chat_id=chat_id, text=reply)
            return {"handled": True, "owner_id": owner_id}

        return {"handled": False, "reason": "no_commander_response"}

    except Exception as error:
        logger.exception("Error handling Telegram message: %s", error)
        return None
