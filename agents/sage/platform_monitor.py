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

# Only call Claude for diagnosis when truly infrastructure-critical issues arise.
# Config warnings like "Twilio not configured" are expected during early launch
# and do not warrant a paid API call every 30 minutes.
_CRITICAL_SIGNAL_KEYWORDS = ("Database", "API response", "Error rate", "Daily cost")


class PlatformMonitor:
    """Runs periodic platform checks and emits actionable diagnostics."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def monitor_platform_health(self) -> dict[str, Any]:
        """Checks latency/error/cost/webhooks and returns health diagnosis.

        Skips entirely when no owners exist to avoid burning API budget before
        the platform has any users.
        """
        # ── Early exit: no owners yet ──────────────────────────────────
        try:
            owners = self.db.client.table("owners").select("id").limit(1).execute()
            if not (owners.data or []):
                logger.debug("Sage monitor: no owners in database — skipping run.")
                return {
                    "status": "no_owners",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as err:
            logger.warning("Sage monitor: could not query owners table — skipping run: %s", err)
            return {
                "status": "skipped",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        # ── Normal run ─────────────────────────────────────────────────
        dependency_health = self._check_dependency_health()
        database_connected = self._check_database_connected()

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

        unhealthy: list[str] = []
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
        severity = (
            "critical"
            if any("Database" in x or "exceeds" in x for x in unhealthy)
            else ("high" if unhealthy else "normal")
        )

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
            logger.warning(
                "Skipping Sage activity log write because database is unavailable: %s", error
            )

        return {
            "status": "healthy" if not unhealthy else "attention_needed",
            "severity": severity,
            "metrics": metrics,
            "unhealthy_signals": unhealthy,
            "diagnosis": diagnosis,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Dependency health — config-key checks ONLY (no live API calls)
    # ------------------------------------------------------------------

    def _check_dependency_health(self) -> dict[str, dict[str, str]]:
        """Checks that required credentials are configured.

        Deliberately avoids live API calls (Claude, OpenAI, Twilio) on every
        30-minute cycle.  A missing key means the integration is not yet set up,
        which is expected during early launch and not worth a paid diagnostic call.
        """
        results: dict[str, dict[str, str]] = {
            "supabase": {"status": "healthy", "reason": "ok"},
            "anthropic": {"status": "healthy", "reason": "ok"},
            "openai": {"status": "healthy", "reason": "ok"},
            "twilio": {"status": "healthy", "reason": "ok"},
        }

        # Supabase — lightweight ping via the shared database wrapper so tests
        # can mock the abstraction layer without needing a live client.
        try:
            self.db.fetch_all("owners")
        except Exception as error:
            results["supabase"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # Anthropic — key presence only
        try:
            settings = get_settings()
            if not getattr(settings, "anthropic_api_key", None):
                results["anthropic"] = {"status": "unhealthy", "reason": "ANTHROPIC_API_KEY not set"}
        except Exception as error:
            results["anthropic"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # OpenAI — key presence only
        try:
            settings = get_settings()
            if not getattr(settings, "openai_api_key", None):
                results["openai"] = {"status": "unhealthy", "reason": "OPENAI_API_KEY not set"}
        except Exception as error:
            results["openai"] = {"status": "unhealthy", "reason": str(error)[:80]}

        # Twilio — key presence only (no outbound message sent)
        try:
            settings = get_settings()
            missing = [
                k for k in ("twilio_account_sid", "twilio_auth_token", "twilio_phone_number")
                if not getattr(settings, k, None)
            ]
            if missing:
                results["twilio"] = {
                    "status": "unhealthy",
                    "reason": f"Missing: {', '.join(missing)}",
                }
        except Exception as error:
            results["twilio"] = {"status": "unhealthy", "reason": str(error)[:80]}

        return results

    # ------------------------------------------------------------------
    # Metric estimators — all use bounded queries (LIMIT 200)
    # ------------------------------------------------------------------

    def _estimate_api_response_time_ms(self) -> int:
        rows = self._safe_fetch_recent("activity_log", limit=200)
        durations = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            value = metadata.get("duration_ms")
            if isinstance(value, (int, float)):
                durations.append(float(value))
        if not durations:
            return 350
        sample = durations[-50:]
        return int(sum(sample) / len(sample))

    def _estimate_error_rate_percent(self) -> float:
        rows = self._safe_fetch_recent("activity_log", limit=200)
        if not rows:
            return 0.0
        error_count = sum(
            1 for row in rows if "error" in str(row.get("outcome") or "").lower()
        )
        return round((error_count / len(rows)) * 100, 2)

    def _check_database_connected(self) -> bool:
        try:
            self.db.client.table("owners").select("id").limit(1).execute()
            return True
        except Exception:
            return False

    def _estimate_webhook_success_rate(self) -> float:
        rows = [
            row
            for row in self._safe_fetch_recent("activity_log", limit=200)
            if "webhook" in str(row.get("action_type") or "").lower()
        ]
        if not rows:
            return 100.0
        success = sum(
            1
            for row in rows
            if str(row.get("outcome") or "").lower() in {"success", "accepted", "processed"}
        )
        return round((success / len(rows)) * 100, 2)

    def _estimate_daily_cost_dollars(self) -> float:
        rows = self._safe_fetch_recent("activity_log", limit=200)
        return round(sum(int(row.get("cost_cents") or 0) for row in rows) / 100, 2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_fetch_recent(self, table_name: str, limit: int = 200) -> list[dict[str, Any]]:
        """Fetches the most recent `limit` rows from `table_name`.

        Uses a direct bounded query instead of fetch_all() to avoid SELECT *
        on potentially large tables.
        """
        try:
            response = (
                self.db.client.table(table_name)
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception:
            return []

    def _diagnose(self, unhealthy: list[str], metrics: dict[str, Any]) -> dict[str, str]:
        """Returns a diagnosis dict.

        Only calls Claude when truly infrastructure-critical signals are present
        (e.g. database down, API latency spiking, costs exceeding budget).
        Config warnings like 'Twilio not configured' are handled locally.
        """
        if not unhealthy:
            return {
                "what_is_wrong": "No critical issues detected.",
                "likely_cause": "Platform operating within thresholds.",
                "how_to_fix": "Continue monitoring every 30 minutes.",
                "priority": "normal",
            }

        # Only escalate to Claude for signals that are truly infrastructure issues.
        critical_signals = [
            s for s in unhealthy
            if any(kw in s for kw in _CRITICAL_SIGNAL_KEYWORDS)
        ]

        if not critical_signals:
            # Config/setup warnings only — no need for a paid API call.
            return {
                "what_is_wrong": "; ".join(unhealthy),
                "likely_cause": "One or more integrations are not yet configured.",
                "how_to_fix": "Set the missing environment variables in Railway and redeploy.",
                "priority": "low",
            }

        # Truly critical — worth asking Claude once.
        prompt = (
            "Generate a concise platform diagnosis JSON with exactly these keys: "
            "what_is_wrong, likely_cause, how_to_fix, priority.\n"
            f"Critical signals: {critical_signals}\nAll metrics: {metrics}"
        )
        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are Sage, a SaaS operations expert. Reply with valid JSON only.",
                max_tokens=300,
            )
            import json
            parsed = json.loads(result["text"])
            return {
                "what_is_wrong": str(parsed.get("what_is_wrong") or "Multiple health checks are out of range."),
                "likely_cause": str(parsed.get("likely_cause") or "Resource saturation or integration instability."),
                "how_to_fix": str(parsed.get("how_to_fix") or "Prioritize failed integrations and reduce non-urgent load."),
                "priority": str(parsed.get("priority") or "high"),
            }
        except Exception:
            return {
                "what_is_wrong": "; ".join(critical_signals),
                "likely_cause": "One or more core dependencies are unstable.",
                "how_to_fix": "Check Railway logs and resolve the highest-severity failing check first.",
                "priority": "high",
            }
