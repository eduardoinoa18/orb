"""Strategy ingestion and normalization for Orion."""

from __future__ import annotations

from typing import Any

from app.database.connection import SupabaseService


class OrionStrategyResearcher:
    """Converts plain-language trader notes into structured strategy rules."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def ingest_strategy(
        self,
        agent_id: str,
        strategy_name: str,
        notes: str,
        source_trader: str | None = None,
    ) -> dict[str, Any]:
        """Stores a strategy row and returns the normalized interpretation."""
        normalized_rules = self._extract_rules(notes)
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "name": strategy_name,
            "description": notes,
            "rules_json": normalized_rules,
            "source_trader": source_trader,
            "is_active": True,
        }

        row = self.db.insert_one("strategies", payload)
        return {
            "status": "ingested",
            "strategy": row,
            "normalized_rules": normalized_rules,
        }

    def _extract_rules(self, notes: str) -> dict[str, Any]:
        text = notes.lower()

        setup_type = "momentum"
        if "mean reversion" in text:
            setup_type = "mean_reversion"
        elif "breakout" in text:
            setup_type = "breakout"
        elif "pullback" in text:
            setup_type = "pullback"

        direction_bias = "both"
        if "long only" in text or "long-only" in text:
            direction_bias = "long"
        elif "short only" in text or "short-only" in text:
            direction_bias = "short"

        session_start = "09:30"
        session_end = "11:30"
        if "power hour" in text:
            session_start = "15:00"
            session_end = "16:00"

        return {
            "setup_type": setup_type,
            "direction_bias": direction_bias,
            "session_start": session_start,
            "session_end": session_end,
            "risk_rules": {
                "max_daily_trades": 3,
                "max_daily_loss_dollars": 150,
                "stop_after_consecutive_losses": 2,
            },
            "raw_notes": notes,
        }
