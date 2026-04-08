"""Tests for Sage platform monitor scheduler."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from agents.sage.monitor_scheduler import SageMonitorScheduler
from config.settings import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings for scheduler tests."""
    settings = MagicMock(spec=Settings)
    settings.sage_monitor_enabled = True
    settings.sage_monitor_interval_minutes = 30
    return settings


@pytest.fixture
def mock_monitor():
    """Create a mock platform monitor."""
    monitor = MagicMock()
    monitor.monitor_platform_health.return_value = {
        "status": "healthy",
        "severity": "normal",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return monitor


def test_scheduler_initializes_with_defaults():
    """Test scheduler creates with default settings and monitor."""
    scheduler = SageMonitorScheduler()
    assert scheduler.monitor is not None
    assert scheduler.settings is not None
    assert scheduler.poll_interval_seconds >= 5


def test_should_run_now_returns_false_when_disabled(mock_settings, mock_monitor):
    """Test should_run_now returns False when monitor is disabled."""
    mock_settings.sage_monitor_enabled = False
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings)
    assert scheduler.should_run_now() is False


def test_should_run_now_returns_true_on_first_run(mock_settings, mock_monitor):
    """Test should_run_now returns True when never run before."""
    mock_settings.sage_monitor_enabled = True
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings)
    assert scheduler._last_run_time is None
    assert scheduler.should_run_now() is True


def test_should_run_now_respects_interval(mock_settings, mock_monitor):
    """Test should_run_now respects 30-minute interval."""
    mock_settings.sage_monitor_enabled = True
    mock_settings.sage_monitor_interval_minutes = 30
    
    now = datetime.now(timezone.utc)
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings, now_provider=lambda: now)
    
    # Set last run to 15 minutes ago (not yet due)
    scheduler._last_run_time = now - timedelta(minutes=15)
    assert scheduler.should_run_now() is False
    
    # Set last run to 35 minutes ago (now due)
    scheduler._last_run_time = now - timedelta(minutes=35)
    assert scheduler.should_run_now() is True


def test_run_once_if_due_executes_monitor(mock_settings, mock_monitor):
    """Test run_once_if_due calls monitor when due."""
    mock_settings.sage_monitor_enabled = True
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings)
    
    result = scheduler.run_once_if_due()
    assert result is True
    assert mock_monitor.monitor_platform_health.called
    assert scheduler._last_run_time is not None


def test_run_once_if_due_returns_false_when_not_due(mock_settings, mock_monitor):
    """Test run_once_if_due skips check when not due."""
    mock_settings.sage_monitor_enabled = True
    mock_settings.sage_monitor_interval_minutes = 30
    
    now = datetime.now(timezone.utc)
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings, now_provider=lambda: now)
    scheduler._last_run_time = now - timedelta(minutes=10)
    
    result = scheduler.run_once_if_due()
    assert result is False
    assert not mock_monitor.monitor_platform_health.called


def test_run_once_if_due_handles_errors_gracefully(mock_settings, mock_monitor):
    """Test run_once_if_due doesn't crash on monitor errors."""
    mock_settings.sage_monitor_enabled = True
    mock_monitor.monitor_platform_health.side_effect = RuntimeError("API error")
    
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings)
    result = scheduler.run_once_if_due()
    
    assert result is False
    assert scheduler._last_run_time is not None  # Updated despite error


def test_scheduler_thread_lifecycle(mock_settings, mock_monitor):
    """Test scheduler thread starts and stops properly."""
    mock_settings.sage_monitor_enabled = True
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings, poll_interval_seconds=1)
    
    assert scheduler._thread is None
    scheduler.start()
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()
    
    scheduler.stop()
    assert scheduler._thread is None


def test_status_returns_diagnostics(mock_settings, mock_monitor):
    """Test status() returns runtime diagnostics."""
    mock_settings.sage_monitor_enabled = True
    mock_settings.sage_monitor_interval_minutes = 30
    
    scheduler = SageMonitorScheduler(monitor=mock_monitor, settings=mock_settings)
    scheduler._last_run_time = datetime.now(timezone.utc)
    
    status = scheduler.status()
    assert status["enabled"] is True
    assert status["interval_minutes"] == 30
    assert status["running"] is False  # Not started
    assert status["last_run_utc"] is not None
