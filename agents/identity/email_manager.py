"""Email identity management helpers."""

from __future__ import annotations

import re
from typing import Any


def _slugify_agent_name(agent_name: str) -> str:
    """Converts an agent name into a safe email local-part."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", ".", agent_name.strip().lower())
    cleaned = re.sub(r"\.+", ".", cleaned).strip(".")
    return cleaned or "agent"


def create_agent_email(agent_name: str, domain: str) -> dict[str, Any]:
    """Creates a simple agent email identity.

    For local development this builds a deterministic alias-style address.
    Later Levels can replace this with Google Workspace or Gmail alias APIs.
    """
    safe_domain = (domain or "localhost").replace("http://", "").replace("https://", "").strip("/")
    local_part = _slugify_agent_name(agent_name)
    email_address = f"{local_part}@{safe_domain}"
    return {
        "email_address": email_address,
        "provider": "alias",
        "provisioned": True,
    }
