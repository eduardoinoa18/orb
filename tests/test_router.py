"""Tests for the AI model routing table (integrations/router.py)."""

from integrations.router import route, RouteDecision


def test_haiku_task_routes_to_haiku() -> None:
    decision = route("sms_compose")
    assert decision.model_tier == "haiku"
    assert decision.provider == "anthropic"
    assert decision.max_tokens == 80


def test_sonnet_task_routes_to_sonnet() -> None:
    decision = route("lead_qualification")
    assert decision.model_tier == "sonnet"
    assert decision.provider == "anthropic"
    assert decision.max_tokens == 400


def test_opus_task_routes_to_opus() -> None:
    decision = route("weekly_review")
    assert decision.model_tier == "opus"
    assert decision.provider == "anthropic"
    assert decision.max_tokens == 1200


def test_groq_task_routes_to_groq() -> None:
    decision = route("health_check")
    assert decision.model_tier == "groq"
    assert decision.provider == "groq"


def test_minimal_budget_forces_haiku_for_opus_task() -> None:
    decision = route("weekly_review", budget_mode="minimal")
    assert decision.model_tier == "haiku"
    assert decision.provider == "anthropic"


def test_deferred_budget_forces_haiku_for_sonnet_task() -> None:
    decision = route("code_generation", budget_mode="deferred")
    assert decision.model_tier == "haiku"


def test_unknown_task_defaults_to_haiku() -> None:
    decision = route("some_unknown_task_xyz")
    assert decision.model_tier == "haiku"


def test_route_returns_route_decision_dataclass() -> None:
    decision = route("email_draft")
    assert isinstance(decision, RouteDecision)
    assert decision.task_type == "email_draft"
    assert decision.can_cache is True


def test_security_audit_routes_to_opus() -> None:
    decision = route("security_audit")
    assert decision.model_tier == "opus"
    assert decision.max_tokens == 1000


def test_commander_response_routes_to_sonnet() -> None:
    decision = route("commander_response")
    assert decision.model_tier == "sonnet"
    assert decision.max_tokens == 500
