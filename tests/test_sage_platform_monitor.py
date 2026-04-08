"""Unit tests for Sage platform monitor dependency health checks."""

from unittest.mock import MagicMock, patch

from agents.sage.platform_monitor import PlatformMonitor


def test_monitor_platform_health_healthy_path() -> None:
    """Monitor reports healthy when metrics and dependencies are all in range."""
    monitor = PlatformMonitor()

    with patch.object(monitor, "_estimate_api_response_time_ms", return_value=220):
        with patch.object(monitor, "_estimate_error_rate_percent", return_value=1.2):
            with patch.object(monitor, "_check_database_connected", return_value=True):
                with patch.object(monitor, "_estimate_webhook_success_rate", return_value=99.0):
                    with patch.object(monitor, "_estimate_daily_cost_dollars", return_value=2.4):
                        with patch.object(monitor, "_check_dependency_health", return_value={
                            "supabase": {"status": "healthy", "reason": "ok"},
                            "anthropic": {"status": "healthy", "reason": "ok"},
                            "openai": {"status": "healthy", "reason": "ok"},
                            "twilio": {"status": "healthy", "reason": "ok"},
                        }):
                            with patch.object(monitor.db, "log_activity"):
                                result = monitor.monitor_platform_health()

    assert result["status"] == "healthy"
    assert result["severity"] == "normal"
    assert result["unhealthy_signals"] == []
    assert result["metrics"]["dependency_health"]["openai"]["status"] == "healthy"


def test_monitor_platform_health_flags_unhealthy_dependencies() -> None:
    """Monitor includes dependency failures in unhealthy signals and raises severity."""
    monitor = PlatformMonitor()

    with patch.object(monitor, "_estimate_api_response_time_ms", return_value=150):
        with patch.object(monitor, "_estimate_error_rate_percent", return_value=0.5):
            with patch.object(monitor, "_check_database_connected", return_value=True):
                with patch.object(monitor, "_estimate_webhook_success_rate", return_value=99.0):
                    with patch.object(monitor, "_estimate_daily_cost_dollars", return_value=1.0):
                        with patch.object(monitor, "_check_dependency_health", return_value={
                            "supabase": {"status": "healthy", "reason": "ok"},
                            "anthropic": {"status": "unhealthy", "reason": "timeout"},
                            "openai": {"status": "healthy", "reason": "ok"},
                            "twilio": {"status": "unhealthy", "reason": "missing credentials"},
                        }):
                            with patch.object(monitor.db, "log_activity"):
                                result = monitor.monitor_platform_health()

    assert result["status"] == "attention_needed"
    assert result["severity"] == "high"
    signals = " | ".join(result["unhealthy_signals"]).lower()
    assert "dependency unhealthy: anthropic" in signals
    assert "dependency unhealthy: twilio" in signals


def test_check_dependency_health_reports_config_errors() -> None:
    """Dependency health marks integrations unhealthy when required calls raise."""
    monitor = PlatformMonitor()

    with patch.object(monitor.db, "fetch_all", side_effect=RuntimeError("db down")):
        with patch("agents.sage.platform_monitor.ask_claude_smart", side_effect=RuntimeError("anthropic down")):
            with patch("agents.sage.platform_monitor.ask_gpt_mini", side_effect=RuntimeError("openai down")):
                mock_settings = MagicMock()
                mock_settings.require.side_effect = RuntimeError("missing twilio key")
                with patch("agents.sage.platform_monitor.get_settings", return_value=mock_settings):
                    result = monitor._check_dependency_health()

    assert result["supabase"]["status"] == "unhealthy"
    assert result["anthropic"]["status"] == "unhealthy"
    assert result["openai"]["status"] == "unhealthy"
    assert result["twilio"]["status"] == "unhealthy"
