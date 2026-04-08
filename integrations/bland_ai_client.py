"""Bland AI integration for ORB — AI-powered voice calls.

Bland AI places fully autonomous phone calls using a natural-sounding AI voice.
Unlike Twilio (which just reads a script), Bland AI can have a real conversation:
it handles unexpected answers, asks follow-up questions, and builds a transcript.

This is used by the wholesale agent to call leads for initial qualification.

PRICING NOTE: Bland AI charges per minute of call time (roughly $0.09/min).
The activity_log stores estimated cost so you can track spend across all agents.
"""

import logging
from typing import Any

import httpx

from config.settings import get_settings

logger = logging.getLogger("orb.bland_ai")

BLAND_AI_BASE_URL = "https://api.bland.ai/v1"
_COST_PER_MINUTE_CENTS = 9  # ~$0.09/min, stored in cents


def _get_headers() -> dict[str, str]:
    """Returns authenticated request headers for Bland AI.

    Called at request time so the app can start without the key — you only
    get an error when you actually try to make a call.
    """
    settings = get_settings()
    api_key = settings.require("bland_ai_api_key")
    return {
        "authorization": api_key,
        "Content-Type": "application/json",
    }


def make_ai_call(
    to_number: str,
    task: str,
    voice_id: str = "mason",
    max_duration_minutes: int = 10,
    first_sentence: str | None = None,
    wait_for_greeting: bool = True,
) -> dict[str, Any]:
    """
    Places an AI-powered phone call using Bland AI.

    The AI will have a natural conversation based on the task description.
    Unlike a scripted call, it can respond to unexpected answers and ask
    follow-up questions.

    Args:
        to_number:            Phone number to call in E.164 format (+12125551234)
        task:                 Plain-English description of what the AI should do.
                              Example: "You are Jake calling about the property at
                              123 Main St. Ask the owner if they would consider selling."
        voice_id:             Bland AI voice name to use (default: "mason" — male, US)
        max_duration_minutes: Hard cap on call length to control costs
        first_sentence:       Optional — exact first sentence the AI will say
        wait_for_greeting:    Whether to wait for "Hello?" before speaking

    Returns a dict with: call_id, status, to_number, estimated_cost_cents
    Raises RuntimeError if BLAND_AI_API_KEY is not set.
    Raises httpx.HTTPStatusError if the API call fails.
    """
    headers = _get_headers()

    payload: dict[str, Any] = {
        "phone_number": to_number,
        "task": task,
        "voice": voice_id,
        "max_duration": max_duration_minutes,
        "wait_for_greeting": wait_for_greeting,
        "record": True,       # Always record so you can review calls
        "answered_by_enabled": True,  # Detect voicemail vs live answer
    }

    if first_sentence:
        payload["first_sentence"] = first_sentence

    try:
        with httpx.Client(timeout=30) as http:
            response = http.post(
                f"{BLAND_AI_BASE_URL}/calls",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        call_id = data.get("call_id", "")
        estimated_cost = max_duration_minutes * _COST_PER_MINUTE_CENTS

        logger.info(
            "Bland AI call placed — call_id=%s to=%s estimated_cost=%d¢",
            call_id, to_number, estimated_cost,
        )

        return {
            "call_id": call_id,
            "status": data.get("status", "queued"),
            "to_number": to_number,
            "estimated_cost_cents": estimated_cost,
        }
    except httpx.HTTPStatusError as error:
        logger.error(
            "Bland AI call failed to=%s status=%d body=%s",
            to_number, error.response.status_code, error.response.text,
        )
        raise


def get_call_transcript(call_id: str) -> dict[str, Any]:
    """
    Retrieves the transcript and metadata for a completed Bland AI call.

    Call this after receiving a Bland AI webhook notification that a call
    has ended. The transcript is then passed to Claude for qualification
    analysis (wholesale agent, Level 4).

    Args:
        call_id: The call ID returned by make_ai_call()

    Returns a dict with: call_id, status, transcript, duration_seconds,
    recording_url, answered_by ("human" or "voicemail")
    """
    headers = _get_headers()

    try:
        with httpx.Client(timeout=30) as http:
            response = http.get(
                f"{BLAND_AI_BASE_URL}/calls/{call_id}",
                headers=headers,
            )
            response.raise_for_status()

        data = response.json()
        transcript_parts: list[str] = []
        for entry in data.get("transcripts", []):
            speaker = "Agent" if entry.get("user") == "assistant" else "Lead"
            transcript_parts.append(f"{speaker}: {entry.get('text', '')}")

        transcript_text = "\n".join(transcript_parts)

        logger.info(
            "Bland AI transcript retrieved — call_id=%s duration=%s",
            call_id, data.get("call_length"),
        )

        return {
            "call_id": call_id,
            "status": data.get("status", "unknown"),
            "transcript": transcript_text,
            "duration_seconds": data.get("call_length", 0),
            "recording_url": data.get("recording_url", ""),
            "answered_by": data.get("answered_by", "unknown"),
        }
    except httpx.HTTPStatusError as error:
        logger.error(
            "Bland AI transcript fetch failed call_id=%s status=%d body=%s",
            call_id, error.response.status_code, error.response.text,
        )
        raise

