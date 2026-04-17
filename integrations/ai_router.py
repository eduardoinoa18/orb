"""AI Router — Unified multi-provider AI dispatch for ORB.

This is the central intelligence layer that selects the best AI model and
provider for any task, so agents never need to hard-code which AI to call.

Routing logic:
  - Image generation      → DALL-E 3 (OpenAI)
  - Voice synthesis       → ElevenLabs
  - Simple/fast tasks     → Claude Haiku  (default cheapest)
  - Writing / research    → Claude Sonnet (balanced)
  - Complex reasoning     → Claude Opus   (most powerful)
  - High-volume / batch   → GPT-4o-mini   (OpenAI cheap alternative)
  - Embeddings / search   → GPT embeddings (when needed)

The router also logs every call so Eduardo can see exactly which providers
cost what across the entire platform, per agent, per day.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger("orb.ai_router")

# Task profile → routing hints
TASK_PROFILES: dict[str, dict[str, Any]] = {
    # ── Text tasks ──────────────────────────────────────────────────────────
    "classify":            {"provider": "claude", "model": "haiku",  "max_tokens": 50},
    "summarize":           {"provider": "claude", "model": "haiku",  "max_tokens": 512},
    "extract":             {"provider": "claude", "model": "haiku",  "max_tokens": 400},
    "boolean_decision":    {"provider": "claude", "model": "haiku",  "max_tokens": 20},
    "short_reply":         {"provider": "claude", "model": "haiku",  "max_tokens": 200},
    "email_draft":         {"provider": "claude", "model": "sonnet", "max_tokens": 600},
    "report":              {"provider": "claude", "model": "sonnet", "max_tokens": 2000},
    "research":            {"provider": "claude", "model": "sonnet", "max_tokens": 2048},
    "coaching":            {"provider": "claude", "model": "sonnet", "max_tokens": 1024},
    "strategy":            {"provider": "claude", "model": "opus",   "max_tokens": 2048},
    "code_review":         {"provider": "claude", "model": "opus",   "max_tokens": 3000},
    "complex_reasoning":   {"provider": "claude", "model": "opus",   "max_tokens": 3000},
    "conversation":        {"provider": "claude", "model": "sonnet", "max_tokens": 1500},
    "platform_admin":      {"provider": "claude", "model": "opus",   "max_tokens": 3000},
    # ── Batch / high volume ──────────────────────────────────────────────────
    "batch_classify":      {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 100},
    "batch_summarize":     {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 400},
    # ── Specialized ─────────────────────────────────────────────────────────
    "image_gen":           {"provider": "openai", "model": "dall-e-3",    "max_tokens": 0},
    "voice_synthesis":     {"provider": "elevenlabs", "model": "eleven_multilingual_v2", "max_tokens": 0},
    "voice_briefing":      {"provider": "elevenlabs", "model": "eleven_multilingual_v2", "max_tokens": 0},
    # ── Agent-specific ──────────────────────────────────────────────────────
    "trade_analysis":      {"provider": "claude", "model": "haiku",  "max_tokens": 512},
    "lead_qualify":        {"provider": "claude", "model": "haiku",  "max_tokens": 400},
    "sales_script":        {"provider": "claude", "model": "sonnet", "max_tokens": 800},
    "content_create":      {"provider": "claude", "model": "sonnet", "max_tokens": 1500},
    "social_post":         {"provider": "claude", "model": "haiku",  "max_tokens": 300},
    "seo_copy":            {"provider": "claude", "model": "sonnet", "max_tokens": 1200},
    "self_review":         {"provider": "claude", "model": "sonnet", "max_tokens": 1500},
    "skill_expand":        {"provider": "claude", "model": "sonnet", "max_tokens": 1000},
    "platform_scan":       {"provider": "claude", "model": "sonnet", "max_tokens": 1500},
    "digest":              {"provider": "claude", "model": "sonnet", "max_tokens": 1500},
}

ProviderType = Literal["claude", "openai", "elevenlabs"]


def route(
    task_type: str,
    prompt: str,
    system: str = "You are a helpful AI assistant for the ORB platform.",
    *,
    owner_id: str | None = None,
    agent_id: str | None = None,
    override_provider: ProviderType | None = None,
    override_model: str | None = None,
    max_tokens: int | None = None,
    # Voice-specific
    voice_id: str | None = None,
    # Image-specific
    image_size: str = "1024x1024",
    image_quality: str = "standard",
) -> dict[str, Any]:
    """Route a task to the best AI provider/model automatically.

    Args:
        task_type: One of the keys in TASK_PROFILES (e.g. "summarize", "image_gen").
                   Unknown task types fall back to "conversation" (Sonnet).
        prompt:    The user prompt or instruction.
        system:    System prompt for text tasks.
        owner_id:  Owner making the request (for cost logging).
        agent_id:  Agent making the request (for cost logging).
        override_provider: Force a specific provider (bypasses routing).
        override_model:    Force a specific model within the provider.
        max_tokens: Override the default max_tokens for the profile.
        voice_id:   ElevenLabs voice ID for voice tasks.
        image_size: DALL-E image size.
        image_quality: DALL-E image quality.

    Returns:
        A unified dict with at minimum:
          text         — the AI response text (empty for image/voice)
          provider     — which provider was used
          model        — which model was used
          cost_cents   — estimated cost
          task_type    — the task type used for routing
          url          — image URL (image tasks only)
          audio_bytes  — raw MP3 bytes (voice tasks only)
    """
    profile = TASK_PROFILES.get(task_type, TASK_PROFILES["conversation"])
    provider: str = override_provider or profile["provider"]
    model: str = override_model or profile["model"]
    effective_max_tokens: int = max_tokens or profile.get("max_tokens", 1024) or 1024

    logger.info(
        "AI Router: task_type=%s provider=%s model=%s owner=%s",
        task_type, provider, model, owner_id or "anon",
    )

    # ── ElevenLabs (voice) ───────────────────────────────────────────────────
    if provider == "elevenlabs":
        return _route_voice(
            text=prompt,
            voice_id=voice_id,
            model_id=model,
            task_type=task_type,
        )

    # ── OpenAI — image generation ────────────────────────────────────────────
    if provider == "openai" and model == "dall-e-3":
        return _route_image(
            prompt=prompt,
            size=image_size,
            quality=image_quality,
        )

    # ── OpenAI — text (GPT-4o-mini) ──────────────────────────────────────────
    if provider == "openai":
        return _route_openai_text(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=effective_max_tokens,
            task_type=task_type,
            agent_id=agent_id,
        )

    # ── Claude (default) ─────────────────────────────────────────────────────
    return _route_claude(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=effective_max_tokens,
        task_type=task_type,
        agent_id=agent_id,
        owner_id=owner_id,
    )


# ── Private routing helpers ───────────────────────────────────────────────────

def _route_claude(
    prompt: str,
    system: str,
    model: str,
    max_tokens: int,
    task_type: str,
    agent_id: str | None,
    owner_id: str | None,
) -> dict[str, Any]:
    """Route to Anthropic Claude."""
    try:
        from integrations.anthropic_client import ask_claude, ask_claude_smart

        model_map = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-6"}
        resolved_model = model_map.get(model, model)

        if model in {"sonnet", "opus"} or resolved_model in {"claude-sonnet-4-6", "claude-opus-4-6"}:
            result = ask_claude_smart(
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                task_type=task_type,
                agent_id=agent_id,
            )
        else:
            result = ask_claude(
                prompt=prompt,
                system=system,
                model=resolved_model,
                max_tokens=max_tokens,
                task_type=task_type,
                agent_id=agent_id,
                owner_id=owner_id,
            )
        return {**result, "provider": "claude", "task_type": task_type}
    except Exception as e:
        logger.error("Claude routing failed for task_type=%s: %s", task_type, e)
        return _error_result("claude", model, task_type, str(e))


def _route_openai_text(
    prompt: str,
    system: str,
    model: str,
    max_tokens: int,
    task_type: str,
    agent_id: str | None,
) -> dict[str, Any]:
    """Route to OpenAI GPT-4o-mini."""
    try:
        from integrations.openai_client import ask_gpt_mini
        result = ask_gpt_mini(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            task_type=task_type,
            agent_id=agent_id,
        )
        return {**result, "provider": "openai", "task_type": task_type}
    except Exception as e:
        logger.warning("OpenAI routing failed (task=%s): %s — falling back to Claude", task_type, e)
        return _route_claude(prompt, system, "haiku", max_tokens, task_type, agent_id, None)


def _route_image(prompt: str, size: str, quality: str) -> dict[str, Any]:
    """Route to DALL-E 3 image generation."""
    try:
        from integrations.openai_client import generate_image
        result = generate_image(prompt=prompt, size=size, quality=quality)
        return {
            "text": f"Image generated: {result.get('url', '')}",
            "url": result.get("url", ""),
            "prompt_used": result.get("prompt_used", prompt),
            "provider": "openai",
            "model": "dall-e-3",
            "cost_cents": 4,  # ~$0.04 standard DALL-E 3
            "task_type": "image_gen",
        }
    except Exception as e:
        logger.error("DALL-E routing failed: %s", e)
        return _error_result("openai", "dall-e-3", "image_gen", str(e))


def _route_voice(
    text: str,
    voice_id: str | None,
    model_id: str,
    task_type: str,
) -> dict[str, Any]:
    """Route to ElevenLabs voice synthesis."""
    try:
        from integrations.elevenlabs_client import (
            DEFAULT_VOICE_ID,
            is_elevenlabs_available,
            text_to_speech,
        )
        if not is_elevenlabs_available():
            raise RuntimeError("ELEVENLABS_API_KEY not configured")
        effective_voice = voice_id or DEFAULT_VOICE_ID
        audio_bytes = text_to_speech(text=text, voice_id=effective_voice, model_id=model_id)
        chars = len(text)
        return {
            "text": "",
            "audio_bytes": audio_bytes,
            "audio_size_bytes": len(audio_bytes),
            "chars_synthesized": chars,
            "provider": "elevenlabs",
            "model": model_id,
            "cost_cents": max(1, chars // 200),  # ~$0.30/1000 chars free tier estimate
            "task_type": task_type,
        }
    except Exception as e:
        logger.error("ElevenLabs routing failed (task=%s): %s", task_type, e)
        return _error_result("elevenlabs", model_id, task_type, str(e))


def _error_result(provider: str, model: str, task_type: str, error: str) -> dict[str, Any]:
    return {
        "text": "",
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "cost_cents": 0,
        "error": error,
        "input_tokens": 0,
        "output_tokens": 0,
    }


# ── Convenience wrappers used by agents ──────────────────────────────────────

def think(
    prompt: str,
    system: str = "You are a helpful AI assistant for the ORB platform.",
    task_type: str = "conversation",
    owner_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Convenience wrapper — routes prompt and returns just the text response.

    Usage:
        answer = ai_router.think("Summarize this lead:", task_type="summarize")
    """
    result = route(task_type=task_type, prompt=prompt, system=system,
                   owner_id=owner_id, agent_id=agent_id)
    return result.get("text", "")


