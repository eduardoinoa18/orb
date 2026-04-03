"""Lightweight Claude client for platform-level checks and prompts."""

from __future__ import annotations

from typing import Any

import anthropic

from config.settings import get_settings


class ClaudeClient:
	"""Tiny wrapper around Anthropic SDK for simple ORB checks."""

	DEFAULT_MODEL = "claude-haiku-4-5-20251001"

	def __init__(self) -> None:
		settings = get_settings()
		self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

	def ask(self, prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 32) -> str:
		"""Sends a simple prompt and returns text response."""
		response = self.client.messages.create(
			model=self.DEFAULT_MODEL,
			max_tokens=max_tokens,
			system=system,
			messages=[{"role": "user", "content": prompt}],
		)
		return response.content[0].text


def ping_claude() -> dict[str, Any]:
	"""Checks Anthropic connectivity with a tiny hello request."""
	text = ClaudeClient().ask(prompt="Reply with exactly: hello", max_tokens=8)
	return {"status": "connected", "response": text.strip()}

