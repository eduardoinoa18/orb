"""Universal AI brain connector for ORB (Module 2, Step B1).

This module defines a provider-agnostic interface so every model can be used
through the same API by agents and routes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BrainMessage:
    """A normalized message for any provider SDK."""

    role: str  # user | assistant | system
    content: str
    tokens: int = 0


@dataclass(slots=True)
class BrainResponse:
    """Normalized response metadata regardless of provider."""

    content: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_cents: int
    latency_ms: int


class BaseBrain(ABC):
    """Every AI brain must implement this interface."""

    provider: str = ""
    model_name: str = ""
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    supports_vision: bool = False
    supports_tools: bool = False
    max_context_tokens: int = 0

    @abstractmethod
    def complete(
        self,
        messages: list[BrainMessage],
        system: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> BrainResponse:
        """Run completion against the provider and return normalized output."""

    def key(self) -> str:
        """Stable registry key for this brain."""
        return f"{self.provider}/{self.model_name}"


class BrainRouter:
    """Registers and resolves available brains."""

    def __init__(self) -> None:
        self._brains: dict[str, BaseBrain] = {}

    def register(self, brain: BaseBrain) -> str:
        """Register a brain instance and return its key."""
        key = brain.key()
        self._brains[key] = brain
        return key

    def get(self, provider: str, model: str) -> BaseBrain:
        """Return a registered brain or raise a user-friendly error."""
        key = f"{provider}/{model}"
        if key not in self._brains:
            raise ValueError(
                f"Brain {key} not connected. "
                "Go to Settings > Integrations to add it."
            )
        return self._brains[key]

    def cheapest_for_task(self, task_complexity: int) -> BaseBrain:
        """Select a brain by complexity and configured prices.

        Complexity scale: 1 (trivial) to 10 (very complex).
        """
        available = list(self._brains.values())
        if not available:
            raise ValueError("No brains registered.")

        if task_complexity <= 3:
            return min(available, key=lambda b: b.cost_per_1k_input)

        if task_complexity <= 7:
            mid = [
                b
                for b in available
                if b.cost_per_1k_input > 0.0002 and b.cost_per_1k_input < 0.005
            ]
            if mid:
                return min(mid, key=lambda b: b.cost_per_1k_input)
            return min(available, key=lambda b: b.cost_per_1k_input)

        return max(available, key=lambda b: b.cost_per_1k_input)

    def cheapest(self) -> BaseBrain:
        """Return cheapest registered brain."""
        available = list(self._brains.values())
        if not available:
            raise ValueError("No brains registered.")
        return min(available, key=lambda b: b.cost_per_1k_input)

    def best(self) -> BaseBrain:
        """Return most expensive registered brain as a quality proxy."""
        available = list(self._brains.values())
        if not available:
            raise ValueError("No brains registered.")
        return max(available, key=lambda b: b.cost_per_1k_input)

    def list_available(self) -> list[dict[str, Any]]:
        """Expose metadata for UI cards in Settings > AI Brains."""
        return [
            {
                "key": k,
                "provider": v.provider,
                "model": v.model_name,
                "cost_per_1k": v.cost_per_1k_input,
                "supports_vision": v.supports_vision,
                "connected": True,
            }
            for k, v in self._brains.items()
        ]


TASK_BRAIN_MAPPING: dict[str, str] = {
    "sms_compose": "groq/llama-3.1-8b-instant",
    "simple_reply": "groq/llama-3.1-8b-instant",
    "date_format": "groq/llama-3.1-8b-instant",
    "email_draft": "anthropic/claude-haiku-4-5-20251001",
    "lead_qualify_simple": "google/gemini-1.5-flash",
    "content_short": "anthropic/claude-haiku-4-5-20251001",
    "lead_qualify_full": "anthropic/claude-sonnet-4-6",
    "email_compose": "anthropic/claude-sonnet-4-6",
    "meeting_summary": "anthropic/claude-sonnet-4-6",
    "strategy_analyze": "anthropic/claude-sonnet-4-6",
    "code_generate": "anthropic/claude-sonnet-4-6",
    "content_long": "anthropic/claude-sonnet-4-6",
    "architecture": "anthropic/claude-opus-4-6",
    "strategy_improve": "anthropic/claude-opus-4-6",
    "security_audit": "anthropic/claude-opus-4-6",
    "weekly_review": "anthropic/claude-opus-4-6",
    "image_analyze": "openai/gpt-4o",
    "chart_read": "openai/gpt-4o",
    "local_task": "ollama/llama3.1",
}


_default_router = BrainRouter()


def register_brain(brain: BaseBrain) -> str:
    """Register a brain in the process-global router."""
    return _default_router.register(brain)


def get_brain(provider: str, model: str) -> BaseBrain:
    """Lookup a brain in the process-global router."""
    return _default_router.get(provider, model)


def get_cheapest_brain() -> BaseBrain:
    """Return cheapest brain from process-global router."""
    return _default_router.cheapest()


def get_best_brain() -> BaseBrain:
    """Return best brain from process-global router."""
    return _default_router.best()


def route_task(
    task_type: str,
    owner_preferences: dict[str, Any] | None = None,
    router: BrainRouter | None = None,
) -> BaseBrain:
    """Route a task to the most suitable connected brain.

    Owner overrides are respected first.
    """
    target_router = router or _default_router

    if owner_preferences:
        if owner_preferences.get("prefer_local"):
            try:
                return target_router.get("ollama", "llama3.1")
            except ValueError:
                return target_router.cheapest()
        if owner_preferences.get("budget_mode"):
            return target_router.cheapest()
        if owner_preferences.get("quality_mode"):
            return target_router.best()

    model_key = TASK_BRAIN_MAPPING.get(
        task_type,
        "anthropic/claude-haiku-4-5-20251001",
    )
    provider, model = model_key.split("/", 1)
    try:
        return target_router.get(provider, model)
    except ValueError:
        return target_router.cheapest()
