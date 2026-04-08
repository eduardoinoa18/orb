"""Universal self-improvement mixin for ORB agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.anthropic_client import ask_claude_smart


@dataclass
class SelfReviewResult:
    """Normalized self-review output for one agent."""

    what_worked: list[str]
    what_failed: list[str]
    token_waste_identified: list[str]
    owner_preferences_learned: list[str]
    behavior_changes: list[str]
    new_skills_to_develop: list[str]


class AgentSelfImprovement:
    """Mixin that gives an agent weekly self-review and adaptation methods."""

    agent_slug: str = "agent"

    def __init__(self) -> None:
        self.db = SupabaseService()

    def learn_from_outcomes(self, agent_id: str, lookback_days: int = 7) -> dict[str, Any]:
        """Analyzes recent activity and returns a practical self-improvement plan."""
        rows = self._load_recent_activity(agent_id=agent_id, lookback_days=lookback_days)
        analysis = self._analyze_with_ai(agent_id=agent_id, rows=rows)
        self._apply_behavior_changes(analysis)
        self._log_summary(agent_id=agent_id, analysis=analysis)

        return {
            "agent_id": agent_id,
            "lookback_days": lookback_days,
            "events_analyzed": len(rows),
            "improvements_made": len(analysis.behavior_changes),
            "plan": {
                "what_worked": analysis.what_worked,
                "what_failed": analysis.what_failed,
                "token_waste_identified": analysis.token_waste_identified,
                "owner_preferences_learned": analysis.owner_preferences_learned,
                "behavior_changes": analysis.behavior_changes,
                "new_skills_to_develop": analysis.new_skills_to_develop,
            },
        }

    def adapt_to_owner_style(self, agent_id: str) -> dict[str, Any]:
        """Updates persona hints from approved/rejected patterns in activity metadata."""
        rows = self._load_recent_activity(agent_id=agent_id, lookback_days=30)
        approvals = [r for r in rows if str(r.get("outcome") or "").lower() == "approved"]
        rejections = [r for r in rows if str(r.get("outcome") or "").lower() == "rejected"]

        style_hint = {
            "preferred_length": "short" if len(approvals) >= len(rejections) else "detailed",
            "tone": "direct and practical",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._merge_config_values({"owner_style": style_hint})
        return {"agent_id": agent_id, "owner_style": style_hint}

    def identify_owner_needs(self, agent_id: str, observation_period_days: int = 30) -> dict[str, Any]:
        """Generates up to three proactive suggestions based on recurring work patterns."""
        rows = self._load_recent_activity(agent_id=agent_id, lookback_days=observation_period_days)
        descriptions = [str(r.get("description") or "") for r in rows]
        suggestions: list[str] = []

        if any("follow-up" in text.lower() for text in descriptions):
            suggestions.append("I can automate your Monday follow-up workflow end-to-end.")
        if any("approval" in text.lower() for text in descriptions):
            suggestions.append("I can batch non-urgent approvals into one daily digest to save your time.")
        if any("error" in str(r.get("outcome") or "").lower() for r in rows):
            suggestions.append("I can add a daily health pre-check to prevent recurring workflow failures.")

        if not suggestions:
            suggestions.append("I can create a weekly ops summary so you only review high-impact decisions.")

        return {"agent_id": agent_id, "suggestions": suggestions[:3], "observation_period_days": observation_period_days}

    def _load_recent_activity(self, agent_id: str, lookback_days: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        try:
            rows = self.db.fetch_all("activity_log", {"agent_id": agent_id})
        except DatabaseConnectionError:
            return []

        filtered: list[dict[str, Any]] = []
        for row in rows:
            created_at = str(row.get("created_at") or "")
            if not created_at:
                continue
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= cutoff:
                filtered.append(row)
        return filtered

    def _analyze_with_ai(self, agent_id: str, rows: list[dict[str, Any]]) -> SelfReviewResult:
        default = SelfReviewResult(
            what_worked=["Kept core workflows running consistently."],
            what_failed=["Some outcomes were not explicitly logged."],
            token_waste_identified=["Long prompts used for short outputs."],
            owner_preferences_learned=["Owner prefers practical updates."],
            behavior_changes=["Use shorter summaries by default."],
            new_skills_to_develop=["Improve proactive alerting."],
        )
        if not rows:
            return default

        prompt = (
            f"Agent ID: {agent_id}\n"
            f"Activity rows (JSON): {json.dumps(rows[-40:], default=str)}\n"
            "Return JSON with keys: what_worked, what_failed, token_waste_identified, "
            "owner_preferences_learned, behavior_changes, new_skills_to_develop"
        )

        try:
            result = ask_claude_smart(prompt=prompt, system="You are an operations self-review assistant.", max_tokens=700)
            parsed = json.loads(result["text"])
            return SelfReviewResult(
                what_worked=list(parsed.get("what_worked") or []),
                what_failed=list(parsed.get("what_failed") or []),
                token_waste_identified=list(parsed.get("token_waste_identified") or []),
                owner_preferences_learned=list(parsed.get("owner_preferences_learned") or []),
                behavior_changes=list(parsed.get("behavior_changes") or []),
                new_skills_to_develop=list(parsed.get("new_skills_to_develop") or []),
            )
        except Exception:
            return default

    def _apply_behavior_changes(self, analysis: SelfReviewResult) -> None:
        self._merge_config_values(
            {
                "self_improvement": {
                    "last_review_at": datetime.now(timezone.utc).isoformat(),
                    "behavior_changes": analysis.behavior_changes,
                    "owner_preferences_learned": analysis.owner_preferences_learned,
                }
            }
        )

    def _log_summary(self, agent_id: str, analysis: SelfReviewResult) -> None:
        self.db.log_activity(
            agent_id=agent_id,
            owner_id=None,
            action_type="self_improvement",
            description=f"Weekly self-review completed with {len(analysis.behavior_changes)} behavior changes.",
            cost_cents=0,
            outcome="success",
            metadata={
                "improvements_made": len(analysis.behavior_changes),
                "optimizer_reason": "self_review",
            },
        )

    def _merge_config_values(self, values: dict[str, Any]) -> None:
        config_path = self._config_path()
        if config_path is None:
            return

        existing: dict[str, Any] = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                existing = {}

        existing.update(values)
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _config_path(self) -> Path | None:
        base = Path(__file__).resolve().parent.parent
        if not self.agent_slug:
            return None
        return base / "config" / "agent_configs" / f"{self.agent_slug}.json"
