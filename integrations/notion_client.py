"""Notion integration client for ORB Platform.

Allows Commander and agents to:
- Create and update pages in any database
- Search across the workspace
- Append blocks to existing pages (notes, logs)
- Read database entries (CRM, tasks, leads)
- Create meeting notes automatically

Requires: NOTION_API_KEY and NOTION_DATABASE_ID in Railway env vars.
Free tier: unlimited API calls on free Notion plan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orb.integrations.notion")

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def _headers() -> dict[str, str]:
    from config.settings import get_settings
    settings = get_settings()
    token = settings.resolve("notion_api_key")
    if not token:
        raise RuntimeError("NOTION_API_KEY not configured.")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def is_notion_available() -> bool:
    try:
        from config.settings import get_settings
        return get_settings().is_configured("notion_api_key")
    except Exception:
        return False


def _request(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    """Make an authenticated request to the Notion API."""
    import json
    import urllib.request

    url = f"{NOTION_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        logger.error("Notion API %s %s failed: %s %s", method, path, e.code, body_text)
        raise RuntimeError(f"Notion API error {e.code}: {body_text[:200]}") from e
    except Exception as e:
        logger.error("Notion request failed: %s", e)
        raise RuntimeError(f"Notion error: {e}") from e


def search(query: str, filter_type: str = "page") -> list[dict[str, Any]]:
    """Search Notion workspace for pages or databases.

    Returns: [{id, title, url, type, last_edited}]
    """
    result = _request("POST", "/search", {
        "query": query,
        "filter": {"value": filter_type, "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "page_size": 20,
    })

    items = []
    for obj in result.get("results", []):
        title_prop = (
            obj.get("title")
            or obj.get("properties", {}).get("Name", {}).get("title", [])
            or obj.get("properties", {}).get("title", {}).get("title", [])
        )
        if isinstance(title_prop, list) and title_prop:
            title = title_prop[0].get("plain_text", "Untitled")
        else:
            title = "Untitled"

        items.append({
            "id": obj.get("id"),
            "title": title,
            "url": obj.get("url"),
            "type": obj.get("object"),
            "last_edited": obj.get("last_edited_time"),
        })

    return items


def get_database_entries(
    database_id: str,
    filter_payload: dict | None = None,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Query a Notion database.

    Args:
        database_id: Notion database ID.
        filter_payload: Optional Notion filter object.
        max_results: Limit results.

    Returns: List of page property dicts.
    """
    body: dict[str, Any] = {"page_size": min(max_results, 100)}
    if filter_payload:
        body["filter"] = filter_payload

    result = _request("POST", f"/databases/{database_id}/query", body)

    entries = []
    for page in result.get("results", []):
        props = page.get("properties", {})
        flat: dict[str, Any] = {"id": page.get("id"), "url": page.get("url")}
        for prop_name, prop_val in props.items():
            prop_type = prop_val.get("type")
            if prop_type == "title":
                texts = prop_val.get("title", [])
                flat[prop_name] = "".join(t.get("plain_text", "") for t in texts)
            elif prop_type == "rich_text":
                texts = prop_val.get("rich_text", [])
                flat[prop_name] = "".join(t.get("plain_text", "") for t in texts)
            elif prop_type == "select":
                sel = prop_val.get("select") or {}
                flat[prop_name] = sel.get("name", "")
            elif prop_type == "multi_select":
                flat[prop_name] = [s.get("name", "") for s in prop_val.get("multi_select", [])]
            elif prop_type in ("number", "checkbox", "url", "email", "phone_number"):
                flat[prop_name] = prop_val.get(prop_type)
            elif prop_type == "date":
                date_obj = prop_val.get("date") or {}
                flat[prop_name] = date_obj.get("start")
            else:
                flat[prop_name] = None
        entries.append(flat)

    return entries


def create_page(
    database_id: str,
    title: str,
    properties: dict[str, Any] | None = None,
    content_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new page in a Notion database.

    Args:
        database_id: Target database.
        title: Page title.
        properties: Additional property values (Notion property format).
        content_blocks: Optional list of Notion block objects.

    Returns: {id, url}
    """
    page_props: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": title}}]},
    }
    if properties:
        page_props.update(properties)

    body: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": page_props,
    }
    if content_blocks:
        body["children"] = content_blocks

    result = _request("POST", "/pages", body)
    logger.info("Notion page created: %s", title)
    return {"id": result.get("id"), "url": result.get("url")}


def append_blocks(page_id: str, blocks: list[dict[str, Any]]) -> bool:
    """Append content blocks to an existing Notion page.

    Useful for logging events, appending meeting notes, etc.
    """
    _request("PATCH", f"/blocks/{page_id}/children", {"children": blocks})
    return True


def create_text_block(text: str) -> dict[str, Any]:
    """Helper: build a paragraph block."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def create_heading_block(text: str, level: int = 2) -> dict[str, Any]:
    """Helper: build a heading block (level 1-3)."""
    htype = f"heading_{min(max(level, 1), 3)}"
    return {
        "object": "block",
        "type": htype,
        htype: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def log_event(page_id: str, event: str, details: str = "") -> bool:
    """Append a timestamped event log entry to a Notion page."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks = [
        create_heading_block(f"[{now}] {event}", level=3),
    ]
    if details:
        blocks.append(create_text_block(details))
    return append_blocks(page_id, blocks)


def test_connection() -> tuple[bool, str]:
    """Verify Notion connectivity."""
    try:
        _request("GET", "/users/me")
        return True, "Notion API connected successfully"
    except Exception as e:
        return False, f"Notion error: {e}"
