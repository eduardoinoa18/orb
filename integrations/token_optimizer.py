"""Token efficiency engine used before AI calls.

This module reduces cost by caching repeated tasks, avoiding unnecessary AI calls,
and choosing the minimum viable model/token budget.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings


AGENT_DAILY_BUDGETS = {
    "rex": 300,
    "aria": 150,
    "nova": 100,
    "orion": 100,
    "sage": 200,
    "atlas": 200,
    "commander": 200,
}

# Platform-wide hard limit (cents/day)
PLATFORM_DAILY_BUDGET_CENTS = 1500


TASK_TOKEN_LIMITS = {
    # HAIKU tier
    "sms_compose": 100,
    "email_subject": 50,
    "categorization": 200,
    "date_calc": 100,
    "status_check": 150,
    # SONNET tier
    "lead_qualification": 400,
    "email_draft": 500,
    "meeting_summary": 600,
    "content_creation": 800,
    "strategy_analysis": 800,
    "code_generation": 1500,
    "commander_response": 500,
    # OPUS tier
    "weekly_review": 1200,
    "strategy_improvement": 1000,
    "architecture": 1500,
    "security_audit": 1000,
    # Legacy keys kept for backwards-compat
    "short_analysis": 300,
    "long_analysis": 800,
    "full_strategy": 1500,
}

# Task types that must use a specific model tier (in normal budget mode).
TASK_MODEL_MAP: dict[str, str] = {
    # HAIKU
    "sms_compose": "haiku",
    "email_subject": "haiku",
    "categorization": "haiku",
    "date_calc": "haiku",
    "status_check": "haiku",
    # SONNET
    "lead_qualification": "sonnet",
    "email_draft": "sonnet",
    "meeting_summary": "sonnet",
    "content_creation": "sonnet",
    "strategy_analysis": "sonnet",
    "code_generation": "sonnet",
    "commander_response": "sonnet",
    # OPUS
    "weekly_review": "opus",
    "strategy_improvement": "opus",
    "architecture": "opus",
    "security_audit": "opus",
}


@dataclass
class OptimizationResult:
    """Structured result for one optimized task request."""

    optimized_prompt: str
    selected_model: str
    max_tokens: int
    used_cache: bool
    cache_key: str
    needs_ai: bool
    bypass_reason: str | None = None
    cached_result: str | None = None
    budget_mode: str = "normal"
    should_defer: bool = False
    daily_budget_cents: int = 0
    spent_today_cents: int = 0
    remaining_budget_cents: int = 0


class TokenOptimizer:
    """Budget-conscious helper that standardizes low-cost AI call prep."""

    def __init__(self) -> None:
        self.db = SupabaseService()
        self.cache_ttl_minutes = self._load_cache_ttl_minutes()

    def optimize_prompt(
        self,
        prompt: str,
        task_type: str,
        max_budget_cents: int = 5,
        agent_id: str | None = None,
        is_critical: bool = False,
    ) -> OptimizationResult:
        """Returns compressed prompt, model choice, and token cap for this task."""
        cache_key = self._build_cache_key(prompt=prompt, task_type=task_type)
        budget_snapshot = self._budget_snapshot(agent_id=agent_id)
        cached = self._check_recent_cache(cache_key)
        if cached is not None:
            return OptimizationResult(
                optimized_prompt=prompt,
                selected_model="cache",
                max_tokens=0,
                used_cache=True,
                cache_key=cache_key,
                needs_ai=False,
                bypass_reason="cache_hit",
                cached_result=cached,
                budget_mode=budget_snapshot["budget_mode"],
                should_defer=False,
                daily_budget_cents=budget_snapshot["daily_budget_cents"],
                spent_today_cents=budget_snapshot["spent_today_cents"],
                remaining_budget_cents=budget_snapshot["remaining_budget_cents"],
            )

        if self._task_is_non_ai(task_type=task_type, prompt=prompt):
            return OptimizationResult(
                optimized_prompt=prompt,
                selected_model="none",
                max_tokens=0,
                used_cache=False,
                cache_key=cache_key,
                needs_ai=False,
                bypass_reason="non_ai_task",
                budget_mode=budget_snapshot["budget_mode"],
                should_defer=False,
                daily_budget_cents=budget_snapshot["daily_budget_cents"],
                spent_today_cents=budget_snapshot["spent_today_cents"],
                remaining_budget_cents=budget_snapshot["remaining_budget_cents"],
            )

        if budget_snapshot["budget_mode"] == "deferred" and not is_critical:
            return OptimizationResult(
                optimized_prompt=self._compress_prompt(prompt),
                selected_model="haiku",
                max_tokens=self._max_tokens_for_task(task_type),
                used_cache=False,
                cache_key=cache_key,
                needs_ai=False,
                bypass_reason="budget_deferred",
                budget_mode="deferred",
                should_defer=True,
                daily_budget_cents=budget_snapshot["daily_budget_cents"],
                spent_today_cents=budget_snapshot["spent_today_cents"],
                remaining_budget_cents=budget_snapshot["remaining_budget_cents"],
            )

        compressed = self._compress_prompt(prompt)
        complexity = self._complexity_score(compressed)
        model = self._select_model(
            complexity=complexity,
            max_budget_cents=max_budget_cents,
            budget_mode=budget_snapshot["budget_mode"],
            task_type=task_type,
        )
        max_tokens = self._max_tokens_for_task(task_type, budget_mode=budget_snapshot["budget_mode"])

        return OptimizationResult(
            optimized_prompt=compressed,
            selected_model=model,
            max_tokens=max_tokens,
            used_cache=False,
            cache_key=cache_key,
            needs_ai=True,
            budget_mode=budget_snapshot["budget_mode"],
            should_defer=False,
            daily_budget_cents=budget_snapshot["daily_budget_cents"],
            spent_today_cents=budget_snapshot["spent_today_cents"],
            remaining_budget_cents=budget_snapshot["remaining_budget_cents"],
        )

    def track_agent_efficiency(self, agent_id: str, period_days: int = 7) -> dict[str, Any]:
        """Builds a lightweight weekly efficiency report for one agent."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        try:
            rows = self.db.fetch_all("activity_log", {"agent_id": agent_id})
        except DatabaseConnectionError:
            rows = []

        relevant = []
        for row in rows:
            created_at = str(row.get("created_at") or "")
            if not created_at:
                continue
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= cutoff:
                relevant.append(row)

        total = len(relevant)
        token_values = [int((row.get("metadata") or {}).get("tokens_used", 0)) for row in relevant if isinstance(row.get("metadata"), dict)]
        avg_tokens = round(sum(token_values) / len(token_values), 2) if token_values else 0.0
        total_cost_cents = sum(int(row.get("cost_cents") or 0) for row in relevant)
        successes = sum(1 for row in relevant if str(row.get("outcome") or "").lower() in {"success", "approved", "opened", "ready"})
        cache_hits = sum(1 for row in relevant if str((row.get("metadata") or {}).get("optimizer_reason", "")) == "cache_hit")
        deferred = sum(1 for row in relevant if str((row.get("metadata") or {}).get("optimizer_reason", "")) == "budget_deferred")
        budget_snapshot = self._budget_snapshot(agent_id=agent_id)

        return {
            "agent_id": agent_id,
            "period_days": period_days,
            "events": total,
            "avg_tokens_per_event": avg_tokens,
            "total_cost_dollars": round(total_cost_cents / 100, 2),
            "cost_per_success_dollars": round((total_cost_cents / 100) / max(successes, 1), 4),
            "cache_hit_rate": round((cache_hits / total) * 100, 2) if total else 0.0,
            "deferred_task_rate": round((deferred / total) * 100, 2) if total else 0.0,
            "daily_budget_dollars": round(self._daily_budget_for_agent(agent_id) / 100, 2),
            "spent_today_dollars": round(budget_snapshot["spent_today_cents"] / 100, 2),
            "remaining_today_dollars": round(budget_snapshot["remaining_budget_cents"] / 100, 2),
            "budget_mode": budget_snapshot["budget_mode"],
        }

    def save_cached_result(self, cache_key: str, result_text: str, agent_id: str | None = None) -> None:
        """Stores a cache hit candidate in activity_log metadata."""
        self.db.log_activity(
            agent_id=agent_id,
            owner_id=None,
            action_type="token_optimizer_cache",
            description=f"Cache write for key={cache_key[:12]}",
            cost_cents=0,
            outcome="success",
            metadata={"cache_key": cache_key, "cached_result": result_text},
        )

    def _build_cache_key(self, prompt: str, task_type: str) -> str:
        raw = f"{task_type}:{prompt.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _check_recent_cache(self, cache_key: str) -> str | None:
        try:
            rows = self.db.fetch_all("activity_log", {"action_type": "token_optimizer_cache"})
        except DatabaseConnectionError:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.cache_ttl_minutes)
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if metadata.get("cache_key") != cache_key:
                continue
            created_at = str(row.get("created_at") or "")
            if created_at:
                try:
                    ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except ValueError:
                    continue
            cached = metadata.get("cached_result")
            if isinstance(cached, str) and cached.strip():
                return cached
        return None

    def _task_is_non_ai(self, task_type: str, prompt: str) -> bool:
        non_ai_types = {"date_calc", "formatting", "value_lookup"}
        if task_type in non_ai_types:
            return True
        prompt_lc = prompt.lower()
        return any(phrase in prompt_lc for phrase in ["format this date", "sort this list", "uppercase this"])

    def _compress_prompt(self, prompt: str) -> str:
        cleaned = re.sub(r"\s+", " ", prompt).strip()
        # Keep compression simple and deterministic for predictable output.
        return cleaned[:4000]

    def _complexity_score(self, prompt: str) -> int:
        words = len(prompt.split())
        if words <= 25:
            return 2
        if words <= 60:
            return 4
        if words <= 140:
            return 6
        if words <= 260:
            return 8
        return 10

    def _select_model(
        self,
        complexity: int,
        max_budget_cents: int,
        budget_mode: str = "normal",
        task_type: str | None = None,
    ) -> str:
        # Budget constraints always override task-type preferences.
        if budget_mode in {"minimal", "deferred"}:
            return "haiku"
        # Explicit task-type → model mapping takes precedence over complexity heuristic.
        if task_type and task_type in TASK_MODEL_MAP:
            return TASK_MODEL_MAP[task_type]
        if complexity <= 3:
            return "haiku"
        if complexity <= 6:
            return "haiku" if max_budget_cents <= 3 else "sonnet"
        if complexity <= 9:
            return "sonnet"
        return "opus"

    def _max_tokens_for_task(self, task_type: str, budget_mode: str = "normal") -> int:
        multiplier = 0.6 if budget_mode in {"minimal", "deferred"} else 1.0
        if task_type in TASK_TOKEN_LIMITS:
            return max(50, int(TASK_TOKEN_LIMITS[task_type] * multiplier))
        if "sms" in task_type:
            return max(50, int(TASK_TOKEN_LIMITS["sms_compose"] * multiplier))
        if "strategy" in task_type:
            return max(50, int(TASK_TOKEN_LIMITS["full_strategy"] * multiplier))
        return max(50, int(TASK_TOKEN_LIMITS["short_analysis"] * multiplier))

    def _daily_budget_for_agent(self, agent_id: str) -> int:
        key = (agent_id or "").lower()
        for name, cents in AGENT_DAILY_BUDGETS.items():
            if name in key:
                return cents
        return 100

    def _budget_snapshot(self, agent_id: str | None) -> dict[str, int | str]:
        daily_budget_cents = self._daily_budget_for_agent(agent_id or "")
        spent_today_cents = self._spent_today_cents(agent_id=agent_id)
        remaining_budget_cents = max(daily_budget_cents - spent_today_cents, 0)

        if spent_today_cents >= daily_budget_cents:
            budget_mode = "deferred"
        elif spent_today_cents >= int(daily_budget_cents * 0.8):
            budget_mode = "minimal"
        else:
            budget_mode = "normal"

        return {
            "daily_budget_cents": daily_budget_cents,
            "spent_today_cents": spent_today_cents,
            "remaining_budget_cents": remaining_budget_cents,
            "budget_mode": budget_mode,
        }

    def _spent_today_cents(self, agent_id: str | None) -> int:
        if not agent_id:
            return 0
        try:
            rows = self.db.fetch_all("activity_log", {"agent_id": agent_id})
        except DatabaseConnectionError:
            return 0

        today = datetime.now(timezone.utc).date()
        spent_today_cents = 0
        for row in rows:
            created_at = str(row.get("created_at") or "")
            if not created_at:
                continue
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.date() != today:
                continue
            spent_today_cents += int(row.get("cost_cents") or 0)
        return spent_today_cents

    def _load_cache_ttl_minutes(self) -> int:
        try:
            ttl = int(get_settings().token_cache_ttl_minutes)
        except Exception:
            ttl = 1440
        return max(ttl, 1)
