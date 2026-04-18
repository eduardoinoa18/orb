"""Platform Soft-Check Engine — ORB's always-on background scanner.

This is the "heartbeat" of the self-improving platform. It runs on a schedule
(every 15 min via Railway cron or APScheduler) and proactively scans for:

  1. Pending platform requests that need Eduardo's attention
  2. Stalled code tasks (picked_up for too long without submission)
  3. Unread inter-agent messages
  4. Failed or degraded integrations
  5. Overdue agent self-improvement reviews
  6. Pending approval tasks in review
  7. User activity anomalies (agents that haven't checked in)

The scanner then:
  - Pushes a compact status into the agent_messages table for Eduardo's Commander
  - Optionally triggers WhatsApp or Telegram notifications for urgent items
  - Updates a platform_status record for the admin dashboard
  - Triggers self-improvement cycles for agents that are due

Eduardo never has to manually check anything — the platform tells him what
needs his attention, what's running smoothly, and what just shipped.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("orb.platform_scan")


class PlatformScanner:
    """Runs soft-check scans across the entire ORB platform."""

    STALE_TASK_HOURS = 24       # code task picked_up but not submitted
    SELF_REVIEW_DAYS = 7        # how often each agent should self-review
    MAX_DIGEST_ITEMS = 10       # items per section in digest

    def __init__(self) -> None:
        self._db = None
        self._admin_id: str | None = None

    @staticmethod
    def _is_missing_table_error(error: Exception) -> bool:
        """Detect missing-table errors from Supabase/PostgREST responses."""
        message = str(error)
        return "PGRST205" in message or "Could not find the table" in message

    def _get_db(self):
        if self._db is None:
            try:
                from app.database.connection import SupabaseService
                self._db = SupabaseService()
            except Exception:
                pass
        return self._db

    def _get_admin_id(self) -> str | None:
        """Finds the platform admin (Eduardo) owner_id."""
        if self._admin_id:
            return self._admin_id
        db = self._get_db()
        if not db:
            return None
        try:
            rows = db.client.table("business_profiles") \
                .select("owner_id") \
                .eq("is_platform_admin", True) \
                .limit(1) \
                .execute()
            if rows.data:
                self._admin_id = rows.data[0]["owner_id"]
                return self._admin_id
            # Fallback: check owners table for superadmin
            rows2 = db.client.table("owners") \
                .select("id") \
                .eq("is_superadmin", True) \
                .limit(1) \
                .execute()
            if rows2.data:
                self._admin_id = rows2.data[0]["id"]
                return self._admin_id
        except Exception:
            pass
        return None

    # ── Scan modules ──────────────────────────────────────────────────────────

    def scan_pending_requests(self) -> dict[str, Any]:
        """Counts pending platform requests by priority."""
        db = self._get_db()
        if not db:
            return {"total": 0, "urgent": 0, "items": []}
        try:
            rows = db.client.table("platform_requests") \
                .select("id,title,priority,request_type,created_at,requester_id") \
                .in_("status", ["pending", "acknowledged"]) \
                .order("created_at", desc=True) \
                .limit(self.MAX_DIGEST_ITEMS) \
                .execute()
            items = rows.data or []
            urgent = [r for r in items if str(r.get("priority", "")).lower() in {"high", "urgent"}]
            return {"total": len(items), "urgent": len(urgent), "items": items}
        except Exception as e:
            if self._is_missing_table_error(e):
                logger.info("scan_pending_requests skipped: platform_requests table not available yet")
                return {"total": 0, "urgent": 0, "items": [], "available": False}
            logger.warning("scan_pending_requests failed: %s", e)
            return {"total": 0, "urgent": 0, "items": [], "error": str(e)}

    def scan_code_tasks(self) -> dict[str, Any]:
        """Finds code tasks that need attention: stale, needs_review, or failed."""
        db = self._get_db()
        if not db:
            return {"needs_review": 0, "stale": 0, "items": []}
        try:
            stale_cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.STALE_TASK_HOURS)).isoformat()

            # Needs review
            review_rows = db.client.table("platform_tasks") \
                .select("id,title,status,created_at,picked_up_at") \
                .eq("status", "needs_review") \
                .order("created_at", desc=True) \
                .limit(10) \
                .execute()

            # Stale (picked_up but not submitted)
            stale_rows = db.client.table("platform_tasks") \
                .select("id,title,status,picked_up_at,assigned_to") \
                .eq("status", "picked_up") \
                .lt("picked_up_at", stale_cutoff) \
                .limit(5) \
                .execute()

            return {
                "needs_review": len(review_rows.data or []),
                "stale": len(stale_rows.data or []),
                "items_review": review_rows.data or [],
                "items_stale": stale_rows.data or [],
            }
        except Exception as e:
            if self._is_missing_table_error(e):
                logger.info("scan_code_tasks skipped: platform_tasks table not available yet")
                return {
                    "needs_review": 0,
                    "stale": 0,
                    "items_review": [],
                    "items_stale": [],
                    "available": False,
                }
            logger.warning("scan_code_tasks failed: %s", e)
            return {"needs_review": 0, "stale": 0, "items_review": [], "items_stale": [], "error": str(e)}

    def scan_unread_messages(self, owner_id: str) -> dict[str, Any]:
        """Counts unread inter-agent messages for an owner."""
        db = self._get_db()
        if not db:
            return {"total": 0, "items": []}
        try:
            rows = db.client.table("agent_messages") \
                .select("id,subject,message_type,from_owner_id,created_at") \
                .eq("to_owner_id", owner_id) \
                .eq("is_read", False) \
                .order("created_at", desc=True) \
                .limit(self.MAX_DIGEST_ITEMS) \
                .execute()
            return {"total": len(rows.data or []), "items": rows.data or []}
        except Exception as e:
            logger.warning("scan_unread_messages failed: %s", e)
            return {"total": 0, "items": [], "error": str(e)}

    def scan_integration_health(self) -> dict[str, Any]:
        """Checks if critical env vars / integrations are configured."""
        required_checks = {
            "anthropic":    bool(os.environ.get("ANTHROPIC_API_KEY")),
            "supabase":     bool(
                os.environ.get("SUPABASE_URL")
                and (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY"))
            ),
        }
        optional_checks = {
            "openai":       bool(os.environ.get("OPENAI_API_KEY")),
            "elevenlabs":   bool(os.environ.get("ELEVENLABS_API_KEY")),
            "twilio":       bool(os.environ.get("TWILIO_ACCOUNT_SID")),
            "telegram":     bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "deploy_webhook": bool(os.environ.get("RAILWAY_DEPLOY_WEBHOOK") or os.environ.get("DEPLOY_WEBHOOK_URL")),
        }
        checks = {**required_checks, **optional_checks}
        failed_required = [k for k, v in required_checks.items() if not v]
        missing_optional = [k for k, v in optional_checks.items() if not v]
        return {
            "all_healthy": len(failed_required) == 0,
            "checks": checks,
            "failed": failed_required,
            "missing_optional": missing_optional,
            "configured": [k for k, v in checks.items() if v],
        }

    def scan_agent_activity(self) -> dict[str, Any]:
        """Checks if platform agents have been active recently."""
        db = self._get_db()
        if not db:
            return {"active_agents": [], "stale_agents": []}
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
            rows = db.client.table("activity_log") \
                .select("agent_id,action_type,created_at") \
                .gte("created_at", cutoff) \
                .order("created_at", desc=True) \
                .limit(100) \
                .execute()
            items = rows.data or []
            active = list({r["agent_id"] for r in items if r.get("agent_id")})
            return {"active_agents": active, "activity_count_48h": len(items)}
        except Exception as e:
            logger.warning("scan_agent_activity failed: %s", e)
            return {"active_agents": [], "activity_count_48h": 0, "error": str(e)}

    def scan_platform_stats(self) -> dict[str, Any]:
        """Quick aggregate: owners, active agents, total requests."""
        db = self._get_db()
        if not db:
            return {}
        try:
            owners_row = db.client.table("owners").select("id", count="exact").execute()
            tasks_row = db.client.table("platform_tasks").select("status").execute()
            tasks = tasks_row.data or []
            return {
                "total_owners": owners_row.count or 0,
                "tasks_deployed": sum(1 for t in tasks if t["status"] == "deployed"),
                "tasks_pending": sum(1 for t in tasks if t["status"] == "pending"),
                "tasks_total": len(tasks),
            }
        except Exception as e:
            if self._is_missing_table_error(e):
                logger.info("scan_platform_stats partial fallback: platform_tasks table not available yet")
                try:
                    owners_row = db.client.table("owners").select("id", count="exact").execute()
                    return {
                        "total_owners": owners_row.count or 0,
                        "tasks_deployed": 0,
                        "tasks_pending": 0,
                        "tasks_total": 0,
                        "tasks_available": False,
                    }
                except Exception:
                    return {"tasks_available": False}
            logger.warning("scan_platform_stats failed: %s", e)
            return {}

    # ── Full scan + digest ────────────────────────────────────────────────────

    def run_full_scan(self) -> dict[str, Any]:
        """Runs all scan modules and returns a unified status report."""
        logger.info("Platform soft-check scan starting...")
        admin_id = self._get_admin_id()

        scan_result = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "admin_id": admin_id,
            "requests": self.scan_pending_requests(),
            "code_tasks": self.scan_code_tasks(),
            "integrations": self.scan_integration_health(),
            "agent_activity": self.scan_agent_activity(),
            "platform_stats": self.scan_platform_stats(),
            "unread_messages": self.scan_unread_messages(admin_id) if admin_id else {"total": 0, "items": []},
        }

        # Build urgency score
        urgency = 0
        if scan_result["requests"]["urgent"] > 0:
            urgency += scan_result["requests"]["urgent"] * 2
        if scan_result["code_tasks"]["needs_review"] > 0:
            urgency += scan_result["code_tasks"]["needs_review"]
        if scan_result["code_tasks"]["stale"] > 0:
            urgency += scan_result["code_tasks"]["stale"] * 3
        if not scan_result["integrations"]["all_healthy"]:
            urgency += 5
        if scan_result["unread_messages"]["total"] > 0:
            urgency += scan_result["unread_messages"]["total"]

        scan_result["urgency_score"] = urgency
        scan_result["needs_attention"] = urgency > 0

        logger.info(
            "Platform scan complete — urgency=%d needs_attention=%s",
            urgency, scan_result["needs_attention"],
        )
        return scan_result

    def build_digest_message(self, scan: dict[str, Any]) -> str:
        """Converts a scan result into a readable digest message for Eduardo."""
        now = datetime.now(timezone.utc).strftime("%b %d %I:%M %p UTC")
        lines = [f"🔍 ORB Platform Scan — {now}"]

        # Requests
        req = scan.get("requests", {})
        if req.get("total", 0) > 0:
            lines.append(f"\n📥 Platform Requests: {req['total']} pending" +
                         (f" ({req['urgent']} URGENT)" if req.get("urgent") else ""))
            for r in req.get("items", [])[:3]:
                lines.append(f"  • [{r.get('priority','?').upper()}] {r.get('title','Untitled')}")

        # Code tasks
        ct = scan.get("code_tasks", {})
        if ct.get("needs_review", 0) > 0:
            lines.append(f"\n✅ Code Tasks Awaiting Review: {ct['needs_review']}")
            for t in ct.get("items_review", [])[:3]:
                lines.append(f"  • {t.get('title','Untitled')}")
        if ct.get("stale", 0) > 0:
            lines.append(f"\n⚠️ Stale Code Tasks (>{self.STALE_TASK_HOURS}h): {ct['stale']}")

        # Unread messages
        msgs = scan.get("unread_messages", {})
        if msgs.get("total", 0) > 0:
            lines.append(f"\n💬 Unread Agent Messages: {msgs['total']}")

        # Integration health
        integrations = scan.get("integrations", {})
        if not integrations.get("all_healthy"):
            failed = integrations.get("failed", [])
            lines.append(f"\n🔴 Integrations Not Configured: {', '.join(failed)}")
        elif integrations.get("missing_optional"):
            optional = integrations.get("missing_optional", [])
            lines.append(f"\n🟡 Optional Integrations Not Configured: {', '.join(optional)}")

        # Stats
        stats = scan.get("platform_stats", {})
        if stats:
            lines.append(
                f"\n📊 Platform: {stats.get('total_owners', 0)} owners · "
                f"{stats.get('tasks_deployed', 0)} tasks deployed · "
                f"{stats.get('tasks_pending', 0)} pending"
            )

        # All clear
        if not scan.get("needs_attention"):
            lines.append("\n✅ All clear — platform running smoothly.")

        return "\n".join(lines)

    def push_digest_to_commander(self, scan: dict[str, Any]) -> bool:
        """Posts the digest as an agent_message to Eduardo's Commander inbox."""
        admin_id = self._get_admin_id()
        if not admin_id:
            logger.warning("push_digest_to_commander: no admin_id found")
            return False
        db = self._get_db()
        if not db:
            return False
        try:
            digest = self.build_digest_message(scan)
            db.client.table("agent_messages").insert({
                "from_owner_id": admin_id,
                "to_owner_id": admin_id,
                "from_agent_type": "platform_scanner",
                "to_agent_type": "commander",
                "message_type": "platform_digest",
                "subject": f"Platform Scan — Urgency {scan.get('urgency_score', 0)}",
                "body": digest,
                "payload": {
                    "urgency_score": scan.get("urgency_score", 0),
                    "needs_attention": scan.get("needs_attention", False),
                    "scanned_at": scan.get("scanned_at"),
                },
            }).execute()
            logger.info("Platform digest pushed to Commander inbox")
            return True
        except Exception as e:
            logger.error("Failed to push digest: %s", e)
            return False

    def push_urgent_notification(self, scan: dict[str, Any]) -> bool:
        """Sends urgent items via WhatsApp or Telegram if configured."""
        if scan.get("urgency_score", 0) < 5:
            return False  # Only push for genuinely urgent situations

        message = self.build_digest_message(scan)

        # Try WhatsApp via Twilio
        sent = False
        try:
            _twilio_send(message)
            sent = True
        except Exception as e:
            logger.debug("WhatsApp push skipped: %s", e)

        # Try Telegram
        if not sent:
            try:
                _telegram_send(message)
                sent = True
            except Exception as e:
                logger.debug("Telegram push skipped: %s", e)

        return sent

    def run_and_notify(self) -> dict[str, Any]:
        """Full scan + push digest + urgent notification. Call from cron/scheduler."""
        scan = self.run_full_scan()
        self.push_digest_to_commander(scan)
        if scan.get("urgency_score", 0) >= 5:
            self.push_urgent_notification(scan)
        return scan


