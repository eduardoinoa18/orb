"""Sage brain starter combining monitoring + self-improvement capabilities."""

from __future__ import annotations

from typing import Any

from agents.sage.platform_monitor import PlatformMonitor
from agents.self_improvement import AgentSelfImprovement


class SageBrain(AgentSelfImprovement):
    """Sage orchestration facade for starter addendum scope."""

    agent_slug = "sage"

    def __init__(self) -> None:
        super().__init__()
        self.monitor = PlatformMonitor()

    def run_platform_monitor(self) -> dict[str, Any]:
        """Runs Sage S1 monitoring cycle."""
        return self.monitor.monitor_platform_health()

    def learn_from_outcomes(self, owner_id: str) -> dict[str, Any]:
        """Runs Sage weekly review and returns improvement updates."""
        result = super().learn_from_outcomes(agent_id=owner_id, lookback_days=7)
        return {
            "status": "updated",
            "owner_id": owner_id,
            "improvements_made": result.get("improvements_made", 0),
            "plan": result.get("plan", {}),
        }
