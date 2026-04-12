"""Google Gemini AI integration for ORB — FREE TIER.

Gemini provides 15 RPM / 1M tokens/day free via AI Studio.
Use for: content generation, analysis, summarization when
Anthropic budget is tight.

MODELS:
  gemini-2.0-flash    — fast, free, 1M context window
  gemini-1.5-flash    — legacy fast model
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database.activity_log import log_activity
from config.settings import get_settings

logger = logging.getLogger("orb.gemini")

_DEFAULT_MODEL = "gemini-2.0-flash"


def _get_client() -> Any:
    """Returns a configured Google GenAI client."""
    settings = get_settings()
    api_key = settings.resolve("google_ai_api_key", default="")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_API_KEY is not configured. Set it in Railway Variables "
            "or get a free key at https://aistudio.google.com/apikey"
        )
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
        )


def ask_gemini(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1024,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Send a message to Gemini and return the response.

    Returns dict with: text, model, cost_cents (always 0), provider.
    """
    genai = _get_client()

    try:
        gen_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.4,
            ),
        )

        response = gen_model.generate_content(prompt)
        text = response.text or ""

        logger.info("Gemini call completed — model=%s cost=0¢", model)

        log_activity(
            agent_id=agent_id,
            action_type="gemini",
            description=f"Gemini call using {model}",
            outcome="success",
            cost_cents=0,
        )

        return {
            "text": text,
            "model": model,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_cents": 0,
            "provider": "google",
        }

    except Exception as error:
        logger.error("Gemini API error: %s", error)
        log_activity(
            agent_id=agent_id,
            action_type="gemini",
            description=f"Gemini call using {model}",
            outcome=f"error: {error}",
            cost_cents=0,
        )
        raise


def is_gemini_available() -> bool:
    """Returns True if Google AI API key is configured."""
    settings = get_settings()
    key = settings.resolve("google_ai_api_key", default="")
    return bool(key and len(key) > 10)
