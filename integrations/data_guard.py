"""ORB DataGuard — Module 4, Step S7.

Prevents sensitive values (API keys, passwords, card numbers) from
appearing in logs, API responses, or activity records.

Usage:
    from integrations.data_guard import DataGuard, get_data_guard
    guard = get_data_guard()
    safe  = guard.redact("my key is sk-ant-xxxx and password=hunter2")
    ok    = guard.is_safe_to_log(text)
"""

from __future__ import annotations

import re
from functools import lru_cache


class DataGuard:
    """Scans text for sensitive data patterns and redacts them."""

    # Patterns that should never appear in plain-text logs or responses.
    SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r'sk-ant-[a-zA-Z0-9\-_]{20,}', re.IGNORECASE),  # Anthropic
        re.compile(r'(?<![a-zA-Z])sk-[a-zA-Z0-9]{20,}', re.IGNORECASE),  # OpenAI
        re.compile(r'AC[a-zA-Z0-9]{32}', re.IGNORECASE),            # Twilio SID
        re.compile(r'[a-zA-Z0-9]{32}'),                              # Twilio token (32-char hex)
        re.compile(r'\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}'),         # Card numbers
        re.compile(r'\d{3}-\d{2}-\d{4}'),                           # SSN
        re.compile(r'(?i)password\s*[=:]\s*\S+'),                   # password= patterns
        re.compile(r'(?i)api_key\s*[=:]\s*\S+'),                    # api_key= patterns
        re.compile(r'(?i)(?:secret|token|auth)\s*[=:]\s*[^\s,\n]{8,}'),  # secret=, token=
        re.compile(r'gAAA[a-zA-Z0-9\-_=]{40,}'),                   # Fernet encrypted values
    ]

    REDACTION_LABEL = "[REDACTED]"

    def scan_for_sensitive(self, text: str) -> list[dict[str, str]]:
        """Return a list of findings without revealing the actual values.

        Each finding contains *type* (pattern name) and *location* (char offset).
        """
        if not isinstance(text, str):
            return []

        findings: list[dict[str, str]] = []
        for pattern in self.SENSITIVE_PATTERNS:
            for match in pattern.finditer(text):
                findings.append({
                    "type": pattern.pattern[:40],
                    "position": str(match.start()),
                    "length": str(len(match.group())),
                })
        return findings

    def redact(self, text: str) -> str:
        """Replace all sensitive values in *text* with [REDACTED].

        The returned string is safe to log or display.
        """
        if not isinstance(text, str):
            return text
        result = text
        for pattern in self.SENSITIVE_PATTERNS:
            result = pattern.sub(self.REDACTION_LABEL, result)
        return result

    def is_safe_to_log(self, text: str) -> bool:
        """Return False if *text* contains any sensitive patterns.

        Use this before every activity_log write.
        """
        if not isinstance(text, str):
            return True
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern.search(text):
                return False
        return True

    def safe_for_log(self, text: str) -> str:
        """Return *text* unchanged if safe, or redact it if not.

        Drop-in for any log call: log_activity(description=guard.safe_for_log(desc))
        """
        if self.is_safe_to_log(text):
            return text
        return self.redact(text)


@lru_cache(maxsize=1)
def get_data_guard() -> DataGuard:
    """Return a cached singleton DataGuard instance."""
    return DataGuard()
