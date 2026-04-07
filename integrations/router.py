"""AI model routing table for ORB.

Determines which model provider and tier to use for a given task type,
respecting the platform's token-efficiency and cost rules.

Routing tiers:
  haiku   — cheapest, fastest (~70 % of calls)
  sonnet  — mid-range  (~25 % of calls)
  opus    — highest quality (~5 % of calls)
  groq    — near-free, used when speed > quality
"""

from __future__ import annotations

from dataclasses import dataclass


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
