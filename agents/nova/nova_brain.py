"""Nova's core text-generation brain helpers."""

from __future__ import annotations

from typing import Any

from agents.self_improvement import AgentSelfImprovement
from integrations.anthropic_client import ask_claude, ask_claude_smart


def _fallback_copy(platform: str, prompt: str) -> str:
    """Local fallback copy so Nova still works when AI keys are missing."""
    prefix = {
        "instagram": "New post:",
        "facebook": "Update:",
        "linkedin": "Professional update:",
        "email": "Subject: Market update",
    }.get(platform, "Post:")
    trimmed = prompt.strip().replace("\n", " ")
    return f"{prefix} {trimmed[:220]}"


def compose_caption(
    prompt: str,
    platform: str,
    tone: str = "professional and modern",
    long_form: bool = False,
) -> dict[str, Any]:
    """Creates a caption tailored for a platform, with graceful fallback."""
    system = (
        "You are Nova, a real-estate marketing assistant. "
        "Write clear, human, non-spammy copy with a natural call-to-action."
    )
    user_prompt = (
        f"Platform: {platform}\n"
        f"Tone: {tone}\n"
        f"Length: {'long' if long_form else 'short'}\n"
        f"Task: {prompt}\n"
        "Return only the final copy text."
    )

    try:
        result = ask_claude_smart(user_prompt, system=system, max_tokens=600 if long_form else 260)
        return {
            "text": result["text"].strip(),
            "model": result["model"],
            "cost_cents": result["cost_cents"],
        }
    except Exception:
        return {
            "text": _fallback_copy(platform, prompt),
            "model": "fallback-template",
            "cost_cents": 0,
        }


def create_newsletter_blurb(prompt: str) -> dict[str, Any]:
    """Creates a concise email/newsletter paragraph for market updates."""
    system = "You write concise real-estate newsletter blurbs with one CTA."
    try:
        result = ask_claude(
            prompt=f"Write a short newsletter section (max 120 words): {prompt}",
            system=system,
            max_tokens=220,
        )
        return {
            "text": result["text"].strip(),
            "model": result["model"],
            "cost_cents": result["cost_cents"],
        }
    except Exception:
        return {
            "text": f"Market update: {prompt[:180]}",
            "model": "fallback-template",
            "cost_cents": 0,
        }


class NovaBrain(AgentSelfImprovement):
    """Nova addendum facade for self-improvement endpoints."""

    agent_slug = "nova"

    def learn_from_outcomes(self, owner_id: str) -> dict[str, Any]:
        """Runs weekly Nova review and returns a normalized update summary."""
        result = super().learn_from_outcomes(agent_id=owner_id, lookback_days=7)
        return {
            "status": "updated",
            "owner_id": owner_id,
            "improvements_made": result.get("improvements_made", 0),
            "plan": result.get("plan", {}),
        }

    def identify_owner_needs(self, owner_id: str) -> dict[str, Any]:
        """Provides proactive owner suggestions from recent Nova patterns."""
        return super().identify_owner_needs(agent_id=owner_id, observation_period_days=30)
