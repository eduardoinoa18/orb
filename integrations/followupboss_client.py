"""Follow Up Boss CRM integration client for ORB Platform.

Allows Commander and agents to:
- Search contacts (people)
- Create new contacts
- Add activity notes to contacts

Requires: FOLLOWUPBOSS_API_KEY in Railway env vars.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("orb.integrations.followupboss")

FUB_API = "https://api.followupboss.com/v1"


def _api_key(override: str | None = None) -> str:
    if override:
        return override
    from config.settings import get_settings
    token = get_settings().resolve("followupboss_api_key")
    if not token:
        raise RuntimeError("FOLLOWUPBOSS_API_KEY not configured.")
    return token


def _headers(api_key_override: str | None = None) -> dict[str, str]:
    token = _api_key(api_key_override)
    raw = f"{token}:".encode("utf-8")
    encoded = base64.b64encode(raw).decode("utf-8")
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def is_followupboss_available() -> bool:
    try:
        from config.settings import get_settings
        return get_settings().is_configured("followupboss_api_key")
    except Exception:
        return False


def _request(method: str, path: str, body: dict[str, Any] | None = None, api_key_override: str | None = None) -> Any:
    url = f"{FUB_API}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(api_key_override), method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_text = e.read().decode("utf-8", errors="replace")
        logger.error("Follow Up Boss API %s %s failed: %s", method, path, error_text)
        raise RuntimeError(f"Follow Up Boss API error {e.code}: {error_text[:240]}") from e
    except Exception as e:
        raise RuntimeError(f"Follow Up Boss error: {e}") from e


def search_people(query: str, limit: int = 10) -> list[dict[str, Any]]:
    q = urllib.parse.quote(query)
    data = _request("GET", f"/people?query={q}&limit={max(1, min(limit, 100))}")
    people = data.get("people", []) if isinstance(data, dict) else []
    return [
        {
            "id": p.get("id"),
            "name": f"{(p.get('firstName') or '').strip()} {(p.get('lastName') or '').strip()}".strip() or "Unknown",
            "email": (p.get("emails") or [{}])[0].get("value", "") if isinstance(p.get("emails"), list) else "",
            "phone": (p.get("phones") or [{}])[0].get("value", "") if isinstance(p.get("phones"), list) else "",
        }
        for p in people
    ]


def create_person(first_name: str, last_name: str, email: str, phone: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
        "emails": [{"value": email}],
    }
    if phone:
        payload["phones"] = [{"value": phone}]

    result = _request("POST", "/people", payload)
    person = result if isinstance(result, dict) else {}
    return {
        "id": person.get("id"),
        "name": f"{first_name} {last_name}".strip(),
        "email": email,
    }


def add_note(person_id: int | str, body: str) -> dict[str, Any]:
    payload = {
        "personId": int(person_id),
        "body": body,
    }
    result = _request("POST", "/notes", payload)
    return {"id": result.get("id") if isinstance(result, dict) else None}


def test_connection(api_key_override: str | None = None) -> tuple[bool, str]:
    try:
        # Lightweight endpoint to validate token and org access.
        data = _request("GET", "/users", api_key_override=api_key_override)
        users = data.get("users", []) if isinstance(data, dict) else []
        return True, f"Follow Up Boss connected ({len(users)} users visible)"
    except Exception as e:
        return False, f"Follow Up Boss connection failed: {e}"
