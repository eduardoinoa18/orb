"""Rule-of-thumb strategy coaching based on Orion performance summaries."""

from __future__ import annotations

from typing import Any


class OrionStrategyImprover:
    """Generates actionable suggestions from summarized performance data."""

    def suggest(self, performance: dict[str, Any]) -> list[str]:
        recommendations: list[str] = []

        live = performance.get("live_trades", {})
        paper = performance.get("paper_trades", {})

        live_win_rate = float(live.get("win_rate") or 0)
        paper_win_rate = float(paper.get("win_rate") or 0)
        total_pnl = float(live.get("total_pnl") or 0) + float(paper.get("total_pnl") or 0)

        if live_win_rate < 45 and live.get("total_trades", 0) >= 8:
            recommendations.append("Lower trade frequency and only take A+ setups until win rate recovers above 50%.")

        if paper_win_rate >= 60 and paper.get("closed_trades", 0) >= 6:
            recommendations.append("Promote the best paper setup into a small-size live trial during the same session window.")

        if total_pnl < 0:
            recommendations.append("Reduce risk to 0.5% per trade and pause trading after the first two losses.")

        best_setup = str(live.get("best_setup") or "")
        if best_setup and best_setup != "n/a":
            recommendations.append(f"Increase focus on '{best_setup}' and de-prioritize underperforming setups.")

        if not recommendations:
            recommendations.append("Performance is stable. Keep current risk limits and gather more sample size before changing rules.")

        return recommendations
