"""Background scheduler for Aria's daily 7 AM briefing SMS."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, tzinfo
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agents.aria.briefing_engine import AriaBriefingEngine
from config.settings import Settings, get_settings

logger = logging.getLogger("orb.aria.scheduler")


class AriaBriefingScheduler:
    """Runs Aria morning briefing once per day at configured local time."""

    def __init__(
        self,
        briefing_engine: AriaBriefingEngine | None = None,
        settings: Settings | None = None,
        now_provider: Callable[[], datetime] | None = None,
        sleep_seconds: int = 30,
    ):
        self.settings = settings or get_settings()
        self.briefing_engine = briefing_engine or AriaBriefingEngine()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.sleep_seconds = max(5, sleep_seconds)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_run_date: str | None = None

    def _resolve_timezone(self) -> tzinfo:
        """Resolve configured timezone; fall back to UTC if invalid."""
        try:
            return ZoneInfo(self.settings.aria_briefing_timezone)
        except (ZoneInfoNotFoundError, Exception):
            logger.warning(
                "Invalid aria_briefing_timezone=%s. Falling back to UTC.",
                self.settings.aria_briefing_timezone,
            )
            return timezone.utc

    def should_run_now(self, now_utc: datetime | None = None) -> bool:
        """Return True if scheduler should send today's briefing at this moment."""
        if not self.settings.aria_briefing_enabled:
            return False

        now_utc = now_utc or self.now_provider()
        tz = self._resolve_timezone()
        now_local = now_utc.astimezone(tz)

        if now_local.hour != self.settings.aria_briefing_hour:
            return False
        if now_local.minute != self.settings.aria_briefing_minute:
            return False

        run_date = now_local.date().isoformat()
        return run_date != self._last_run_date

    def run_once_if_due(self, now_utc: datetime | None = None) -> bool:
        """Run briefing once if current time matches configured schedule."""
        if not self.should_run_now(now_utc=now_utc):
            return False

        now_utc = now_utc or self.now_provider()
        run_date = now_utc.astimezone(self._resolve_timezone()).date().isoformat()

        try:
            result = self.briefing_engine.generate_and_send_briefing()
            if result.get("success"):
                logger.info("Aria morning briefing sent", extra={"date": run_date})
            else:
                logger.error(
                    "Aria morning briefing failed",
                    extra={"date": run_date, "error": result.get("send_error")},
                )
        except Exception as exc:
            logger.exception("Aria briefing scheduler crashed: %s", exc)
        finally:
            # Mark the day as attempted to prevent duplicate sends on the same date.
            self._last_run_date = run_date

        return True

    def start(self) -> None:
        """Start the scheduler loop in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        if not self.settings.aria_briefing_enabled:
            logger.info("Aria morning briefing scheduler disabled by configuration")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="aria-briefing-scheduler", daemon=True)
        self._thread.start()
        logger.info(
            "Aria morning briefing scheduler started",
            extra={
                "hour": self.settings.aria_briefing_hour,
                "minute": self.settings.aria_briefing_minute,
                "timezone": self.settings.aria_briefing_timezone,
            },
        )

    def stop(self) -> None:
        """Stop scheduler loop and join thread quickly."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("Aria morning briefing scheduler stopped")

    def _loop(self) -> None:
        """Polling loop that checks schedule at short intervals."""
        while not self._stop_event.is_set():
            self.run_once_if_due()
            time.sleep(self.sleep_seconds)

    def status(self) -> dict[str, str | int | bool | None]:
        """Return runtime scheduler diagnostics for debugging."""
        thread_alive = bool(self._thread and self._thread.is_alive())
        return {
            "enabled": self.settings.aria_briefing_enabled,
            "running": thread_alive,
            "hour": self.settings.aria_briefing_hour,
            "minute": self.settings.aria_briefing_minute,
            "timezone": self.settings.aria_briefing_timezone,
            "last_run_date": self._last_run_date,
        }
