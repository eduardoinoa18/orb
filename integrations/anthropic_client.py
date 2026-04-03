"""Anthropic Claude integration for ORB.

All Claude calls go through this module so we have one place to:
  - Pick the right model (cheap Haiku vs. smart Sonnet vs. powerful Opus)
  - Track token usage and cost in the activity_log table
  - Handle errors without crashing the calling agent

COST GUIDE (approximate as of 2025):
  claude-haiku-4-5-20251001  — cheapest, fast, good for simple tasks
    claude-sonnet-4-6          — balanced cost/quality, good for writing/research
    claude-opus-4-6            — most powerful, most expensive, use sparingly
"""

import json
import logging
from typing import Any

import anthropic

from app.database.activity_log import log_activity
from config.settings import get_settings
from integrations.token_optimizer import OptimizationResult, TokenOptimizer

logger = logging.getLogger("orb.anthropic")

# Cost per 1 million tokens in US cents (approximate)
_MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001":  {"input": 25,   "output": 125},
    "claude-sonnet-4-6":          {"input": 300,  "output": 1500},
    "claude-opus-4-6":            {"input": 1500, "output": 7500},
}

_MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}


def _get_client() -> anthropic.Anthropic:
    """Returns an authenticated Anthropic client.

    Calling settings.require() here — not at module load time — means the
    app can start without the key. You only get an error when you actually
    try to call Claude for the first time.
    """
    settings = get_settings()
    api_key = settings.require("anthropic_api_key")
    return anthropic.Anthropic(api_key=api_key)


