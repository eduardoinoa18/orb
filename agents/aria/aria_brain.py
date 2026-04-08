"""Aria brain wrapper for self-improvement addendum methods."""

from __future__ import annotations

from typing import Any

from agents.self_improvement import AgentSelfImprovement


class AriaBrain(AgentSelfImprovement):
	"""Aria addendum facade for weekly learning and owner adaptation."""

	agent_slug = "aria"

	def learn_from_outcomes(self, owner_id: str) -> dict[str, Any]:
		"""Runs a weekly review over Aria's recent outcomes."""
		result = super().learn_from_outcomes(agent_id=owner_id, lookback_days=7)
		return {
			"status": "updated",
			"owner_id": owner_id,
			"improvements_made": result.get("improvements_made", 0),
			"plan": result.get("plan", {}),
		}

	def learn_owner_style(self, owner_id: str) -> dict[str, Any]:
		"""Adapts Aria communication style from owner outcomes."""
		style = super().adapt_to_owner_style(agent_id=owner_id)
		return {"status": "adapted", "owner_id": owner_id, **style}
