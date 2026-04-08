"""Atlas Brain — Module 1, Step A1.

Routes developer tasks to the appropriate model tier:
- Standard tasks (generate_feature, diagnose_error): claude-3-5-sonnet
- Heavy tasks (advise_on_feature, security_scan): claude-opus

Atlas is the 7th ORB agent: a senior developer on call 24/7.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.self_improvement import AgentSelfImprovement
from app.database.connection import SupabaseService
from integrations.anthropic_client import ask_claude_smart

logger = logging.getLogger("orb.atlas")

# Model constants — upgrade these as Anthropic releases newer versions
_STANDARD_MODEL = "claude-3-5-sonnet-20241022"
_HEAVY_MODEL = "claude-opus-4-5"


class AtlasBrain(AgentSelfImprovement):
    """Orchestrates Atlas's developer capabilities.

    Usage:
        brain = AtlasBrain()
        result = brain.generate_feature("Add a calendar sync endpoint", owner_id="owner_123")
    """

    agent_slug = "atlas"

    def __init__(self) -> None:
        super().__init__()
        self.db = SupabaseService()

    # ------------------------------------------------------------------
    # Public API — routes to sub-modules
    # ------------------------------------------------------------------

    def generate_feature(
        self,
        feature_description: str,
        owner_id: str,
        context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate production-ready Python code for a described feature.

        Args:
            feature_description: Plain-English description of the feature.
            owner_id: Platform owner requesting the feature.
            context_files: Optional list of existing file contents to include.

        Returns:
            dict with keys: code, explanation, tests, model_used, tokens_used
        """
        from agents.atlas.code_generator import CodeGenerator
        return CodeGenerator(brain=self).generate_feature(
            feature_description=feature_description,
            owner_id=owner_id,
            context_files=context_files or [],
        )

    def diagnose_error(
        self,
        error_message: str,
        stack_trace: str,
        context: str = "",
        agent_id: str = "",
    ) -> dict[str, Any]:
        """Diagnose a Python error and suggest a concrete fix.

        Args:
            error_message: The exception message text.
            stack_trace: Full traceback string.
            context: Optional surrounding code or description.
            agent_id: The agent or module where the error occurred.

        Returns:
            dict with keys: root_cause, fix, affected_files, confidence, model_used
        """
        from agents.atlas.bug_detective import BugDetective
        return BugDetective(brain=self).diagnose_error(
            error_message=error_message,
            stack_trace=stack_trace,
            context=context,
            agent_id=agent_id,
        )

    def advise_on_feature(
        self,
        feature_request: str,
        owner_id: str,
    ) -> dict[str, Any]:
        """Provide architecture advice for a feature before coding begins.

        Uses Claude Opus for deeper reasoning.

        Args:
            feature_request: Description of the desired feature.
            owner_id: Platform owner.

        Returns:
            dict with keys: recommendation, risks, alternatives, effort_estimate, model_used
        """
        from agents.atlas.architecture_advisor import ArchitectureAdvisor
        return ArchitectureAdvisor(brain=self).advise(
            feature_request=feature_request,
            owner_id=owner_id,
        )

    def security_scan(
        self,
        code_snippet: str,
        file_path: str = "",
    ) -> dict[str, Any]:
        """Scan a code snippet for OWASP Top 10 vulnerabilities.

        Uses Claude Opus to reason about subtle security issues.

        Args:
            code_snippet: Python source code to check.
            file_path: Optional source file path (for context in findings).

        Returns:
            dict with keys: findings (list), severity, recommendation, model_used
        """
        prompt = (
            "You are an expert security auditor specializing in Python web apps (FastAPI/Django). "
            "Scan the following code for OWASP Top 10 vulnerabilities, injection flaws, "
            "hardcoded secrets, insecure deserialization, broken auth, and sensitive data exposure. "
            "For each finding: state the vulnerability type, line reference if visible, severity "
            "(critical/high/medium/low), and the exact remediation.\n\n"
            f"File: {file_path or 'unknown'}\n\n```python\n{code_snippet}\n```\n\n"
            "Respond ONLY with a valid JSON object: "
            "{\"findings\": [{\"type\": ..., \"severity\": ..., \"line\": ..., \"fix\": ...}], "
            "\"overall_severity\": ..., \"recommendation\": ...}"
        )
        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are a world-class cybersecurity engineer auditing production code.",
                max_tokens=2048,
            )
            raw = result.get("text", "{}")
            # Strip markdown fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            parsed["model_used"] = _HEAVY_MODEL
            parsed["tokens_used"] = result.get("usage", {})
            return parsed
        except Exception as exc:
            logger.warning("Atlas security_scan fallback: %s", exc)
            return {
                "findings": [],
                "overall_severity": "unknown",
                "recommendation": "Could not complete automated scan. Please review manually.",
                "model_used": _HEAVY_MODEL,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Learning (self-improvement base class hook)
    # ------------------------------------------------------------------

    def learn_outcomes(
        self,
        owner_id: str,
        outcomes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Record what worked and what failed so Atlas improves over time."""
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            self.db.client.table("agent_activity").insert({
                "agent_id": "atlas",
                "owner_id": owner_id,
                "action": "learn_outcomes",
                "result": json.dumps({"outcomes": outcomes, "recorded_at": timestamp}),
                "status": "completed",
                "created_at": timestamp,
            }).execute()
        except Exception as exc:
            logger.warning("Atlas learn_outcomes DB write failed: %s", exc)

        return {
            "status": "learned",
            "outcomes_count": len(outcomes),
            "recorded_at": timestamp,
        }

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _call_standard(prompt: str, system: str, max_tokens: int = 2048) -> dict[str, Any]:
        """Call Claude Sonnet for standard tasks."""
        return ask_claude_smart(prompt=prompt, system=system, max_tokens=max_tokens)

    @staticmethod
    def _call_heavy(prompt: str, system: str, max_tokens: int = 4096) -> dict[str, Any]:
        """Call Claude Opus for complex reasoning tasks."""
        return ask_claude_smart(prompt=prompt, system=system, max_tokens=max_tokens)
