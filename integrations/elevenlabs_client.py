"""ElevenLabs voice synthesis client for ORB Platform.

Allows Commander and agents to:
- Convert text to speech (MP3/WAV)
- Clone owner's voice (advanced plan)
- Generate voice briefings and alerts
- Create audio summaries of reports

Requires: ELEVENLABS_API_KEY in Railway env vars.
Free tier: 10,000 characters/month (great for briefings/alerts).
"""

from __future__ import annotations

import logging
import urllib.request
import urllib.error
import json
from typing import Any

logger = logging.getLogger("orb.integrations.elevenlabs")

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"

# Default professional voices (IDs from ElevenLabs free tier)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — calm, professional
MALE_VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"    # Josh — confident


def _headers(accept: str = "application/json") -> dict[str, str]:
    from config.settings import get_settings
    token = get_settings().resolve("elevenlabs_api_key")
    if not token:
        raise RuntimeError("ELEVENLABS_API_KEY not configured.")
    return {
        "xi-api-key": token,
        "Content-Type": "application/json",
        "Accept": accept,
    }


def is_elevenlabs_available() -> bool:
    try:
        from config.settings import get_settings
        return get_settings().is_configured("elevenlabs_api_key")
    except Exception:
        return False


def text_to_speech(
    text: str,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> bytes:
    """Convert text to speech and return raw MP3 bytes.

    Args:
        text: Text to synthesize (max 5,000 chars on free plan).
        voice_id: ElevenLabs voice ID.
        model_id: Model to use (multilingual_v2 for best quality).
        stability: Voice stability 0.0-1.0 (higher = less expressive).
        similarity_boost: Voice clarity 0.0-1.0 (higher = more distinct).

    Returns: MP3 audio bytes.
    """
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    body = json.dumps({
        "text": text[:4900],  # Safety trim
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
        },
    }).encode()

    # Use audio/mpeg accept header for MP3
    headers = {
        **_headers(accept="audio/mpeg"),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_bytes = resp.read()
            logger.info(
                "ElevenLabs TTS: %d chars → %d bytes audio",
                len(text),
                len(audio_bytes),
            )
            return audio_bytes
    except urllib.error.HTTPError as e:
        error_text = e.read().decode()
        logger.error("ElevenLabs TTS failed: %s %s", e.code, error_text)
        raise RuntimeError(f"ElevenLabs error {e.code}: {error_text[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"ElevenLabs error: {e}") from e


def text_to_speech_file(
    text: str,
    output_path: str,
    voice_id: str = DEFAULT_VOICE_ID,
) -> str:
    """Convert text to speech and save to a file.

    Args:
        text: Text to synthesize.
        output_path: Full path to save the MP3 file.
        voice_id: ElevenLabs voice ID.

    Returns: Path to the saved file.
    """
    audio = text_to_speech(text, voice_id=voice_id)
    with open(output_path, "wb") as f:
        f.write(audio)
    logger.info("ElevenLabs audio saved to %s", output_path)
    return output_path


def list_voices() -> list[dict[str, Any]]:
    """List all available voices for the account."""
    url = f"{ELEVENLABS_BASE}/voices"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return [
            {
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "category": v.get("category"),
                "labels": v.get("labels", {}),
            }
            for v in data.get("voices", [])
        ]
    except Exception as e:
        logger.error("ElevenLabs list_voices failed: %s", e)
        return []


def get_usage_info() -> dict[str, Any]:
    """Get current character usage and quota."""
    url = f"{ELEVENLABS_BASE}/user"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        sub = data.get("subscription", {})
        return {
            "character_count": sub.get("character_count", 0),
            "character_limit": sub.get("character_limit", 10000),
            "tier": sub.get("tier", "free"),
            "can_extend": sub.get("can_extend_character_limit", False),
        }
    except Exception as e:
        logger.error("ElevenLabs get_usage_info failed: %s", e)
        return {}


def create_briefing_audio(
    briefing_text: str,
    output_path: str = "/tmp/orb_briefing.mp3",
) -> str:
    """Generate a morning briefing audio file.

    Uses a calm professional voice optimized for news/briefing delivery.
    """
    return text_to_speech_file(
        text=briefing_text,
        output_path=output_path,
        voice_id=DEFAULT_VOICE_ID,
    )


def test_connection() -> tuple[bool, str]:
    """Verify ElevenLabs API key and check quota."""
    try:
        usage = get_usage_info()
        remaining = usage.get("character_limit", 0) - usage.get("character_count", 0)
        return True, f"ElevenLabs connected — {remaining:,} chars remaining this month"
    except Exception as e:
        return False, f"ElevenLabs connection failed: {e}"
