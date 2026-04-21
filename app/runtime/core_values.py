"""Core-values scoring helpers for continuous platform refinement.

The platform's north-star values are intentionally simple:
  1) Simplicity: keep operations easy to run and reason about.
  2) Reliability: keep critical systems healthy and predictable.
  3) Owner control: keep decisions visible and manageable.
  4) Learning velocity: improve behavior over time from real outcomes.
"""

from __future__ import annotations

from typing import Any


NORTH_STAR = "Simple, reliable, owner-controlled AI operations that improve every week."


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _weighted_overall(scores: dict[str, int]) -> int:
    # Simplicity and reliability are weighted slightly higher as platform guardrails.
    weighted = (
        scores["simplicity"] * 0.3
        + scores["reliability"] * 0.3
        + scores["owner_control"] * 0.2
        + scores["learning_velocity"] * 0.2
    )
    return _clamp_score(round(weighted))


def evaluate_preflight_core_values(report: dict[str, Any]) -> dict[str, Any]:
    """Build a core-values scorecard from a preflight report."""
    blockers = len(report.get("blockers") or [])
    warnings = len(report.get("warnings") or [])
    schema_ready = bool((report.get("schema") or {}).get("ready"))

    simplicity = _clamp_score(100 - blockers * 20 - warnings * 5)
    reliability = _clamp_score(100 - blockers * 25 - (0 if schema_ready else 20))
    owner_control = _clamp_score(96 - blockers * 12 - warnings * 4)
    learning_velocity = _clamp_score(92 - blockers * 10 - warnings * 3)

    scores = {
        "simplicity": simplicity,
        "reliability": reliability,
        "owner_control": owner_control,
        "learning_velocity": learning_velocity,
    }
    recommendations = _recommendations_from_scores(scores=scores)

    return {
        "north_star": NORTH_STAR,
        "overall": _weighted_overall(scores),
        "scores": scores,
        "recommendations": recommendations,
        "signals": {
            "blockers": blockers,
            "warnings": warnings,
            "schema_ready": schema_ready,
        },
    }


def evaluate_scan_core_values(scan_result: dict[str, Any]) -> dict[str, Any]:
    """Build a core-values scorecard from the platform soft-check scan."""
    requests = scan_result.get("requests") or {}
    code_tasks = scan_result.get("code_tasks") or {}
    integrations = scan_result.get("integrations") or {}
    activity = scan_result.get("agent_activity") or {}
    unread_messages = scan_result.get("unread_messages") or {}

    pending_requests = int(requests.get("total") or 0)
    urgent_requests = int(requests.get("urgent") or 0)
    needs_review = int(code_tasks.get("needs_review") or 0)
    stale_tasks = int(code_tasks.get("stale") or 0)
    unread = int(unread_messages.get("total") or 0)
    failed_integrations = len(integrations.get("failed") or [])
    activity_count_48h = int(activity.get("activity_count_48h") or 0)

    complexity_load = pending_requests + needs_review + stale_tasks * 2
    simplicity = _clamp_score(100 - complexity_load * 2 - urgent_requests * 4)
    reliability = _clamp_score(100 - failed_integrations * 20 - stale_tasks * 8 - urgent_requests * 5)
    owner_control = _clamp_score(96 - unread * 2 - urgent_requests * 5)
    learning_velocity = _clamp_score(70 + min(24, activity_count_48h // 4) - stale_tasks * 5)

    scores = {
        "simplicity": simplicity,
        "reliability": reliability,
        "owner_control": owner_control,
        "learning_velocity": learning_velocity,
    }
    recommendations = _recommendations_from_scores(scores=scores)

    return {
        "north_star": NORTH_STAR,
        "overall": _weighted_overall(scores),
        "scores": scores,
        "recommendations": recommendations,
        "signals": {
            "pending_requests": pending_requests,
            "urgent_requests": urgent_requests,
            "needs_review": needs_review,
            "stale_tasks": stale_tasks,
            "failed_integrations": failed_integrations,
            "unread_messages": unread,
            "activity_count_48h": activity_count_48h,
        },
    }


def _recommendations_from_scores(scores: dict[str, int]) -> list[str]:
    recommendations: list[str] = []
    if scores["simplicity"] < 75:
        recommendations.append("Reduce WIP: close stale/pending tasks before creating new ones.")
    if scores["reliability"] < 80:
        recommendations.append("Prioritize required integration and schema blockers in the next cycle.")
    if scores["owner_control"] < 80:
        recommendations.append("Consolidate approvals and unread items into one daily commander digest.")
    if scores["learning_velocity"] < 75:
        recommendations.append("Run weekly learn-from-outcomes reviews for every active agent.")
    if not recommendations:
        recommendations.append("Maintain current operating rhythm and keep weekly self-review cadence.")
    return recommendations