# ── Notification helpers ──────────────────────────────────────────────────────

def _twilio_send(message: str) -> None:
    """Sends a WhatsApp message via Twilio if configured."""
    import urllib.request
    import urllib.parse
    import base64

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
    to_number = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")

    if not all([account_sid, auth_token, from_number, to_number]):
        raise RuntimeError("Twilio WhatsApp not fully configured")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({
        "From": f"whatsapp:{from_number}",
        "To": f"whatsapp:{to_number}",
        "Body": message[:1600],
    }).encode()
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        logger.info("WhatsApp digest sent (status %s)", resp.status)


def _telegram_send(message: str) -> None:
    """Sends a Telegram message via Bot API if configured."""
    import urllib.request

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")

    if not all([bot_token, chat_id]):
        raise RuntimeError("Telegram not configured")

    import json
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": message[:4096], "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        logger.info("Telegram digest sent (status %s)", resp.status)


# ── Scheduler integration ─────────────────────────────────────────────────────

def schedule_platform_scan() -> None:
    """Call this from app startup to register the recurring scan.

    Uses APScheduler if available, otherwise logs a warning.
    The scan runs every 15 minutes by default.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scanner = PlatformScanner()
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=scanner.run_and_notify,
            trigger="interval",
            minutes=15,
            id="platform_soft_check",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        logger.info("Platform soft-check scanner scheduled (every 15 min)")
    except ImportError:
        logger.warning(
            "APScheduler not installed — platform scan must be triggered via cron endpoint. "
            "Add 'apscheduler' to requirements.txt to enable automatic scanning."
        )
    except Exception as e:
        logger.error("Failed to schedule platform scan: %s", e)
