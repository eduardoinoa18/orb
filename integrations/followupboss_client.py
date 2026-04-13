"""Follow Up Boss CRM integration client for ORB Platform.

Full-featured real estate CRM integration. Allows Commander and agents to:
- Search and manage contacts (leads, buyers, sellers)
- Create and update people (leads)
- Add notes and log calls
- Manage deals/transactions
- Create and assign tasks
- Read smart lists
- Push inbound lead events
- Track pipeline stages

Follow Up Boss API docs: https://docs.followupboss.com/reference
Auth: Basic auth with API key as username, no password.

Requires: FOLLOWUPBOSS_API_KEY in Railway env vars.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

logger = logging.getLogger("orb.integrations.followupboss")

FUB_BASE = "https://api.followupboss.com/v1"


def _headers(api_key_override: str | None = None) -> dict[str, str]:
    from config.settings import get_settings
    api_key = api_key_override or get_settings().resolve("followupboss_api_key")
    if not api_key:
        raise RuntimeError("FOLLOWUPBOSS_API_KEY not configured.")
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def is_followupboss_available() -> bool:
    """Check whether Follow Up Boss is configured."""
    try:
        from config.settings import get_settings
        return get_settings().is_configured("followupboss_api_key")
    except Exception:
        return False


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    api_key_override: str | None = None,
) -> Any:
    """Make an authenticated request to the FUB API."""
    url = f"{FUB_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url += ("&" if "?" in url else "?") + qs
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(api_key_override), method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        error_text = e.read().decode()
        logger.error("FUB API %s %s failed (%s): %s", method, path, e.code, error_text[:300])
        raise RuntimeError(f"Follow Up Boss error {e.code}: {error_text[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"Follow Up Boss error: {e}") from e


# ---------------------------------------------------------------------------
# People (Contacts / Leads)
# ---------------------------------------------------------------------------

def search_people(
    query: str = "",
    sort: str = "created",
    limit: int = 20,
    tags: str | None = None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    """Search contacts/leads in Follow Up Boss.

    Returns: [{id, name, emails, phones, stage, tags, source, created, assignedTo}]
    """
    params: dict[str, Any] = {"sort": sort, "limit": min(limit, 100)}
    if query:
        params["query"] = query
    if tags:
        params["tags"] = tags
    if stage:
        params["stage"] = stage

    result = _request("GET", "/people", params=params)
    people = result.get("people", []) if isinstance(result, dict) else []

    return [
        {
            "id": p.get("id"),
            "firstName": p.get("firstName", ""),
            "lastName": p.get("lastName", ""),
            "name": f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(),
            "emails": [e.get("value") for e in (p.get("emails") or [])],
            "phones": [ph.get("value") for ph in (p.get("phones") or [])],
            "stage": p.get("stage", ""),
            "tags": p.get("tags", []),
            "source": p.get("source", ""),
            "created": p.get("created", ""),
            "assignedTo": p.get("assignedTo", ""),
            "lastActivity": p.get("lastActivity", ""),
            "price": p.get("price"),
            "propertyType": p.get("propertyType", ""),
        }
        for p in people
    ]


def get_person(person_id: int) -> dict[str, Any]:
    """Get a single contact/lead by ID."""
    return _request("GET", f"/people/{person_id}") or {}


def create_person(
    first_name: str,
    last_name: str = "",
    email: str = "",
    phone: str = "",
    source: str = "ORB Platform",
    stage: str = "Lead",
    tags: list[str] | None = None,
    assigned_to: str | None = None,
    custom_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new lead/contact in Follow Up Boss."""
    body: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
        "source": source,
        "stage": stage,
    }
    if email:
        body["emails"] = [{"value": email, "type": "home"}]
    if phone:
        body["phones"] = [{"value": phone, "type": "mobile"}]
    if tags:
        body["tags"] = tags
    if assigned_to:
        body["assignedTo"] = assigned_to
    if custom_fields:
        body.update(custom_fields)

    result = _request("POST", "/people", body)
    person_id = result.get("id")
    logger.info("FUB person created: %s %s (ID: %s)", first_name, last_name, person_id)
    return {"id": person_id, "name": f"{first_name} {last_name}".strip(), "stage": stage}


