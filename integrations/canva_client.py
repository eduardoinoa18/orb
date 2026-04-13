"""Minimal Canva integration helpers for ORB.

This module provides:
- API key connectivity checks
- A reliable create URL builder so agents can open Canva with a design type
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from config.settings import get_settings

CANVA_API_BASE = "https://api.canva.com/rest/v1"


def is_canva_available() -> bool:
    settings = get_settings()
    return bool(settings.resolve("canva_api_key"))


def test_canva_connection(api_key: str) -> tuple[bool, str]:
    if not api_key:
        return False, "Missing Canva API key"

    try:
        response = requests.get(
            f"{CANVA_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=12,
        )
        if response.status_code == 200:
            return True, "Canva API reachable"
        if response.status_code in (401, 403):
            return False, "Invalid Canva API key"
        return False, f"Canva API error ({response.status_code})"
    except requests.RequestException as error:
        return False, f"Canva request failed: {error}"


def build_canva_create_url(design_type: str, title: str, prompt: str) -> str:
    safe_type = (design_type or "presentation").strip().lower().replace(" ", "-")
    base = f"https://www.canva.com/create/{quote(safe_type)}/"
    # Keep user context in URL for quick copy/paste into Canva workflow.
    return f"{base}?title={quote(title)}&brief={quote(prompt)}"
