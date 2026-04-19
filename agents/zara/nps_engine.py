"""NPS (Net Promoter Score) engine for ORB platform.

Sends surveys, records responses, computes NPS score,
and generates AI-driven insights from promoters/detractors.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.zara.nps")


class NPSEngine:
    """Handles NPS surveys and platform health measurement."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def send_survey(self, owner_id: str) -> dict[str, Any]:
        """Dispatch NPS survey to an owner (via Commander inbox)."""
        try:
            self.db.client.table("agent_messages").insert({
                "owner_id": owner_id,
                "agent": "zara",
                "role": "assistant",
                "content": (
                    "👋 Quick question from Zara!\n\n"
                    "On a scale of 0–10, how likely are you to recommend ORB to a colleague or friend?\n\n"
                    "Reply with just a number (0-10) and optionally share any feedback. "
                    "Your input directly shapes what we build next. Thank you! 🙏"
                ),
                "metadata": {"survey_type": "nps", "survey_version": "1"},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            # Log that survey was sent
            self.db.client.table("nps_responses").insert({
                "owner_id": owner_id,
                "score": None,  # Will be updated when owner responds
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            return {"sent": True, "owner_id": owner_id}
        except Exception as e:
            logger.error("Failed to send NPS survey: %s", e)
            return {"sent": False, "error": str(e)}

    def record_response(self, owner_id: str, score: int, comment: str = "") -> dict[str, Any]:
        """Save an NPS score and generate AI follow-up action."""
        if not 0 <= score <= 10:
            return {"error": "Score must be 0–10"}

        category = "promoter" if score >= 9 else ("passive" if score >= 7 else "detractor")

        try:
            # Update or insert response
            existing = self.db.fetch_all("nps_responses", {"owner_id": owner_id, "status": "sent"})
            if existing:
                self.db.client.table("nps_responses").update({
                    "score": score,
                    "comment": comment,
                    "category": category,
                    "status": "responded",
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                }).eq("owner_id", owner_id).eq("status", "sent").execute()
            else:
                self.db.client.table("nps_responses").insert({
                    "owner_id": owner_id,
                    "score": score,
                    "comment": comment,
                    "category": category,
                    "status": "responded",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                }).execute()

            # Generate follow-up message
            follow_up = think(
                prompt=(
                    f"NPS score: {score}/10 ({category})\n"
                    f"Comment: {comment or 'No comment'}\n"
                    "Write a warm 2-sentence thank-you response. "
                    "If detractor, acknowledge and offer help. "
                    "If promoter, celebrate and invite referrals."
                ),
                task_type="email",
            )

            # Push follow-up to Commander inbox
            self.db.client.table("agent_messages").insert({
                "owner_id": owner_id,
                "agent": "zara",
                "role": "assistant",
                "content": follow_up,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            # Alert Eduardo if detractor
            if category == "detractor":
                self.db.client.table("agent_messages").insert({
                    "owner_id": "master",
                    "agent": "zara",
                    "role": "assistant",
                    "content": (
                        f"🔴 NPS DETRACTOR — Owner {owner_id}\n"
                        f"Score: {score}/10\n"
                        f"Comment: {comment or 'None'}\n"
                        "Recommend reaching out personally within 24 hours."
                    ),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()

            return {
                "recorded": True,
                "score": score,
                "category": category,
                "follow_up_sent": True,
            }
        except Exception as e:
            logger.error("Failed to record NPS response: %s", e)
            return {"recorded": False, "error": str(e)}

    def get_summary(self) -> dict[str, Any]:
        """Compute platform-wide NPS score."""
        try:
            rows = self.db.client.table("nps_responses").select("*").eq("status", "responded").execute().data or []
            if not rows:
                return {"nps_score": None, "total_responses": 0, "breakdown": {}}

            promoters = sum(1 for r in rows if r.get("score", 0) >= 9)
            passives = sum(1 for r in rows if 7 <= r.get("score", 0) <= 8)
            detractors = sum(1 for r in rows if r.get("score", 0) <= 6)
            total = len(rows)
            nps = round(((promoters - detractors) / total) * 100) if total > 0 else 0

            # Summarize comments via AI
            comments = [r.get("comment", "") for r in rows if r.get("comment")]
            ai_insight = ""
            if comments:
                ai_insight = think(
                    prompt=f"Summarize these NPS comments in 3 bullet points:\n{chr(10).join(comments[:20])}",
                    task_type="extract",
                )

            return {
                "nps_score": nps,
                "total_responses": total,
                "breakdown": {"promoters": promoters, "passives": passives, "detractors": detractors},
                "response_rate_pct": round((total / max(total, 1)) * 100),
                "ai_insights": ai_insight,
            }
        except Exception as e:
            logger.error("Failed to compute NPS summary: %s", e)
            return {"error": str(e)}