def update_person(person_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    """Update a contact's fields by ID."""
    return _request("PUT", f"/people/{person_id}", updates) or {}


def add_tag(person_id: int, tag: str) -> bool:
    """Add a tag to a contact."""
    person = get_person(person_id)
    existing = person.get("tags", []) or []
    if tag not in existing:
        existing.append(tag)
        update_person(person_id, {"tags": existing})
    return True


def change_stage(person_id: int, stage: str) -> bool:
    """Move a contact to a different pipeline stage."""
    update_person(person_id, {"stage": stage})
    logger.info("FUB person %s moved to stage '%s'", person_id, stage)
    return True


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def add_note(person_id: int, body: str, subject: str = "") -> dict[str, Any]:
    """Add a note to a contact."""
    payload: dict[str, Any] = {"personId": person_id, "body": body}
    if subject:
        payload["subject"] = subject
    result = _request("POST", "/notes", payload)
    return {"id": result.get("id")}


def get_notes(person_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Get recent notes for a contact."""
    result = _request("GET", "/notes", params={"personId": str(person_id), "limit": str(limit)})
    return [
        {"id": n.get("id"), "subject": n.get("subject", ""), "body": n.get("body", ""), "created": n.get("created", "")}
        for n in (result.get("notes", []) if isinstance(result, dict) else [])
    ]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def create_task(
    person_id: int,
    name: str,
    due_date: str,
    description: str = "",
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Create a task for a contact."""
    payload: dict[str, Any] = {"personId": person_id, "name": name, "dueDate": due_date, "description": description}
    if assigned_to:
        payload["assignedTo"] = assigned_to
    result = _request("POST", "/tasks", payload)
    return {"id": result.get("id"), "name": name}


def get_tasks(person_id: int | None = None, status: str = "pending", limit: int = 20) -> list[dict[str, Any]]:
    """Get tasks, optionally filtered by contact or status."""
    params: dict[str, str] = {"status": status, "limit": str(limit)}
    if person_id:
        params["personId"] = str(person_id)
    result = _request("GET", "/tasks", params=params)
    return [
        {"id": t.get("id"), "name": t.get("name", ""), "personId": t.get("personId"),
         "dueDate": t.get("dueDate", ""), "status": t.get("status", "pending"), "assignedTo": t.get("assignedTo", "")}
        for t in (result.get("tasks", []) if isinstance(result, dict) else [])
    ]


def complete_task(task_id: int) -> bool:
    """Mark a task as completed."""
    _request("PUT", f"/tasks/{task_id}", {"status": "completed"})
    return True


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

def log_call(person_id: int, outcome: str = "Connected", duration_seconds: int = 0, note: str = "") -> dict[str, Any]:
    """Log a phone call to a contact."""
    payload: dict[str, Any] = {"personId": person_id, "outcome": outcome, "duration": duration_seconds}
    if note:
        payload["note"] = note
    result = _request("POST", "/calls", payload)
    return {"id": result.get("id")}


# ---------------------------------------------------------------------------
# Deals / Transactions
# ---------------------------------------------------------------------------

def create_deal(
    person_id: int,
    name: str,
    price: float = 0,
    stage: str = "Pre-Approval",
    deal_type: str = "Buyer",
    property_address: str = "",
) -> dict[str, Any]:
    """Create a deal/transaction for a contact."""
    payload: dict[str, Any] = {
        "personId": person_id, "name": name, "price": price, "stage": stage, "dealType": deal_type,
    }
    if property_address:
        payload["propertyAddress"] = property_address
    result = _request("POST", "/deals", payload)
    return {"id": result.get("id"), "name": name}


def get_deals(person_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Get deals, optionally filtered by contact."""
    params: dict[str, str] = {"limit": str(limit)}
    if person_id:
        params["personId"] = str(person_id)
    result = _request("GET", "/deals", params=params)
    return [
        {"id": d.get("id"), "name": d.get("name", ""), "stage": d.get("stage", ""),
         "price": d.get("price"), "dealType": d.get("dealType", ""), "created": d.get("created", "")}
        for d in (result.get("deals", []) if isinstance(result, dict) else [])
    ]


# ---------------------------------------------------------------------------
# Events (inbound lead capture)
# ---------------------------------------------------------------------------

def push_event(
    source: str,
    event_type: str,
    person: dict[str, Any],
    description: str = "",
    property_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Push an inbound lead event to Follow Up Boss.

    Used by landing pages and lead sources to push new leads in.
    """
    payload: dict[str, Any] = {"source": source, "type": event_type, "person": person}
    if description:
        payload["description"] = description
    if property_info:
        payload["property"] = property_info
    return _request("POST", "/events", payload)


# ---------------------------------------------------------------------------
# Smart Lists
# ---------------------------------------------------------------------------

def get_smart_lists() -> list[dict[str, Any]]:
    """Get all smart lists defined in Follow Up Boss."""
    result = _request("GET", "/smartLists")
    return [
        {"id": sl.get("id"), "name": sl.get("name", ""), "count": sl.get("count", 0)}
        for sl in (result.get("smartlists", []) if isinstance(result, dict) else [])
    ]


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection(api_key_override: str | None = None) -> tuple[bool, str]:
    """Verify Follow Up Boss API key works."""
    try:
        data = _request("GET", "/me", api_key_override=api_key_override)
        name = data.get("name", "Unknown") if isinstance(data, dict) else "Unknown"
        return True, f"Connected to Follow Up Boss as '{name}'"
    except Exception as e:
        return False, f"Follow Up Boss connection failed: {e}"
