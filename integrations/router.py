"""AI model routing table for ORB.

Determines which model provider and tier to use for a given task type,
respecting the platform's token-efficiency and cost rules.

Routing tiers:
  haiku   — cheapest, fastest (~70 % of calls)
  sonnet  — mid-range  (~25 % of calls)
  opus    — highest quality (~5 % of calls)
  groq    — near-free, used when speed > quality
  gemini  — free Google tier, content fallback
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("orb.router")


# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

_HAIKU_TASKS: frozenset[str] = frozenset(
    {
        "sms_compose",
        "email_subject",
        "categorization",
        "date_calc",
        "status_check",
        "simple_decision",
        "format_conversion",
        "data_extraction",
        "health_check",
    }
)

_SONNET_TASKS: frozenset[str] = frozenset(
    {
        "lead_qualification",
        "email_draft",
        "meeting_summary",
        "content_creation",
        "strategy_analysis",
        "code_generation",
        "commander_response",
    }
)

_OPUS_TASKS: frozenset[str] = frozenset(
    {
        "weekly_review",
        "strategy_improvement",
        "architecture",
        "security_audit",
    }
)

_GROQ_TASKS: frozenset[str] = frozenset(
    {
        "simple_decision",
        "format_conversion",
        "data_extraction",
        "health_check",
    }
)

# Token limits per task type (mirrors token_optimizer.TASK_TOKEN_LIMITS)
_TOKEN_LIMITS: dict[str, int] = {
    # HAIKU
    "sms_compose": 80,
    "email_subject": 40,
    "categorization": 200,
    "date_calc": 100,
    "status_check": 150,
    # SONNET
    "lead_qualification": 400,
    "email_draft": 500,
    "meeting_summary": 600,
    "content_creation": 800,
    "strategy_analysis": 800,
    "code_generation": 1500,
    "commander_response": 500,
    # OPUS
    "weekly_review": 1200,
    "strategy_improvement": 1000,
    "architecture": 1500,
    "security_audit": 1000,
    # GROQ / fast
    "simple_decision": 50,
    "format_conversion": 100,
    "data_extraction": 200,
    "health_check": 50,
}

_DEFAULT_TOKEN_LIMIT = 300


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    """Routing outcome for a single AI call."""

    model_tier: str   # haiku | sonnet | opus | groq
    provider: str     # anthropic | groq
    max_tokens: int
    task_type: str
    can_cache: bool


def route(task_type: str, budget_mode: str = "normal") -> RouteDecision:
    """Return the routing decision for *task_type* under the given *budget_mode*.

    When *budget_mode* is ``"minimal"`` or ``"deferred"``, all non-GROQ tasks
    are forced down to haiku regardless of their normal tier.
    """
    normalised = task_type.strip().lower()

    # Forced downgrade for budget constraints
    if budget_mode in {"minimal", "deferred"}:
        return RouteDecision(
            model_tier="haiku",
            provider="anthropic",
            max_tokens=_TOKEN_LIMITS.get(normalised, _DEFAULT_TOKEN_LIMIT),
            task_type=normalised,
            can_cache=True,
        )

    if normalised in _GROQ_TASKS:
        return RouteDecision(
            model_tier="groq",
            provider="groq",
            max_tokens=_TOKEN_LIMITS.get(normalised, 50),
            task_type=normalised,
            can_cache=False,
        )

    if normalised in _OPUS_TASKS:
        return RouteDecision(
            model_tier="opus",
            provider="anthropic",
            max_tokens=_TOKEN_LIMITS.get(normalised, _DEFAULT_TOKEN_LIMIT),
            task_type=normalised,
            can_cache=True,
        )

    if normalised in _SONNET_TASKS:
        return RouteDecision(
            model_tier="sonnet",
            provider="anthropic",
            max_tokens=_TOKEN_LIMITS.get(normalised, _DEFAULT_TOKEN_LIMIT),
            task_type=normalised,
            can_cache=True,
        )

    # Default to haiku for unknown / simple tasks
    return RouteDecision(
        model_tier="haiku",
        provider="anthropic",
        max_tokens=_TOKEN_LIMITS.get(normalised, _DEFAULT_TOKEN_LIMIT),
        task_type=normalised,
        can_cache=True,
    )


def ask_routed(
    prompt: str,
    system: str = "You are a helpful assistant.",
    task_type: str = "short_analysis",
    max_tokens: int | None = None,
    budget_mode: str = "normal",
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Route a request to the best available AI provider automatically.

    Tries: Groq (free) → Anthropic → Gemini (free) → fallback error.
    This is the single function all agents should use for cost-optimized AI calls.
    """
    decision = route(task_type, budget_mode=budget_mode)
    tokens = max_tokens or decision.max_tokens

    # If routed to Groq, try it first
    if decision.provider == "groq":
        try:
            from integrations.groq_client import ask_groq, is_groq_available
            if is_groq_available():
                return ask_groq(
                    prompt=prompt, system=system,
                    max_tokens=tokens, agent_id=agent_id,
                )
        except Exception:
            logger.warning("Groq unavailable, falling through to Anthropic")

    # Primary: Anthropic
    try:
        from integrations.anthropic_client import ask_claude
        from integrations.anthropic_client import _MODEL_ALIASES

        model_id = _MODEL_ALIASES.get(decision.model_tier, "claude-haiku-4-5-20251001")
        return ask_claude(
            prompt=prompt, system=system,
            model=model_id, max_tokens=tokens,
            task_type=task_type, agent_id=agent_id,
        )
    except Exception as anthropic_err:
        logger.warning("Anthropic unavailable: %s — trying fallbacks", anthropic_err)

    # Fallback: Gemini (free)
    try:
        from integrations.gemini_client import ask_gemini, is_gemini_available
        if is_gemini_available():
            return ask_gemini(
                prompt=prompt, system=system,
                max_tokens=tokens, agent_id=agent_id,
            )
    except Exception:
        logger.warning("Gemini also unavailable")

    # Fallback: Groq (if not already tried)
    if decision.provider != "groq":
        try:
            from integrations.groq_client import ask_groq, is_groq_available
            if is_groq_available():
                return ask_groq(
                    prompt=prompt, system=system,
                    max_tokens=tokens, agent_id=agent_id,
                )
        except Exception:
            pass

    raise RuntimeError(
        "No AI provider available. Set at least one of: "
        "ANTHROPIC_API_KEY, GROQ_API_KEY, or GOOGLE_AI_API_KEY in Railway Variables."
    )
