"""Twilio integration for ORB — SMS and phone calls.

All SMS messages and calls from ORB agents go through this module.
Every outgoing message and call is logged to the activity_log table so
you can see exactly what your agents are doing and what it costs.

PRICING NOTES (Twilio as of 2025):
  Outbound SMS to US: ~$0.0079 per message = 1 cent per message
  Outbound call to US: ~$0.014 per minute
"""

import logging
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.database.activity_log import log_activity
from config.settings import get_settings

logger = logging.getLogger("orb.twilio")

# Cost estimates in cents — used for activity_log cost tracking
_SMS_COST_CENTS = 1      # ~$0.0079 per message, round up to 1 cent
_CALL_COST_PER_MIN_CENTS = 2  # ~$0.014 per minute


def _get_client() -> Client:
    """Returns an authenticated Twilio client.

    Called at request time so the app starts without the credentials — you
    only get an error when you actually try to send a message or make a call.
    """
    settings = get_settings()
    account_sid = settings.require("twilio_account_sid")
    auth_token = settings.require("twilio_auth_token")
    return Client(account_sid, auth_token)


# Public alias used by modules that need the raw client (e.g. whatsapp_commander).
get_twilio_client = _get_client


def send_sms(
    to: str,
    message: str,
    from_number: str | None = None,
) -> dict[str, Any]:
    """
    Sends an SMS message from one of your Twilio numbers.

    Args:
        to:           The recipient's phone number in E.164 format, e.g. +12125551234
        message:      The text content of the SMS (max 1600 characters)
        from_number:  Optional — which Twilio number to send from.
                      Defaults to the TWILIO_PHONE_NUMBER in your .env file.

    Returns a dict with: sid, status, to, from_number, body
    Raises RuntimeError if credentials are not configured.
    Raises TwilioRestException if the API call fails.
    """
    settings = get_settings()
    sender = from_number or settings.require("twilio_phone_number")
    client = _get_client()

    try:
        msg = client.messages.create(body=message, from_=sender, to=to)
        logger.info(
            "SMS sent — sid=%s to=%s status=%s cost=%d¢",
            msg.sid, to, msg.status, _SMS_COST_CENTS,
        )
        log_activity(
            agent_id=None,
            action_type="sms",
            description=f"Sent SMS to {to}",
            outcome=msg.status,
            cost_cents=_SMS_COST_CENTS,
        )
        return {
            "sid": msg.sid,
            "status": msg.status,
            "to": to,
            "from_number": sender,
            "body": message,
            "cost_cents": _SMS_COST_CENTS,
        }
    except TwilioRestException as error:
        logger.error("Twilio SMS error to=%s: %s", to, error)
        log_activity(
            agent_id=None,
            action_type="sms",
            description=f"Failed SMS to {to}",
            outcome=str(error),
            cost_cents=0,
        )
        raise


def make_call(
    to: str,
    script: str,
    from_number: str | None = None,
) -> dict[str, Any]:
    """
    Places a phone call that reads out a script using text-to-speech.

    This is a simple TwiML-based call — good for quick alerts and notifications.
    For AI-powered conversational calls, use bland_ai_client.make_ai_call() instead.

    Args:
        to:           The phone number to call in E.164 format
        script:       The words that Twilio will speak when the call connects
        from_number:  Optional — which Twilio number to call from

    Returns a dict with: sid, status, to, from_number
    """
    settings = get_settings()
    sender = from_number or settings.require("twilio_phone_number")
    client = _get_client()

    # TwiML: Twilio's XML format for controlling what a call does
    # <Say> reads text aloud, <Pause> adds a moment of silence
    twiml = f"<Response><Say voice='Polly.Matthew'>{script}</Say><Pause length='1'/></Response>"

    try:
        call = client.calls.create(
            twiml=twiml,
            from_=sender,
            to=to,
        )
        logger.info("Call placed — sid=%s to=%s status=%s", call.sid, to, call.status)
        log_activity(
            agent_id=None,
            action_type="call",
            description=f"Placed Twilio call to {to}",
            outcome=call.status,
            cost_cents=_CALL_COST_PER_MIN_CENTS,
        )
        return {
            "sid": call.sid,
            "status": call.status,
            "to": to,
            "from_number": sender,
        }
    except TwilioRestException as error:
        logger.error("Twilio call error to=%s: %s", to, error)
        log_activity(
            agent_id=None,
            action_type="call",
            description=f"Failed Twilio call to {to}",
            outcome=str(error),
            cost_cents=0,
        )
        raise


def get_messages(phone_number: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Retrieves recent SMS messages sent to or from a specific phone number.

    Useful for checking what an agent has been saying and for debugging
    conversation flows in the wholesale lead sequences.

    Args:
        phone_number:  The E.164 phone number to filter messages for
        limit:         Maximum number of messages to return (default 20)

    Returns a list of message dicts, newest first.
    """
    client = _get_client()
    try:
        messages = client.messages.list(to=phone_number, limit=limit)
        result = []
        for msg in messages:
            result.append({
                "sid": msg.sid,
                "from": msg.from_,
                "to": msg.to,
                "body": msg.body,
                "status": msg.status,
                "direction": msg.direction,
                "date_sent": str(msg.date_sent),
            })
        logger.info("Retrieved %d messages for %s", len(result), phone_number)
        return result
    except TwilioRestException as error:
        logger.error("Twilio get_messages error: %s", error)
        raise

