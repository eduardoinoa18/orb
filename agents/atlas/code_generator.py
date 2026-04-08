"""Atlas Code Generator — Module 1, Step A1.

Generates production-ready Python code (with tests) for a described feature.
Uses Claude Sonnet for cost-efficiency; falls back to a structured scaffold
if the API is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.atlas.atlas_brain import AtlasBrain

logger = logging.getLogger("orb.atlas.code_generator")


class CodeGenerator:
    """Generates production Python code from a plain-English description."""

    SYSTEM_PROMPT = (
        "You are Atlas, a senior Python engineer specializing in FastAPI, Pydantic v2, "
        "and async patterns. You write clean, secure, testable code that follows "
        "PEP 8 and OWASP secure coding guidelines. Include docstrings and type hints. "
        "Never hardcode secrets or credentials."
    )

    def __init__(self, brain: "AtlasBrain") -> None:
        self._brain = brain

    def generate_feature(
        self,
        feature_description: str,
        owner_id: str,
        context_files: list[str],
    ) -> dict[str, Any]:
        """Generate code for *feature_description*.

        Args:
            feature_description: Plain-English description.
            owner_id: Requesting owner (for activity logging).
            context_files: Up to 5 existing file contents for context.

        Returns:
            dict with keys: code, explanation, tests, model_used, tokens_used
        """
        # Build context section (truncate each file to 300 chars to stay within limits)
        context_section = ""
        if context_files:
            snippets = [f[:300] for f in context_files[:5]]
            context_section = "\n\nExisting code context:\n```python\n" + "\n---\n".join(snippets) + "\n```"

        prompt = (
            f"Generate production-ready Python code for this feature:\n\n"
            f"Feature: {feature_description}"
            f"{context_section}\n\n"
            "Respond ONLY with a valid JSON object:\n"
            '{"code": "...full source code...", '
            '"explanation": "...what it does and why...", '
            '"tests": "...pytest test code..."}'
        )

        try:
            result = self._brain._call_standard(
                prompt=prompt,
                system=self.SYSTEM_PROMPT,
                max_tokens=2048,
            )
            raw = result.get("text", "{}")
            raw = _strip_fences(raw)
            parsed = json.loads(raw)
            parsed.setdefault("code", "")
            parsed.setdefault("explanation", "")
            parsed.setdefault("tests", "")
            parsed["model_used"] = "claude-3-5-sonnet-20241022"
            parsed["tokens_used"] = result.get("usage", {})
            return parsed
        except Exception as exc:
            logger.warning("CodeGenerator fallback for '%s': %s", feature_description[:60], exc)
            return _fallback_scaffold(feature_description, str(exc))


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from an API response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            return inner.strip()
    return text


def _fallback_scaffold(feature_description: str, error: str) -> dict[str, Any]:
    """Return a minimal scaffold when the AI call fails."""
    slug = feature_description[:40].lower().replace(" ", "_")
    return {
        "code": f'"""TODO: Implement {feature_description}"""\n\ndef {slug[:20]}():\n    raise NotImplementedError("{feature_description}")\n',
        "explanation": f"Atlas could not generate code automatically. Error: {error}",
        "tests": f'def test_{slug[:20]}():\n    pass  # TODO\n',
        "model_used": "fallback",
        "tokens_used": {},
    }
