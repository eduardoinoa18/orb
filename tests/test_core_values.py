from app.runtime.core_values import evaluate_preflight_core_values, evaluate_scan_core_values


def test_preflight_core_values_reports_strong_score_when_clean() -> None:
    report = {
        "blockers": [],
        "warnings": [],
        "schema": {"ready": True},
    }
    scorecard = evaluate_preflight_core_values(report)

    assert scorecard["overall"] >= 90
    assert scorecard["scores"]["simplicity"] >= 90
    assert scorecard["scores"]["reliability"] >= 90
    assert scorecard["recommendations"]


def test_preflight_core_values_degrades_with_blockers_and_warnings() -> None:
    report = {
        "blockers": [{"code": "critical_supabase_url"}],
        "warnings": [{"code": "warn_openai_api_key"}, {"code": "warn_twilio_account_sid"}],
        "schema": {"ready": False},
    }
    scorecard = evaluate_preflight_core_values(report)

    assert scorecard["overall"] < 90
    assert scorecard["scores"]["reliability"] < 90
    assert len(scorecard["recommendations"]) >= 1


def test_scan_core_values_penalizes_stale_and_urgent_load() -> None:
    scan = {
        "requests": {"total": 7, "urgent": 2},
        "code_tasks": {"needs_review": 4, "stale": 3},
        "integrations": {"failed": ["supabase"], "all_healthy": False},
        "agent_activity": {"activity_count_48h": 5},
        "unread_messages": {"total": 6},
    }
    scorecard = evaluate_scan_core_values(scan)

    assert scorecard["scores"]["simplicity"] < 80
    assert scorecard["scores"]["reliability"] < 80
    assert scorecard["scores"]["owner_control"] < 90
    assert any("Reduce WIP" in line for line in scorecard["recommendations"])
