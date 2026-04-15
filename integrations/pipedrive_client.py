"""Pipedrive CRM client for ORB Platform.

Agents can use Pipedrive for full sales pipeline management:
  - Create and search persons, organizations, deals
  - Move deals through pipeline stages
  - Log calls, notes, and activities
  - Get pipeline overview and stage stats

Requires:
  PIPEDRIVE_API_KEY  — API key from Pipedrive Settings → Personal Preferences → API

Docs: https://developers.pipedrive.com/docs/api/v1
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.pipedrive")

BASE_URL = "https://api.pipedrive.com/v1"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_pipedrive_available() -> bool:
    return bool(get_settings().resolve("pipedrive_api_key", default=""))


def _api_key() -> str:
    return get_settings().resolve("pipedrive_api_key", default="")


def _get(path: str, params: dict | None = None) -> dict:
    p = dict(params or {})
    p["api_token"] = _api_key()
    qs = urllib.parse.urlencode(p)
    url = f"{BASE_URL}/{path.lstrip('/')}?{qs}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}?api_token={_api_key()}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _put(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}?api_token={_api_key()}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Persons (contacts)
# ---------------------------------------------------------------------------

def search_persons(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search for persons by name, email, or phone."""
    resp = _get("persons/search", {"term": query, "limit": limit, "fields": "name,email,phone"})
    items = resp.get("data", {}).get("items", []) or []
    return [
        {
            "id": i["item"]["id"],
            "name": i["item"].get("name", ""),
            "email": (i["item"].get("emails") or [{}])[0].get("value", ""),
            "phone": (i["item"].get("phones") or [{}])[0].get("value", ""),
            "org": i["item"].get("organization", {}).get("name", "") if i["item"].get("organization") else "",
        }
        for i in items
    ]


def create_person(
    name: str,
    email: str = "",
    phone: str = "",
    org_id: int | None = None,
) -> dict[str, Any]:
    """Create a new person/contact in Pipedrive."""
    body: dict[str, Any] = {"name": name}
    if email:
        body["email"] = [{"value": email, "primary": True}]
    if phone:
        body["phone"] = [{"value": phone, "primary": True}]
    if org_id:
        body["org_id"] = org_id
    resp = _post("persons", body)
    return resp.get("data", resp)


def get_person(person_id: int) -> dict[str, Any]:
    """Get a person by ID."""
    resp = _get(f"persons/{person_id}")
    return resp.get("data", resp)


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

def create_deal(
    title: str,
    person_id: int | None = None,
    org_id: int | None = None,
    value: float = 0,
    currency: str = "USD",
    stage_id: int | None = None,
    pipeline_id: int | None = None,
) -> dict[str, Any]:
    """Create a new deal in the pipeline."""
    body: dict[str, Any] = {"title": title, "value": value, "currency": currency}
    if person_id:
        body["person_id"] = person_id
    if org_id:
        body["org_id"] = org_id
    if stage_id:
        body["stage_id"] = stage_id
    if pipeline_id:
        body["pipeline_id"] = pipeline_id
    resp = _post("deals", body)
    return resp.get("data", resp)


def update_deal_stage(deal_id: int, stage_id: int) -> dict[str, Any]:
    """Move a deal to a different pipeline stage."""
    resp = _put(f"deals/{deal_id}", {"stage_id": stage_id})
    return resp.get("data", resp)


def get_deal(deal_id: int) -> dict[str, Any]:
    """Get deal details."""
    resp = _get(f"deals/{deal_id}")
    return resp.get("data", resp)


def search_deals(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search deals by title."""
    resp = _get("deals/search", {"term": query, "limit": limit})
    items = resp.get("data", {}).get("items", []) or []
    return [
        {
            "id": i["item"]["id"],
            "title": i["item"].get("title", ""),
            "value": i["item"].get("value", 0),
            "currency": i["item"].get("currency", "USD"),
            "status": i["item"].get("status", ""),
            "stage": i["item"].get("stage", {}).get("name", "") if i["item"].get("stage") else "",
        }
        for i in items
    ]


def get_open_deals(limit: int = 20) -> list[dict[str, Any]]:
    """Get all open deals."""
    resp = _get("deals", {"status": "open", "limit": limit, "sort": "update_time DESC"})
    items = resp.get("data") or []
    return [
        {
            "id": d["id"],
            "title": d.get("title", ""),
            "value": d.get("value", 0),
            "stage": d.get("stage_id", ""),
            "person": d.get("person_id", {}).get("name", "") if d.get("person_id") else "",
        }
        for d in items
    ]


# ---------------------------------------------------------------------------
# Activities (notes, calls, meetings)
# ---------------------------------------------------------------------------

def add_note(deal_id: int | None = None, person_id: int | None = None, content: str = "") -> dict[str, Any]:
    """Add a note to a deal or person."""
    body: dict[str, Any] = {"content": content}
    if deal_id:
        body["deal_id"] = deal_id
    if person_id:
        body["person_id"] = person_id
    resp = _post("notes", body)
    return resp.get("data", resp)


def log_activity(
    subject: str,
    activity_type: str = "call",
    deal_id: int | None = None,
    person_id: int | None = None,
    due_date: str | None = None,
    note: str = "",
    done: bool = True,
) -> dict[str, Any]:
    """Log an activity (call, meeting, task, email, deadline).

    Args:
        subject: Activity title.
        activity_type: 'call' | 'meeting' | 'task' | 'deadline' | 'email'
        due_date: ISO date string e.g. '2026-04-15'
        done: Whether activity is already completed.
    """
    body: dict[str, Any] = {
        "subject": subject,
        "type": activity_type,
        "done": 1 if done else 0,
        "note": note,
    }
    if deal_id:
        body["deal_id"] = deal_id
    if person_id:
        body["person_id"] = person_id
    if due_date:
        body["due_date"] = due_date
    resp = _post("activities", body)
    return resp.get("data", resp)


# ---------------------------------------------------------------------------
# Pipeline overview
# ---------------------------------------------------------------------------

def list_pipelines() -> list[dict[str, Any]]:
    """Get all pipelines."""
    resp = _get("pipelines")
    return [{"id": p["id"], "name": p["name"]} for p in (resp.get("data") or [])]


def list_stages(pipeline_id: int | None = None) -> list[dict[str, Any]]:
    """Get stages for a pipeline (or all stages)."""
    params: dict = {}
    if pipeline_id:
        params["pipeline_id"] = pipeline_id
    resp = _get("stages", params)
    return [
        {"id": s["id"], "name": s["name"], "pipeline_id": s["pipeline_id"]}
        for s in (resp.get("data") or [])
    ]


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the authenticated user."""
    try:
        resp = _get("users/me")
        user = resp.get("data", {})
        return {
            "success": True,
            "name": user.get("name"),
            "email": user.get("email"),
            "company": user.get("company_name"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
