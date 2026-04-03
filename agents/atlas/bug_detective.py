"""Atlas Bug Detective — Module 1, Step A2.

Diagnoses Python errors and proposes concrete fixes.
Uses Claude Sonnet for speed; suitable for CI/CD integration.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.atlas.atlas_brain import AtlasBrain

logger = logging.getLogger("orb.atlas.bug_detective")


class BugDetective:
    """Analyses stack traces and error messages to find root causes."""

    SYSTEM_PROMPT = (
        "You are Atlas, a senior Python debugger. You read error messages and stack traces "
        "with expert precision, identify root causes immediately, and propose the minimal, "
        "safest fix. You never guess — you reason step by step."
    )

    def __init__(self, brain: "AtlasBrain") -> None:
        self._brain = brain

    def diagnose_error(
        self,
        error_message: str,
        stack_trace: str,
        context: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """Diagnose *error_message* + *stack_trace* and return a fix.

        Returns:
            dict with keys: root_cause, fix, affected_files, confidence, model_used
        """
        prompt = (
            f"Diagnose this Python error and propose the exact fix.\n\n"
            f"Error: {error_message}\n\n"
            f"Stack trace:\n{stack_trace}\n\n"
            f"Context: {context or 'none provided'}\n"
            f"Agent/module: {agent_id or 'unknown'}\n\n"
            "Respond ONLY with a valid JSON object:\n"
            '{"root_cause": "...", "fix": "...exact code change...", '
            '"affected_files": ["..."], "confidence": "high|medium|low"}'
        )

        try:
            result = self._brain._call_standard(
                prompt=prompt,
                system=self.SYSTEM_PROMPT,
                max_tokens=1024,
            )
            raw = result.get("text", "{}")
            raw = _strip_fences(raw)
            parsed = json.loads(raw)
            parsed.setdefault("root_cause", "Unknown")
            parsed.setdefault("fix", "Review the stack trace manually.")
            parsed.setdefault("affected_files", [])
            parsed.setdefault("confidence", "low")
            parsed["model_used"] = "claude-3-5-sonnet-20241022"
            parsed["tokens_used"] = result.get("usage", {})
            return parsed
        except Exception as exc:
            logger.warning("BugDetective fallback for '%s': %s", error_message[:60], exc)
            return {
                "root_cause": "Atlas could not analyse this error automatically.",
                "fix": f"Review the stack trace manually. Error: {exc}",
                "affected_files": [],
                "confidence": "low",
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
