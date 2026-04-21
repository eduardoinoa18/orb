from types import SimpleNamespace
from unittest.mock import patch

from app.runtime.preflight import build_preflight_report


def test_preflight_report_ready_when_schema_and_critical_values_are_good() -> None:
    fake_settings = SimpleNamespace(
        supabase_url="https://orb-prod.supabase.co",
        supabase_service_key="service-key-real",
        anthropic_api_key="sk-ant-real",
        openai_api_key="sk-openai-real",
        twilio_account_sid="AC123456789",
        twilio_auth_token="auth-token-real",
        stripe_secret_key="sk_live_real",
    )

    with patch("app.runtime.preflight.get_settings", return_value=fake_settings), patch(
        "app.runtime.preflight.schema_readiness_payload", return_value={"ready": True, "checks": []}
    ):
        report = build_preflight_report()

    assert report["ready"] is True
    assert report["summary"]["blocker_count"] == 0
    assert report["score"] == 100
    assert "core_values" in report
    assert "overall" in report["core_values"]
    assert "scores" in report["core_values"]


def test_preflight_report_includes_schema_blocker_when_not_ready() -> None:
    fake_settings = SimpleNamespace(
        supabase_url="https://orb-prod.supabase.co",
        supabase_service_key="service-key-real",
        anthropic_api_key="sk-ant-real",
        openai_api_key="openai-placeholder",
        twilio_account_sid="placeholder",
        twilio_auth_token="placeholder",
        stripe_secret_key="",
    )

    with patch("app.runtime.preflight.get_settings", return_value=fake_settings), patch(
        "app.runtime.preflight.schema_readiness_payload", return_value={"ready": False, "checks": []}
    ):
        report = build_preflight_report()

    assert report["ready"] is False
    assert report["summary"]["blocker_count"] >= 1
    assert any(item.get("code") == "schema_not_ready" for item in report["blockers"])
    assert report["core_values"]["overall"] < 100
