"""Tests for Aria 7:00 AM briefing scheduler."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from agents.aria.briefing_scheduler import AriaBriefingScheduler


def _make_settings(enabled: bool = True, hour: int = 7, minute: int = 0, tz: str = "UTC"):
    settings = MagicMock()
    settings.aria_briefing_enabled = enabled
    settings.aria_briefing_hour = hour
    settings.aria_briefing_minute = minute
    settings.aria_briefing_timezone = tz
    return settings


def test_should_run_now_true_at_exact_time():
    engine = MagicMock()
    settings = _make_settings(hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    assert scheduler.should_run_now(now_utc) is True


def test_should_run_now_false_at_wrong_minute():
    engine = MagicMock()
    settings = _make_settings(hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 1, tzinfo=timezone.utc)
    assert scheduler.should_run_now(now_utc) is False


def test_run_once_if_due_calls_generate_and_send_briefing():
    engine = MagicMock()
    engine.generate_and_send_briefing.return_value = {"success": True}
    settings = _make_settings(hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    ran = scheduler.run_once_if_due(now_utc)

    assert ran is True
    engine.generate_and_send_briefing.assert_called_once()


def test_run_once_if_due_only_once_per_day():
    engine = MagicMock()
    engine.generate_and_send_briefing.return_value = {"success": True}
    settings = _make_settings(hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    first = scheduler.run_once_if_due(now_utc)
    second = scheduler.run_once_if_due(now_utc)

    assert first is True
    assert second is False
    engine.generate_and_send_briefing.assert_called_once()


def test_run_once_if_due_runs_again_next_day():
    engine = MagicMock()
    engine.generate_and_send_briefing.return_value = {"success": True}
    settings = _make_settings(hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    day1 = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 2, 7, 0, tzinfo=timezone.utc)

    assert scheduler.run_once_if_due(day1) is True
    assert scheduler.run_once_if_due(day2) is True
    assert engine.generate_and_send_briefing.call_count == 2


def test_scheduler_disabled_never_runs():
    engine = MagicMock()
    settings = _make_settings(enabled=False, hour=7, minute=0, tz="UTC")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    assert scheduler.run_once_if_due(now_utc) is False
    engine.generate_and_send_briefing.assert_not_called()


def test_invalid_timezone_falls_back_to_utc():
    engine = MagicMock()
    engine.generate_and_send_briefing.return_value = {"success": True}
    settings = _make_settings(hour=7, minute=0, tz="Bad/Timezone")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    now_utc = datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc)
    assert scheduler.run_once_if_due(now_utc) is True
    engine.generate_and_send_briefing.assert_called_once()


def test_status_shape_contains_schedule_config():
    engine = MagicMock()
    settings = _make_settings(hour=7, minute=0, tz="America/New_York")
    scheduler = AriaBriefingScheduler(briefing_engine=engine, settings=settings)

    status = scheduler.status()

    assert status["enabled"] is True
    assert status["hour"] == 7
    assert status["minute"] == 0
    assert status["timezone"] == "America/New_York"
