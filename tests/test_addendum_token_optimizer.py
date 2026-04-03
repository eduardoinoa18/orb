"""Tests for Addendum 4 token optimizer."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from integrations.token_optimizer import TokenOptimizer


def test_optimize_prompt_returns_cache_hit_when_recent_cache_exists() -> None:
    cache_key = __import__("hashlib").sha256("sms_compose:hello".encode("utf-8")).hexdigest()
    with patch("integrations.token_optimizer.SupabaseService") as mock_db_cls:
        mock_db = MagicMock()
        mock_db.fetch_all.return_value = [
            {
                "action_type": "token_optimizer_cache",
                "created_at": "2099-01-01T00:00:00+00:00",
                "metadata": {
                    "cache_key": cache_key,
                    "cached_result": "cached-output",
                },
            }
        ]
        mock_db_cls.return_value = mock_db
        optimizer = TokenOptimizer()

    result = optimizer.optimize_prompt(prompt="hello", task_type="sms_compose")
    assert result.used_cache is True
    assert result.cached_result == "cached-output"


def test_optimize_prompt_selects_haiku_for_simple_tasks() -> None:
    with patch("integrations.token_optimizer.SupabaseService") as mock_db_cls:
        mock_db = MagicMock()
        mock_db.fetch_all.return_value = []
        mock_db_cls.return_value = mock_db
        optimizer = TokenOptimizer()

    result = optimizer.optimize_prompt(prompt="Write a short sms reminder", task_type="sms_compose")
    assert result.selected_model == "haiku"
    assert result.max_tokens == 100
    assert result.needs_ai is True


def test_optimize_prompt_ignores_expired_cache_entries() -> None:
    cache_key = __import__("hashlib").sha256("sms_compose:hello".encode("utf-8")).hexdigest()
    settings = SimpleNamespace(token_cache_ttl_minutes=60)
    with patch("integrations.token_optimizer.get_settings", return_value=settings), patch(
        "integrations.token_optimizer.SupabaseService"
    ) as mock_db_cls:
        mock_db = MagicMock()
        mock_db.fetch_all.return_value = [
            {
                "action_type": "token_optimizer_cache",
                "created_at": "2000-01-01T00:00:00+00:00",
                "metadata": {
                    "cache_key": cache_key,
                    "cached_result": "stale-output",
                },
            }
        ]
        mock_db_cls.return_value = mock_db
        optimizer = TokenOptimizer()

    result = optimizer.optimize_prompt(prompt="hello", task_type="sms_compose")
    assert result.used_cache is False
    assert result.cached_result is None
    assert result.needs_ai is True


def test_optimize_prompt_switches_to_minimal_mode_near_budget_limit() -> None:
    current_timestamp = datetime.now(timezone.utc).isoformat()
    settings = SimpleNamespace(token_cache_ttl_minutes=1440)
    with patch("integrations.token_optimizer.get_settings", return_value=settings), patch(
        "integrations.token_optimizer.SupabaseService"
    ) as mock_db_cls:
        mock_db = MagicMock()

        def fetch_all(table_name: str, filters=None):  # type: ignore[no-untyped-def]
            if table_name == "activity_log" and filters == {"agent_id": "rex"}:
                return [
                    {
                        "created_at": current_timestamp,
                        "cost_cents": 260,
                    }
                ]
            if table_name == "activity_log" and filters == {"action_type": "token_optimizer_cache"}:
                return []
            return []

        mock_db.fetch_all.side_effect = fetch_all
        mock_db_cls.return_value = mock_db
        optimizer = TokenOptimizer()

    result = optimizer.optimize_prompt(
        prompt="Write a detailed strategy recap for this week.",
        task_type="full_strategy",
        agent_id="rex",
    )
    assert result.budget_mode == "minimal"
    assert result.selected_model == "haiku"
    assert result.max_tokens == 900
    assert result.needs_ai is True
    assert result.remaining_budget_cents == 40


def test_optimize_prompt_defers_non_critical_tasks_after_budget_is_exhausted() -> None:
    current_timestamp = datetime.now(timezone.utc).isoformat()
    settings = SimpleNamespace(token_cache_ttl_minutes=1440)
    with patch("integrations.token_optimizer.get_settings", return_value=settings), patch(
        "integrations.token_optimizer.SupabaseService"
    ) as mock_db_cls:
        mock_db = MagicMock()

        def fetch_all(table_name: str, filters=None):  # type: ignore[no-untyped-def]
            if table_name == "activity_log" and filters == {"agent_id": "rex"}:
                return [
                    {
                        "created_at": current_timestamp,
                        "cost_cents": 320,
                    }
                ]
            if table_name == "activity_log" and filters == {"action_type": "token_optimizer_cache"}:
                return []
            return []

        mock_db.fetch_all.side_effect = fetch_all
        mock_db_cls.return_value = mock_db
        optimizer = TokenOptimizer()

    result = optimizer.optimize_prompt(
        prompt="Draft a long growth analysis.",
        task_type="long_analysis",
        agent_id="rex",
        is_critical=False,
    )
    assert result.needs_ai is False
    assert result.should_defer is True
    assert result.bypass_reason == "budget_deferred"
    assert result.budget_mode == "deferred"
