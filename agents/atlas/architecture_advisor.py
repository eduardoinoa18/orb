"""Atlas Architecture Advisor — Module 1, Step A3.

Provides high-level architecture advice BEFORE coding begins.
Uses Claude Opus for deeper multi-step reasoning.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.atlas.atlas_brain import AtlasBrain

logger = logging.getLogger("orb.atlas.architecture_advisor")


class ArchitectureAdvisor:
    """Evaluates feature requests and recommends the right design approach."""

    SYSTEM_PROMPT = (
        "You are Atlas, a principal software architect with 15 years of experience "
        "designing scalable, secure, maintainable systems. You think about trade-offs, "
        "data models, API contracts, failure modes, and long-term maintenance before "
        "recommending an approach. You are practical — you size effort honestly and "
        "highlight risks the owner may not have considered."
    )

    def __init__(self, brain: "AtlasBrain") -> None:
        self._brain = brain

    def advise(
        self,
        feature_request: str,
        owner_id: str,
    ) -> dict[str, Any]:
        """Return architecture advice for *feature_request*.

        Args:
            feature_request: Description of the desired feature.
            owner_id: Requesting owner.

        Returns:
            dict with keys: recommendation, risks, alternatives,
                            effort_estimate, model_used, tokens_used
        """
        prompt = (
            f"Provide architecture advice for this feature request.\n\n"
            f"Feature: {feature_request}\n\n"
            "Consider: data model changes needed, API design, security implications, "
            "scalability, third-party dependencies, and testing strategy.\n\n"
            "Respond ONLY with a valid JSON object:\n"
            '{"recommendation": "...", '
            '"risks": ["..."], '
            '"alternatives": ["..."], '
            '"effort_estimate": "hours|days|weeks", '
            '"data_model_changes": ["..."], '
            '"api_endpoints": ["..."]}'
        )

        try:
            result = self._brain._call_heavy(
                prompt=prompt,
                system=self.SYSTEM_PROMPT,
                max_tokens=4096,
            )
            raw = result.get("text", "{}")
            raw = _strip_fences(raw)
            parsed = json.loads(raw)
            parsed.setdefault("recommendation", "See response above.")
            parsed.setdefault("risks", [])
            parsed.setdefault("alternatives", [])
            parsed.setdefault("effort_estimate", "unknown")
            parsed.setdefault("data_model_changes", [])
            parsed.setdefault("api_endpoints", [])
            parsed["model_used"] = "claude-opus-4-5"
            parsed["tokens_used"] = result.get("usage", {})
            return parsed
        except Exception as exc:
            logger.warning("ArchitectureAdvisor fallback for '%s': %s", feature_request[:60], exc)
            return {
                "recommendation": f"Atlas could not analyse this request automatically. Error: {exc}",
                "risks": [],
                "alternatives": [],
                "effort_estimate": "unknown",
                "data_model_changes": [],
                "api_endpoints": [],
                "model_used": "fallback",
                "tokens_used": {},
            }


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            return inner.strip()
    return text
