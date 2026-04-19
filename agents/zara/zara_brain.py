"""Zara — Customer Success & Onboarding Agent.

Zara makes sure every owner on ORB succeeds. She:
  - Guides new users through onboarding (step-by-step flows)
  - Monitors customer health scores and churn signals
  - Runs NPS surveys and synthesizes feedback
  - Sends milestone check-ins and proactive nudges
  - Escalates at-risk accounts to Eduardo via Commander inbox
  - Delegates customer content needs to Nova

Business rationale: Retention is the cheapest growth. Zara is the
early-warning system that catches struggling owners before they churn.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.self_improvement import AgentSelfImprovement
from agents.skill_engine import AgentSkillEngine
from agents.zara.nps_engine import NPSEngine
from agents.zara.onboarding_flow import OnboardingFlow
from agents.zara.success_tracker import SuccessTracker
from app.database.connection import SupabaseService
from integrations.ai_router import think
from integrations.resend_client import send_resend_email
from integrations.whatsapp_commander import send_whatsapp_message

logger = logging.getLogger("orb.zara")


class ZaraBrain(AgentSelfImprovement, AgentSkillEngine):
    """Customer success brain — proactive, empathetic, data-driven."""

    agent_slug = "zara"

    def __init__(self) -> None:
        AgentSelfImprovement.__init__(self)
        AgentSkillEngine.__init__(self)
        self.db = SupabaseService()
        self.nps = NPSEngine()
        self.flow = OnboardingFlow()
        self.tracker = SuccessTracker()

    # ── Core conversation handler ─────────────────────────────────────────

    def chat(self, owner_id: str, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route an owner message through Zara's success lens."""
        ctx = context or {}
        health = self.tracker.get_health_score(owner_id)
        skill_ctx = self.build_skill_context(owner_id)

        system = (
            "You are Zara, ORB's Customer Success Agent. You are warm, proactive, and genuinely care "
            "about every owner's success. You guide people, celebrate wins, flag concerns early, and "
            "connect owners to the right resources. You never make owners feel judged for struggling — "
            "you make them feel supported.\n\n"
            f"Owner health score: {health.get('score', 'unknown')}/100\n"
            f"Onboarding complete: {health.get('onboarding_complete', False)}\n"
            f"Days since last active: {health.get('days_inactive', 0)}\n"
            f"{skill_ctx}"
        )

        prompt = f"Owner message: {message}\nContext: {json.dumps(ctx)}"
        response = think(prompt=prompt, task_type="report", system_override=system)

        return {
            "agent": "zara",
            "message": response,
            "health_score": health.get("score"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Onboarding ────────────────────────────────────────────────────────

    def start_onboarding(self, owner_id: str, business_profile: dict[str, Any]) -> dict[str, Any]:
        """Kick off the onboarding flow for a new owner."""
        return self.flow.initialize(owner_id=owner_id, business_profile=business_profile)

    def get_onboarding_status(self, owner_id: str) -> dict[str, Any]:
        """Return current onboarding progress and next step."""
        return self.flow.get_status(owner_id)

    def complete_onboarding_step(self, owner_id: str, step_key: str, data: dict[str, Any]) -> dict[str, Any]:
        """Mark an onboarding step done and return the next one."""
        return self.flow.complete_step(owner_id=owner_id, step_key=step_key, data=data)

    # ── Health & Churn Risk ───────────────────────────────────────────────

    def analyze_churn_risk(self, owner_id: str) -> dict[str, Any]:
        """Run a full churn risk analysis for an owner."""
        health = self.tracker.get_health_score(owner_id)
        score = health.get("score", 50)
        signals = health.get("signals", [])

        risk_level = "low"
        if score < 30:
            risk_level = "critical"
        elif score < 50:
            risk_level = "high"
        elif score < 70:
            risk_level = "medium"

        analysis = think(
            prompt=(
                f"Owner health score: {score}/100\n"
                f"Risk signals: {signals}\n"
                "Provide a 3-sentence churn risk summary and 2 specific actions to re-engage this owner."
            ),
            task_type="report",
        )

        result = {
            "owner_id": owner_id,
            "health_score": score,
            "risk_level": risk_level,
            "signals": signals,
            "ai_analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Auto-escalate critical accounts to Commander inbox
        if risk_level == "critical":
            self._escalate_to_commander(owner_id=owner_id, analysis=result)

        return result

    def _escalate_to_commander(self, owner_id: str, analysis: dict[str, Any]) -> None:
        """Push a critical churn alert to Eduardo's Commander inbox."""
        try:
            self.db.client.table("agent_messages").insert({
                "owner_id": "master",  # Eduardo's Commander inbox
                "agent": "zara",
                "role": "assistant",
                "content": (
                    f"⚠️ CHURN RISK ALERT — Owner {owner_id}\n"
                    f"Health score: {analysis['health_score']}/100 ({analysis['risk_level']} risk)\n"
                    f"Signals: {', '.join(analysis.get('signals', []))}\n\n"
                    f"{analysis.get('ai_analysis', '')}"
                ),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.warning("Failed to escalate churn alert: %s", e)

    # ── NPS & Feedback ────────────────────────────────────────────────────

    def send_nps_survey(self, owner_id: str) -> dict[str, Any]:
        """Dispatch an NPS survey to an owner."""
        return self.nps.send_survey(owner_id)

    def record_nps_response(self, owner_id: str, score: int, comment: str = "") -> dict[str, Any]:
        """Save an NPS response and generate follow-up actions."""
        return self.nps.record_response(owner_id=owner_id, score=score, comment=comment)

    def get_nps_summary(self) -> dict[str, Any]:
        """Get platform-wide NPS summary (admin)."""
        return self.nps.get_summary()

    # ── Proactive Outreach ────────────────────────────────────────────────

    def generate_check_in_message(self, owner_id: str, trigger: str = "weekly") -> str:
        """Write a personalized check-in message for an owner."""
        health = self.tracker.get_health_score(owner_id)
        return think(
            prompt=(
                f"Write a warm, brief check-in message for an ORB platform owner.\n"
                f"Trigger: {trigger} check-in\n"
                f"Health score: {health.get('score', 70)}/100\n"
                f"Days since last active: {health.get('days_inactive', 0)}\n"
                f"Top agents used: {health.get('top_agents', ['Commander'])}\n"
                "Keep it under 120 words. Feel personal, not automated."
            ),
            task_type="email",
        )

    def run_weekly_success_review(self) -> dict[str, Any]:
        """Platform-wide weekly sweep: flag at-risk owners, celebrate wins."""
        return self.tracker.run_weekly_review()

    def _active_channel_mappings(self, owner_id: str, platform: str) -> list[dict[str, Any]]:
        """Fetch active channel mappings for an owner/platform, if table is available."""
        try:
            rows = (
                self.db.client.table("channel_mappings")
                .select("external_id,platform,is_active")
                .eq("owner_id", owner_id)
                .eq("platform", platform)
                .eq("is_active", True)
                .limit(3)
                .execute()
                .data
                or []
            )
            return rows
        except Exception:
            return []

    def _send_check_in_message(self, owner: dict[str, Any], message: str) -> dict[str, Any]:
        """Try preferred channels in order: WhatsApp then email; return delivery result."""
        owner_id = str(owner.get("id") or "")
        whatsapp_targets = [str(r.get("external_id") or "").strip() for r in self._active_channel_mappings(owner_id, "whatsapp")]
        whatsapp_targets = [t.replace("whatsapp:", "").strip() for t in whatsapp_targets if t.strip()]
        phone = str(owner.get("phone") or "").strip()
        if phone and phone not in whatsapp_targets:
            whatsapp_targets.append(phone)

        for target in whatsapp_targets:
            if send_whatsapp_message(target, message):
                return {"sent": True, "channel": "whatsapp", "target": target}

        email_targets = [str(r.get("external_id") or "").strip() for r in self._active_channel_mappings(owner_id, "email")]
        email_targets = [e for e in email_targets if e]
        email = str(owner.get("email") or "").strip()
        if email and email not in email_targets:
            email_targets.append(email)

        for target in email_targets:
            result = send_resend_email(
                to_email=target,
                subject="Quick ORB check-in from Zara",
                html=f"<p>{message}</p>",
            )
            if bool(result.get("sent")):
                return {"sent": True, "channel": "email", "target": target}

        return {"sent": False, "channel": "none", "target": None, "reason": "no_configured_channel"}

    def send_at_risk_check_ins(self, dry_run: bool = False, max_accounts: int = 100) -> dict[str, Any]:
        """Send personalized weekly check-ins to at-risk owners (health score < 50)."""
        try:
            rows = (
                self.db.client.table("owners")
                .select("id,email,phone")
                .order("created_at", desc=False)
                .limit(max(1, min(max_accounts, 1000)))
                .execute()
                .data
                or []
            )
        except Exception as e:
            logger.error("Failed to load owners for Zara check-ins: %s", e)
            return {"error": str(e), "scanned": 0, "at_risk": 0, "sent": 0}

        sent = 0
        at_risk = 0
        details: list[dict[str, Any]] = []

        for owner in rows:
            owner_id = str(owner.get("id") or "").strip()
            if not owner_id:
                continue

            health = self.tracker.get_health_score(owner_id)
            score = int(health.get("score") or 0)
            if score >= 50:
                continue

            at_risk += 1
            message = self.generate_check_in_message(owner_id=owner_id, trigger="weekly at-risk")

            if dry_run:
                details.append({"owner_id": owner_id, "score": score, "sent": False, "channel": "dry_run"})
                continue

            delivery = self._send_check_in_message(owner=owner, message=message)
            if delivery.get("sent"):
                sent += 1

            details.append(
                {
                    "owner_id": owner_id,
                    "score": score,
                    "sent": bool(delivery.get("sent")),
                    "channel": delivery.get("channel"),
                    "target": delivery.get("target"),
                }
            )

        summary = {
            "scanned": len(rows),
            "at_risk": at_risk,
            "sent": sent,
            "dry_run": dry_run,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }

        try:
            self.db.client.table("agent_messages").insert(
                {
                    "owner_id": "master",
                    "agent": "zara",
                    "role": "assistant",
                    "content": (
                        "📬 Zara weekly at-risk check-ins\n"
                        f"Scanned: {summary['scanned']}\n"
                        f"At risk: {summary['at_risk']}\n"
                        f"Sent: {summary['sent']}\n"
                        f"Dry run: {summary['dry_run']}"
                    ),
                    "created_at": summary["timestamp"],
                }
            ).execute()
        except Exception:
            logger.warning("Unable to write Zara check-in summary to Commander inbox")

        return summary
