"""Groq AI integration for ORB — FREE TIER.

Groq provides near-instant inference on Llama and Mixtral models.
Free tier: 14,400 requests/day, 6,000 tokens/min.

Use this for: simple decisions, format conversion, data extraction,
health checks — anything where speed > quality and cost must be $0.

MODELS:
  llama-3.3-70b-versatile  — strong general purpose (free)
  llama-3.1-8b-instant     — fastest, cheapest (free)
  mixtral-8x7b-32768       — good at structured output (free)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database.activity_log import log_activity
from config.settings import get_settings

logger = logging.getLogger("orb.groq")

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_FAST_MODEL = "llama-3.1-8b-instant"


def _get_client() -> Any:
    """Returns an authenticated Groq client. Raises RuntimeError if not configured."""
    settings = get_settings()
    api_key = settings.resolve("groq_api_key", default="")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Set it in Railway Variables "
            "or get a free key at https://console.groq.com"
        )
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except ImportError:
        raise RuntimeError(
            "groq package not installed. Run: pip install groq"
        )


def ask_groq(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 512,
    agent_id: str | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Send a message to Groq and return the response.

    Returns dict with: text, model, input_tokens, output_tokens, cost_cents (always 0).
    """
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        text = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "Groq call completed — model=%s in=%d out=%d cost=0¢",
            model, input_tokens, output_tokens,
        )

        log_activity(
            agent_id=agent_id,
            action_type="groq",
            description=f"Groq call using {model}",
            outcome="success",
            cost_cents=0,
        )

        return {
            "text": text,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": 0,
            "provider": "groq",
        }

    except Exception as error:
        logger.error("Groq API error: %s", error)
        log_activity(
            agent_id=agent_id,
            action_type="groq",
            description=f"Groq call using {model}",
            outcome=f"error: {error}",
            cost_cents=0,
        )
        raise


def ask_groq_fast(
    prompt: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 256,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Ultra-fast Groq call using the smallest model. Best for classification and extraction."""
    return ask_groq(
        prompt=prompt,
        system=system,
        model=_FAST_MODEL,
        max_tokens=max_tokens,
        agent_id=agent_id,
        temperature=0.1,
    )


def is_groq_available() -> bool:
    """Returns True if Groq API key is configured."""
    settings = get_settings()
    key = settings.resolve("groq_api_key", default="")
    return bool(key and len(key) > 10)
