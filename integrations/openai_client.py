"""OpenAI integration for ORB.

OpenAI is used as a secondary AI provider for two specific tasks:
  1. Cheap text tasks (gpt-4o-mini) when Claude would be overkill
  2. Image generation (DALL-E 3) for the marketing agent

For most reasoning and text tasks, prefer the Anthropic client instead —
Claude Haiku is generally better value than gpt-4o-mini for our use case.
"""

import logging
from typing import Any

import openai as openai_lib

from app.database.activity_log import log_activity
from config.settings import get_settings
from integrations.token_optimizer import OptimizationResult, TokenOptimizer

logger = logging.getLogger("orb.openai")


def _get_client() -> openai_lib.OpenAI:
    """Returns an authenticated OpenAI client.

    Called at request time so the app can start without the key — you only
    get an error when you actually try to use this function.
    """
    settings = get_settings()
    api_key = settings.require("openai_api_key")
    return openai_lib.OpenAI(api_key=api_key)


def ask_gpt_mini(
    prompt: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    task_type: str = "short_analysis",
    max_budget_cents: int = 3,
    agent_id: str | None = None,
    is_critical: bool = False,
) -> dict[str, Any]:
    """
    Sends a message to gpt-4o-mini — a fast, cheap OpenAI model.

    Use this for simple tasks where you specifically need OpenAI's behaviour,
    or for high-volume tasks where cost per call matters. Returns a dict with
    the text response and token usage.

    Returns dict with: text, model, input_tokens, output_tokens
    """
    optimizer: TokenOptimizer | None = None
    try:
        optimizer = TokenOptimizer()
        optimization = optimizer.optimize_prompt(
            prompt=prompt,
            task_type=task_type,
            max_budget_cents=max_budget_cents,
            agent_id=agent_id,
            is_critical=is_critical,
        )
    except Exception:
        optimization = OptimizationResult(
            optimized_prompt=prompt,
            selected_model="haiku",
            max_tokens=max_tokens,
            used_cache=False,
            cache_key="unavailable",
            needs_ai=True,
            bypass_reason="optimizer_unavailable",
            cached_result=None,
            budget_mode="normal",
            should_defer=False,
            daily_budget_cents=0,
            spent_today_cents=0,
            remaining_budget_cents=0,
        )

    if not optimization.needs_ai:
        text = optimization.cached_result or optimization.optimized_prompt
        model = "cache" if optimization.cached_result else ("deferred" if optimization.should_defer else "none")
        return {
            "text": text,
            "model": model,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_cents": 0,
            "optimization": {
                "budget_mode": optimization.budget_mode,
                "bypass_reason": optimization.bypass_reason,
                "remaining_budget_cents": optimization.remaining_budget_cents,
                "should_defer": optimization.should_defer,
            },
        }

    client = _get_client()
    resolved_max_tokens = min(max_tokens, optimization.max_tokens) if optimization.max_tokens > 0 else max_tokens
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=resolved_max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": optimization.optimized_prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost_cents = max(1, round(((input_tokens * 15) + (output_tokens * 60)) / 1_000_000))

        if optimizer is not None and optimization.cache_key != "unavailable":
            try:
                optimizer.save_cached_result(optimization.cache_key, text, agent_id=agent_id)
            except Exception:
                logger.warning("Failed to persist token optimizer cache entry")

        log_activity(
            agent_id=agent_id,
            action_type="openai",
            description="OpenAI call using gpt-4o-mini",
            outcome="success",
            cost_cents=cost_cents,
        )

        logger.info(
            "GPT-mini call completed — in=%d out=%d", input_tokens, output_tokens
        )

        return {
            "text": text,
            "model": "gpt-4o-mini",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": cost_cents,
            "optimization": {
                "max_tokens": resolved_max_tokens,
                "budget_mode": optimization.budget_mode,
                "remaining_budget_cents": optimization.remaining_budget_cents,
            },
        }
    except openai_lib.APIError as error:
        logger.error("OpenAI API error: %s", error)
        log_activity(
            agent_id=agent_id,
            action_type="openai",
            description="OpenAI call using gpt-4o-mini",
            outcome=f"error: {error}",
            cost_cents=0,
        )
        raise


def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
) -> dict[str, Any]:
    """
    Generates an image using DALL-E 3.

    Used by the marketing agent to create property photos, social media
    graphics, or anything else that needs AI-generated visuals.

    Returns dict with: url (the image URL, valid for ~1 hour), prompt_used
    """
    client = _get_client()
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,        # type: ignore[arg-type]
            quality=quality,  # type: ignore[arg-type]
            n=1,
        )
        image_url = response.data[0].url or ""
        revised_prompt = response.data[0].revised_prompt or prompt

        logger.info("DALL-E 3 image generated — size=%s quality=%s", size, quality)

        return {
            "url": image_url,
            "prompt_used": revised_prompt,
            "size": size,
        }
    except openai_lib.APIError as error:
        logger.error("OpenAI image generation error: %s", error)
        raise

