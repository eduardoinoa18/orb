"""Customer success tracker — health scores, milestones, churn signals."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.zara.tracker")

# Health score weights (must sum to 100)
HEALTH_WEIGHTS = {
    "login_recency": 20,       # Days since last login
    "commander_usage": 20,     # Active Commander conversations
    "agent_activation": 20,    # How many agents are active
    "integration_count": 15,   # Connected integrations
    "onboarding_complete": 15, # Completed onboarding
    "nps_score": 10,           # NPS response (if any)
}


class SuccessTracker:
    """Tracks owner health and surfaces churn signals."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def get_health_score(self, owner_id: str) -> dict[str, Any]:
        """Compute a 0–100 health score for an owner."""
        try:
            score = 0
            signals = []

            # 1. Login recency (check activity log)
            try:
                logs = (
                    self.db.client.table("activity_log")
                    .select("created_at")
                    .eq("owner_id", owner_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                    .data or []
                )
                if logs:
                    last_seen = datetime.fromisoformat(logs[0]["created_at"].replace("Z", "+00:00"))
                    days_inactive = (datetime.now(timezone.utc) - last_seen).days
                    if days_inactive <= 1:
                        score += 20
                    elif days_inactive <= 7:
                        score += 15
                    elif days_inactive <= 14:
                        score += 8
                    else:
                        signals.append(f"No login in {days_inactive} days")
                else:
                    days_inactive = 999
                    signals.append("Never logged in")
            except Exception:
                days_inactive = 0

            # 2. Commander usage
            try:
                msg_count = (
                    self.db.client.table("agent_messages")
                    .select("id", count="exact")
                    .eq("owner_id", owner_id)
                    .eq("role", "user")
                    .execute()
                    .count or 0
                )
                if msg_count >= 50:
                    score += 20
                elif msg_count >= 20:
                    score += 15
                elif msg_count >= 5:
                    score += 8
                elif msg_count >= 1:
                    score += 4
                else:
                    signals.append("No Commander conversations")
            except Exception:
                pass

            # 3. Agent activation
            try:
                agent_rows = self.db.fetch_all("agents", {"owner_id": owner_id, "active": True})
                active_count = len(agent_rows)
                score += min(20, active_count * 5)
                if active_count == 0:
                    signals.append("No agents activated")
                top_agents = [r.get("slug", "") for r in agent_rows[:3]]
            except Exception:
                top_agents = []

            # 4. Integrations
            try:
                int_rows = self.db.fetch_all("integrations", {"owner_id": owner_id, "enabled": True})
                int_count = len(int_rows)
                score += min(15, int_count * 5)
                if int_count == 0:
                    signals.append("No integrations connected")
            except Exception:
                pass

            # 5. Onboarding
            try:
                ob_rows = self.db.fetch_all("onboarding_flows", {"owner_id": owner_id})
                onboarding_complete = ob_rows[0].get("completed_at") is not None if ob_rows else False
                if onboarding_complete:
                    score += 15
                else:
                    signals.append("Onboarding not completed")
            except Exception:
                onboarding_complete = False

            # 6. NPS
            try:
                nps_rows = (
                    self.db.client.table("nps_responses")
                    .select("score")
                    .eq("owner_id", owner_id)
                    .eq("status", "responded")
                    .order("responded_at", desc=True)
                    .limit(1)
                    .execute()
                    .data or []
                )
                if nps_rows:
                    nps = nps_rows[0].get("score", 5)
                    score += round((nps / 10) * 10)
            except Exception:
                pass

            return {
                "owner_id": owner_id,
                "score": min(100, score),
                "signals": signals,
                "onboarding_complete": onboarding_complete,
                "days_inactive": days_inactive,
                "top_agents": top_agents,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to compute health score: %s", e)
            return {"owner_id": owner_id, "score": 50, "signals": [], "error": str(e)}

    def run_weekly_review(self) -> dict[str, Any]:
        """Scan all owners for churn risk and surface alerts."""
        try:
            # Get all active owners
            owner_rows = self.db.client.table("owner_profiles").select("owner_id").execute().data or []
            at_risk = []
            healthy = []

            for row in owner_rows:
                oid = row["owner_id"]
                health = self.get_health_score(oid)
                score = health.get("score", 50)
                if score < 50:
                    at_risk.append({"owner_id": oid, "score": score, "signals": health.get("signals", [])})
                else:
                    healthy.append(oid)

            # Push summary to Commander inbox
            summary = think(
                prompt=(
                    f"Weekly success review:\n"
                    f"- Total owners: {len(owner_rows)}\n"
                    f"- At risk (score < 50): {len(at_risk)}\n"
                    f"- Healthy: {len(healthy)}\n"
                    f"- Critical accounts: {[a for a in at_risk if a['score'] < 30]}\n"
                    "Write a 4-sentence executive summary with top 2 recommendations."
                ),
                task_type="report",
            )

            self.db.client.table("agent_messages").insert({
                "owner_id": "master",
                "agent": "zara",
                "role": "assistant",
                "content": f"📊 Weekly Success Review\n\n{summary}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            return {
                "total": len(owner_rows),
                "at_risk": len(at_risk),
                "healthy": len(healthy),
                "critical_accounts": [a for a in at_risk if a["score"] < 30],
                "summary": summary,
            }
        except Exception as e:
            logger.error("Weekly review failed: %s", e)
            return {"error": str(e)}
