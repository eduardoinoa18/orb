"""Background scheduler for Sage's 30-minute platform health monitoring."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from agents.sage.platform_monitor import PlatformMonitor
from config.settings import Settings, get_settings

logger = logging.getLogger("orb.sage.scheduler")


class SageMonitorScheduler:
    """Runs Sage platform monitor check every 30 minutes in the background."""

    def __init__(
        self,
        monitor: PlatformMonitor | None = None,
        settings: Settings | None = None,
        now_provider: Callable[[], datetime] | None = None,
        poll_interval_seconds: int = 30,
    ):
        self.settings = settings or get_settings()
        self.monitor = monitor or PlatformMonitor()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.poll_interval_seconds = max(5, poll_interval_seconds)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_run_time: datetime | None = None

    def should_run_now(self, now_utc: datetime | None = None) -> bool:
        """Return True if 30+ minutes have passed since last run."""
        if not self.settings.sage_monitor_enabled:
            return False

        now_utc = now_utc or self.now_provider()

        # First run or 30+ minutes since last run
        if self._last_run_time is None:
            return True

        elapsed_seconds = (now_utc - self._last_run_time).total_seconds()
        return elapsed_seconds >= (self.settings.sage_monitor_interval_minutes * 60)

    def run_once_if_due(self) -> bool:
        """Executes monitor check if due; returns True if check ran."""
        if not self.should_run_now():
            return False

        try:
            now_utc = self.now_provider()
            logger.info("Running Sage platform monitor check...")
            result = self.monitor.monitor_platform_health()
            self._last_run_time = now_utc
            logger.info("Sage monitor check completed. Status: %s", result.get("status"))
            return True
        except Exception as error:
            logger.error("Sage monitor check failed: %s", error, exc_info=True)
            # Still update last run time so we don't spam retries
            self._last_run_time = self.now_provider()
            return False

    def start(self) -> None:
        """Start background polling thread (daemon)."""
        if self._thread is not None:
            logger.warning("Scheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()
        logger.info("Sage monitor scheduler started")

    def stop(self) -> None:
        """Stop background thread and wait for graceful shutdown."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=2)
        self._thread = None
        logger.info("Sage monitor scheduler stopped")

    def _polling_loop(self) -> None:
        """Background thread that polls every poll_interval_seconds."""
        while not self._stop_event.is_set():
            try:
                self.run_once_if_due()
            except Exception as error:
                logger.error("Unexpected error in Sage monitor polling loop: %s", error, exc_info=True)

            # Sleep in small intervals so stop() responds quickly
            self._stop_event.wait(timeout=self.poll_interval_seconds)

    def status(self) -> dict:
        """Return runtime diagnostics."""
        return {
            "enabled": self.settings.sage_monitor_enabled,
            "interval_minutes": self.settings.sage_monitor_interval_minutes,
            "running": self._thread is not None and self._thread.is_alive(),
            "last_run_utc": self._last_run_time.isoformat() if self._last_run_time else None,
        }
