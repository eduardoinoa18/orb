"""Rex brain addendum: generalized sales learning + self-improvement proof of concept."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.self_improvement import AgentSelfImprovement
from agents.skill_engine import AgentSkillEngine
from app.database.connection import SupabaseService
from integrations.anthropic_client import ask_claude_smart
from integrations.token_optimizer import TokenOptimizer


class RexBrain(AgentSelfImprovement, AgentSkillEngine):
    """Generalized sales brain that learns owner context and weekly outcomes."""

    agent_slug = "rex"

    def __init__(self) -> None:
        AgentSelfImprovement.__init__(self)
        AgentSkillEngine.__init__(self)
        self.optimizer = TokenOptimizer()
        self.db = SupabaseService()

    def learn_from_owner(
        self,
        owner_id: str,
        product_description: str,
        ideal_customer_profile: str,
        common_objections: list[str],
        successful_close_examples: list[str],
    ) -> dict[str, Any]:
        """Learns the owner's sales context and stores it in rex.json."""
        raw_prompt = (
            "Build a sales knowledge profile in JSON with keys: "
            "what_owner_sells, ideal_customer_profile, solved_problems, "
            "objections_and_responses, winning_language_patterns, conversation_goals.\n"
            f"Owner product: {product_description}\n"
            f"Ideal customer: {ideal_customer_profile}\n"
            f"Common objections: {common_objections}\n"
            f"Successful closes: {successful_close_examples}"
        )

        optimization = self.optimizer.optimize_prompt(prompt=raw_prompt, task_type="short_analysis", max_budget_cents=4)
        profile: dict[str, Any]
        if optimization.needs_ai:
            try:
                ai_result = ask_claude_smart(
                    prompt=optimization.optimized_prompt,
                    system="You are a sales enablement strategist.",
                    max_tokens=optimization.max_tokens,
                )
                profile = json.loads(ai_result["text"])
                self.optimizer.save_cached_result(optimization.cache_key, ai_result["text"])
            except Exception:
                profile = self._fallback_profile(
                    product_description=product_description,
                    ideal_customer_profile=ideal_customer_profile,
                    common_objections=common_objections,
                    successful_close_examples=successful_close_examples,
                )
        else:
            profile = self._fallback_profile(
                product_description=product_description,
                ideal_customer_profile=ideal_customer_profile,
                common_objections=common_objections,
                successful_close_examples=successful_close_examples,
            )

        payload = {
            "name": "Rex",
            "role": "sales_agent",
            "persona": "Adaptable, persuasive, genuine. Focuses on qualifying and listening first.",
            "industry": "learned_from_owner",
            "product_knowledge": "loaded_dynamically",
            "self_improving": True,
            "owner_learning": {
                "owner_id": owner_id,
                "learned_at": datetime.now(timezone.utc).isoformat(),
                "profile": profile,
            },
        }
        self._save_rex_config(payload)

        self.db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="rex_owner_learning",
            description="Rex learned owner sales context and updated scripts baseline.",
            cost_cents=0,
            outcome="success",
            metadata={"optimizer_reason": optimization.bypass_reason or "ai"},
        )

        return {
            "status": "learned",
            "owner_id": owner_id,
            "profile": profile,
            "optimization": {
                "selected_model": optimization.selected_model,
                "max_tokens": optimization.max_tokens,
                "used_cache": optimization.used_cache,
            },
        }

    def learn_from_outcomes(self, owner_id: str) -> dict[str, Any]:
        """Weekly proof-of-concept: Rex self-improves based on recent outcomes."""
        # For proof-of-concept we use owner_id as grouping key in activity metadata.
        result = super().learn_from_outcomes(agent_id=owner_id, lookback_days=7)
        self.db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="rex_outcome_learning",
            description="Rex updated approach from weekly won/lost pattern analysis.",
            cost_cents=0,
            outcome="success",
            metadata={"improvements_made": result.get("improvements_made", 0)},
        )
        return {
            "status": "updated",
            "owner_id": owner_id,
            "improvements_made": result.get("improvements_made", 0),
            "plan": result.get("plan", {}),
        }

    def _save_rex_config(self, payload: dict[str, Any]) -> None:
        path = self._rex_config_path()
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                existing = {}
        existing.update(payload)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _rex_config_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "config" / "agent_configs" / "rex.json"

    def _fallback_profile(
        self,
        product_description: str,
        ideal_customer_profile: str,
        common_objections: list[str],
        successful_close_examples: list[str],
    ) -> dict[str, Any]:
        return {
            "what_owner_sells": product_description,
            "ideal_customer_profile": ideal_customer_profile,
            "solved_problems": ["Time", "Complexity", "Revenue growth"],
            "objections_and_responses": [
                {"objection": text, "response": "Acknowledge concern, then show proof and next step."}
                for text in common_objections[:5]
            ],
            "winning_language_patterns": successful_close_examples[:5],
            "conversation_goals": ["Qualify fit", "Confirm urgency", "Book next step"],
        }