def _estimate_cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Returns the approximate cost in cents for a given model and token counts."""
    rates = _MODEL_COSTS.get(model, {"input": 300, "output": 1500})
    cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
    return max(1, round(cost))  # always at least 1 cent so we don't log 0-cost calls


def _infer_task_type(prompt: str, max_tokens: int) -> str:
    """Infers an optimizer task label from prompt shape and output budget."""
    prompt_lc = prompt.lower()
    if any(keyword in prompt_lc for keyword in ["sms", "text message", "reminder"]):
        return "sms_compose"
    if any(keyword in prompt_lc for keyword in ["strategy", "trade setup", "risk manager"]):
        return "full_strategy"
    if max_tokens <= 220:
        return "short_analysis"
    if max_tokens >= 900:
        return "long_analysis"
    return "short_analysis"


def _resolve_model_alias(model_name: str, fallback: str) -> str:
    """Maps optimizer model aliases to concrete Anthropic model IDs."""
    return _MODEL_ALIASES.get(model_name, fallback)


def ask_claude(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 1024,
    task_type: str | None = None,
    max_budget_cents: int = 5,
    agent_id: str | None = None,
    is_critical: bool = False,
) -> dict[str, Any]:
    """
    Sends a message to Claude and returns the response plus usage metadata.

    Use this for cheap, fast tasks — summarising, classifying, short answers.
    Defaults to Haiku which is the most cost-effective model.

    Returns a dict with:
      text        — Claude's response as a plain string
      model       — which model was actually used
      input_tokens  — how many tokens your prompt used
      output_tokens — how many tokens Claude's reply used
      cost_cents    — estimated cost in US cents

    Raises RuntimeError if ANTHROPIC_API_KEY is not set.
    Raises anthropic.APIError if the API call fails.
    """
    inferred_task_type = task_type or _infer_task_type(prompt=prompt, max_tokens=max_tokens)
    optimizer: TokenOptimizer | None = None
    try:
        optimizer = TokenOptimizer()
        optimization = optimizer.optimize_prompt(
            prompt=prompt,
            task_type=inferred_task_type,
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
        if optimization.cached_result is not None:
            logger.info("Claude call bypassed via cache hit")
            return {
                "text": optimization.cached_result,
                "model": "cache",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_cents": 0,
                "optimization": {
                    "budget_mode": optimization.budget_mode,
                    "bypass_reason": optimization.bypass_reason,
                    "remaining_budget_cents": optimization.remaining_budget_cents,
                },
            }
        logger.info("Claude call bypassed as non-AI task")
        return {
            "text": "" if optimization.should_defer else optimization.optimized_prompt,
            "model": "deferred" if optimization.should_defer else "none",
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

    resolved_model = model
    if model == "claude-haiku-4-5-20251001" or task_type is not None:
        resolved_model = _resolve_model_alias(optimization.selected_model, fallback=model)

    resolved_max_tokens = max_tokens
    if optimization.max_tokens > 0:
        resolved_max_tokens = min(max_tokens, optimization.max_tokens)

    client = _get_client()
    try:
        response = client.messages.create(
            model=resolved_model,
            max_tokens=resolved_max_tokens,
            system=system,
            messages=[{"role": "user", "content": optimization.optimized_prompt}],
        )
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_cents = _estimate_cost_cents(resolved_model, input_tokens, output_tokens)

        logger.info(
            "Claude call completed — model=%s in=%d out=%d cost=%d¢",
            resolved_model, input_tokens, output_tokens, cost_cents,
        )
        if optimizer is not None and optimization.cache_key != "unavailable":
            try:
                optimizer.save_cached_result(optimization.cache_key, response.content[0].text, agent_id=agent_id)
            except Exception:
                logger.warning("Failed to persist token optimizer cache entry")
        log_activity(
            agent_id=agent_id,
            action_type="claude",
            description=f"Anthropic call using {resolved_model}",
            outcome="success",
            cost_cents=cost_cents,
        )

        return {
            "text": response.content[0].text,
            "model": resolved_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": cost_cents,
            "optimization": {
                "selected_model": optimization.selected_model,
                "max_tokens": resolved_max_tokens,
                "budget_mode": optimization.budget_mode,
                "remaining_budget_cents": optimization.remaining_budget_cents,
            },
        }
    except anthropic.APIError as error:
        logger.error("Anthropic API error: %s", error)
        log_activity(
            agent_id=agent_id,
            action_type="claude",
            description=f"Anthropic call using {resolved_model}",
            outcome=f"error: {error}",
            cost_cents=0,
        )
        raise


def ask_claude_smart(
    prompt: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 2048,
    task_type: str = "long_analysis",
    max_budget_cents: int = 8,
    agent_id: str | None = None,
    is_critical: bool = False,
) -> dict[str, Any]:
    """
    Sends a message to Claude Sonnet — the balanced model for research and writing.

    Use this when Haiku isn't good enough but you don't need full Opus power.
    Costs roughly 10x more than Haiku, but produces much better long-form content.
    """
    return ask_claude(
        prompt=prompt,
        system=system,
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        task_type=task_type,
        max_budget_cents=max_budget_cents,
        agent_id=agent_id,
        is_critical=is_critical,
    )


def analyze_trade_setup(
    strategy_rules: dict[str, Any],
    market_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Evaluates whether a trading alert matches the active strategy rules.

    Used by the trading agent (Level 3) whenever TradingView sends a webhook.
    Returns a structured JSON decision with confidence score, entry/stop/target,
    and plain-English reasoning.

    Returns dict with keys: valid, confidence, entry_price, stop_loss,
    take_profit, reasoning.
    """
    system_prompt = (
        "You are a professional futures trader and risk manager. "
        "You evaluate trade setups strictly based on written rules. "
        "You always respond in valid JSON only — no extra text."
    )

    user_prompt = f"""
Given these strategy rules:
{json.dumps(strategy_rules, indent=2)}

And this market alert:
{json.dumps(market_data, indent=2)}

Evaluate if this is a valid setup.
Respond with this exact JSON structure:
{{
  "valid": true or false,
  "confidence": 0-100,
  "entry_price": float or null,
  "stop_loss": float or null,
  "take_profit": float or null,
  "reasoning": "Two sentence maximum explanation."
}}
"""
    result = ask_claude(
        prompt=user_prompt,
        system=system_prompt,
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
    )

    try:
        parsed = json.loads(result["text"])
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON response for trade analysis")
        parsed = {
            "valid": False,
            "confidence": 0,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "reasoning": "Claude returned an invalid response format.",
        }

    return {**parsed, "cost_cents": result["cost_cents"]}


def route_task(task_description: str) -> str:
    """
    Decides which AI model to use based on the type of task.

    This is an automatic cost-saver. Instead of always sending everything to
    the expensive model, we classify the task first and pick the cheapest
    model that can handle it well.

    Returns one of: "haiku", "sonnet", "opus", "dalle"
    """
    routing_prompt = f"""
Classify this task into exactly one category.
Task: "{task_description}"

Categories:
- "haiku" — short/simple: classify, summarise in 1-2 lines, boolean decision, extract data
- "sonnet" — medium: write an email, research a topic, explain something, draft a report
- "opus" — complex: multi-step reasoning, code review, strategy analysis, anything with nuance
- "dalle" — needs an image

Respond with exactly one word from the list above. No punctuation. No explanation.
"""
    result = ask_claude(
        prompt=routing_prompt,
        system="You are a task classifier. Respond with exactly one word.",
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
    )
    model_choice = result["text"].strip().lower()
    valid_choices = {"haiku", "sonnet", "opus", "dalle"}
    if model_choice not in valid_choices:
        logger.warning("route_task got unexpected value '%s', defaulting to haiku", model_choice)
        return "haiku"
    return model_choice

