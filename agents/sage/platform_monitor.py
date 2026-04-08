"""Sage platform monitoring (Addendum S1 starter)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.anthropic_client import ask_claude_smart
from integrations.openai_client import ask_gpt_mini
from config.settings import get_settings


logger = logging.getLogger("orb.sage.platform_monitor")


class PlatformMonitor:
    """Runs periodic platform checks and emits actionable diagnostics."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def monitor_platform_health(self) -> dict[str, Any]:
        """Checks latency/error/cost/webhooks and returns health diagnosis."""
        dependency_health = self._check_dependency_health()
        database_connected = self._check_database_connected()

        # Avoid repeated failing DB reads when permissions are unavailable.
        if database_connected:
            api_response_ms = self._estimate_api_response_time_ms()
            error_rate_percent = self._estimate_error_rate_percent()
            webhook_success_percent = self._estimate_webhook_success_rate()
            daily_cost_dollars = self._estimate_daily_cost_dollars()
        else:
            api_response_ms = 350
            error_rate_percent = 0.0
            webhook_success_percent = 0.0
            daily_cost_dollars = 0.0

        metrics = {
            "api_response_ms": api_response_ms,
            "error_rate_percent": error_rate_percent,
            "database_connected": database_connected,
            "webhook_success_percent": webhook_success_percent,
            "daily_cost_dollars": daily_cost_dollars,
            "dependency_health": dependency_health,
        }

        unhealthy = []
        if metrics["api_response_ms"] > 2000:
            unhealthy.append("API response time exceeds 2 seconds")
        if metrics["error_rate_percent"] > 5:
            unhealthy.append("Error rate exceeds 5%")
        if not metrics["database_connected"]:
            unhealthy.append("Database connection is unstable")
        if metrics["webhook_success_percent"] < 95:
            unhealthy.append("Webhook success rate below 95%")
        if metrics["daily_cost_dollars"] > 15:
            unhealthy.append("Daily cost exceeded $15 budget")
        for name, status in dependency_health.items():
            if status.get("status") != "healthy":
                reason = status.get("reason") or "dependency check failed"
                unhealthy.append(f"Dependency unhealthy: {name} ({reason})")

        diagnosis = self._diagnose(unhealthy, metrics)
        severity = "critical" if any("Database" in x or "exceeds" in x for x in unhealthy) else ("high" if unhealthy else "normal")

        try:
            self.db.log_activity(
                agent_id=None,
                owner_id=None,
                action_type="sage_platform_monitor",
                description="Sage completed 30-minute platform health scan.",
                cost_cents=0,
                outcome="healthy" if not unhealthy else "attention_needed",
                metadata={
                    "metrics": metrics,
                    "diagnosis": diagnosis,
                    "severity": severity,
                },
            )
        except DatabaseConnectionError as error:
            logger.warning("Skipping Sage activity log write because database is unavailable: %s", error)

        return {
            "status": "healthy" if not unhealthy else "attention_needed",
            "severity": severity,
            "metrics": metrics,
            "unhealthy_signals": unhealthy,
            "diagnosis": diagnosis,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def _check_dependency_health(self) -> dict[str, dict[str, str]]:
        """Performs lightweight checks for core ORB integrations used in production."""
        results: dict[str, dict[str, str]] = {
            "supabase": {"status": "healthy", "reason": "ok"},
            "anthropic": {"status": "healthy", "reason": "ok"},
            "openai": {"status": "healthy", "reason": "ok"},
            "twilio": {"status": "healthy", "reason": "ok"},
        }

        # Supabase
        try:
            self.db.fetch_all("owners")
        except Exception as error:
            results["supabase"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # Anthropic
        try:
            ask_claude_smart(
                prompt="health check: reply with 'ok'",
                system="You are a health check service.",
                max_tokens=12,
                task_type="short_analysis",
                max_budget_cents=1,
                is_critical=True,
            )
        except Exception as error:
            results["anthropic"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # OpenAI
        try:
            ask_gpt_mini(
                prompt="health check: reply with ok",
                system="You are a health check service.",
                max_tokens=12,
                task_type="short_analysis",
                max_budget_cents=1,
                is_critical=True,
            )
        except Exception as error:
            results["openai"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # Twilio configuration sanity check (no outbound message sent)
        try:
            settings = get_settings()
            settings.require("twilio_account_sid")
            settings.require("twilio_auth_token")
            settings.require("twilio_phone_number")
        except Exception as error:
            results["twilio"] = {"status": "unhealthy", "reason": str(error)[:80]}

        return results

    def _estimate_api_response_time_ms(self) -> int:
        rows = self._safe_fetch("activity_log")
        durations = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            value = metadata.get("duration_ms")
            if isinstance(value, (int, float)):
                durations.append(float(value))
        if not durations:
            return 350
        return int(sum(durations[-50:]) / len(durations[-50:]))

    def _estimate_error_rate_percent(self) -> float:
        rows = self._safe_fetch("activity_log")
        if not rows:
            return 0.0
        error_count = sum(1 for row in rows if "error" in str(row.get("outcome") or "").lower())
        return round((error_count / len(rows)) * 100, 2)

    def _check_database_connected(self) -> bool:
        try:
            self.db.fetch_all("owners")
            return True
        except DatabaseConnectionError:
            return False

    def _estimate_webhook_success_rate(self) -> float:
        rows = [row for row in self._safe_fetch("activity_log") if "webhook" in str(row.get("action_type") or "").lower()]
        if not rows:
            return 100.0
        success = sum(1 for row in rows if str(row.get("outcome") or "").lower() in {"success", "accepted", "processed"})
        return round((success / len(rows)) * 100, 2)

    def _estimate_daily_cost_dollars(self) -> float:
        rows = self._safe_fetch("activity_log")
        return round(sum(int(row.get("cost_cents") or 0) for row in rows) / 100, 2)

    def _safe_fetch(self, table_name: str) -> list[dict[str, Any]]:
        try:
            return self.db.fetch_all(table_name)
        except DatabaseConnectionError:
            return []

    def _diagnose(self, unhealthy: list[str], metrics: dict[str, Any]) -> dict[str, str]:
        if not unhealthy:
            return {
                "what_is_wrong": "No critical issues detected.",
                "likely_cause": "Platform operating within thresholds.",
                "how_to_fix": "Continue monitoring every 30 minutes.",
                "priority": "normal",
            }

        prompt = (
            "Generate concise platform diagnosis JSON with keys what_is_wrong, likely_cause, "
            "how_to_fix, priority.\n"
            f"Unhealthy signals: {unhealthy}\nMetrics: {metrics}"
        )
        try:
            result = ask_claude_smart(prompt=prompt, system="You are Sage, a SaaS operations expert.", max_tokens=300)
            parsed = __import__("json").loads(result["text"])
            return {
                "what_is_wrong": str(parsed.get("what_is_wrong") or "Multiple health checks are out of range."),
                "likely_cause": str(parsed.get("likely_cause") or "Resource saturation or integration instability."),
                "how_to_fix": str(parsed.get("how_to_fix") or "Prioritize failed integrations and reduce non-urgent load."),
                "priority": str(parsed.get("priority") or "high"),
            }
        except Exception:
            return {
                "what_is_wrong": "; ".join(unhealthy),
                "likely_cause": "One or more dependencies are unstable.",
                "how_to_fix": "Check logs, then resolve the highest-severity failing check first.",
                "priority": "high",
            }
