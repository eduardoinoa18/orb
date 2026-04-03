"""Tests for universal brain connector (Module 2 Step B1)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from integrations.brain_connector import (
    BaseBrain,
    BrainMessage,
    BrainResponse,
    BrainRouter,
    route_task,
)


@dataclass
class _StubBrain(BaseBrain):
    provider: str
    model_name: str
    cost_per_1k_input: float
    cost_per_1k_output: float = 0.0
    supports_vision: bool = False
    supports_tools: bool = True
    max_context_tokens: int = 8192

    def complete(self, messages, system=None, max_tokens=1000, temperature=0.7):
        return BrainResponse(
            content="ok",
            model_used=f"{self.provider}/{self.model_name}",
            input_tokens=10,
            output_tokens=20,
            cost_cents=1,
            latency_ms=25,
        )


def _seed_router() -> BrainRouter:
    router = BrainRouter()
    router.register(_StubBrain("groq", "llama-3.1-8b-instant", 0.0001))
    router.register(_StubBrain("google", "gemini-1.5-flash", 0.0003))
    router.register(_StubBrain("anthropic", "claude-haiku-4-5-20251001", 0.0004))
    router.register(_StubBrain("anthropic", "claude-sonnet-4-6", 0.003))
    router.register(_StubBrain("anthropic", "claude-opus-4-6", 0.015))
    router.register(_StubBrain("openai", "gpt-4o", 0.01, supports_vision=True))
    router.register(_StubBrain("ollama", "llama3.1", 0.0))
    return router


def test_register_and_get_brain():
    router = BrainRouter()
    key = router.register(_StubBrain("anthropic", "claude-sonnet-4-6", 0.003))
    assert key == "anthropic/claude-sonnet-4-6"
    brain = router.get("anthropic", "claude-sonnet-4-6")
    assert brain.model_name == "claude-sonnet-4-6"


def test_get_unknown_brain_raises():
    router = BrainRouter()
    with pytest.raises(ValueError):
        router.get("anthropic", "missing")


def test_brain_response_shape_from_complete():
    router = _seed_router()
    brain = router.get("groq", "llama-3.1-8b-instant")
    response = brain.complete([BrainMessage(role="user", content="hello")])
    assert response.content == "ok"
    assert response.model_used == "groq/llama-3.1-8b-instant"


def test_brain_router_selects_cheapest_for_simple():
    router = _seed_router()
    # Includes local ollama at 0.0, so this should win.
    selected = router.cheapest_for_task(task_complexity=2)
    assert selected.provider == "ollama"


def test_brain_router_selects_mid_for_medium():
    router = _seed_router()
    # Medium selects within (0.0002, 0.005), cheapest should be Gemini flash.
    selected = router.cheapest_for_task(task_complexity=6)
    assert selected.provider == "google"
    assert selected.model_name == "gemini-1.5-flash"


def test_brain_router_selects_opus_for_complex():
    router = _seed_router()
    selected = router.cheapest_for_task(task_complexity=9)
    assert selected.provider == "anthropic"
    assert selected.model_name == "claude-opus-4-6"


def test_route_task_uses_mapping_when_available():
    router = _seed_router()
    selected = route_task("meeting_summary", router=router)
    assert selected.model_name == "claude-sonnet-4-6"


def test_route_task_budget_mode_uses_cheapest():
    router = _seed_router()
    selected = route_task("architecture", owner_preferences={"budget_mode": True}, router=router)
    assert selected.provider == "ollama"


def test_route_task_quality_mode_uses_best():
    router = _seed_router()
    selected = route_task("simple_reply", owner_preferences={"quality_mode": True}, router=router)
    assert selected.model_name == "claude-opus-4-6"


def test_route_task_privacy_prefers_local():
    router = _seed_router()
    selected = route_task("email_compose", owner_preferences={"prefer_local": True}, router=router)
    assert selected.provider == "ollama"


def test_fallback_when_brain_unavailable():
    router = BrainRouter()
    router.register(_StubBrain("groq", "llama-3.1-8b-instant", 0.0001))
    selected = route_task("architecture", router=router)
    # Architecture maps to opus, but opus is not connected, so fallback to cheapest.
    assert selected.provider == "groq"