def think_structured(
    prompt: str,
    system: str = "You are a helpful AI assistant for the ORB platform. Always respond with valid JSON.",
    task_type: str = "extract",
    owner_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Routes prompt and attempts to parse the response as JSON.

    Returns the parsed dict, or {"_raw": text, "_parse_error": "..."} if JSON fails.
    """
    import json
    result = route(task_type=task_type, prompt=prompt, system=system,
                   owner_id=owner_id, agent_id=agent_id)
    text = result.get("text", "")
    try:
        # Strip markdown code fences if present
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(clean)
    except Exception as e:
        return {"_raw": text, "_parse_error": str(e)}


def speak(
    text: str,
    voice_id: str | None = None,
    owner_id: str | None = None,
) -> bytes:
    """Route text → ElevenLabs → MP3 bytes. Returns empty bytes if unavailable."""
    result = route(task_type="voice_synthesis", prompt=text, voice_id=voice_id, owner_id=owner_id)
    return result.get("audio_bytes", b"")


def generate_image_url(prompt: str, size: str = "1024x1024") -> str:
    """Route image prompt → DALL-E 3 → image URL."""
    result = route(task_type="image_gen", prompt=prompt, image_size=size)
    return result.get("url", "")


def auto_route(
    prompt: str,
    system: str = "You are a helpful AI assistant for the ORB platform.",
    owner_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Classify the prompt first, then route to the best model automatically.

    This is the most expensive routing option (one extra Haiku call for
    classification) — only use when you genuinely don't know the task type.
    """
    from integrations.anthropic_client import route_task
    task_type_hint = route_task(prompt)
    # Map route_task hints to our task profiles
    mapping = {
        "haiku": "summarize",
        "sonnet": "report",
        "opus": "complex_reasoning",
        "dalle": "image_gen",
    }
    task_type = mapping.get(task_type_hint, "conversation")
    return route(task_type=task_type, prompt=prompt, system=system,
                 owner_id=owner_id, agent_id=agent_id)
