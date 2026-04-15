"""Mailchimp Marketing API client for ORB Platform.

Agents can use Mailchimp to:
  - Add / update subscribers in any audience list
  - Tag subscribers for segmentation
  - Trigger automated email sequences (Customer Journeys)
  - Send transactional emails via Mandrill (if enabled)
  - Pull campaign stats
  - Create audience segments

Requires:
  MAILCHIMP_API_KEY    — API key from Mailchimp Account → Extras → API Keys
  MAILCHIMP_SERVER     — Server prefix from the API key e.g. 'us6' (last part after '-')
  MAILCHIMP_LIST_ID    — Default Audience/List ID (optional, can be passed per-call)

Docs: https://mailchimp.com/developer/marketing/api/
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.mailchimp")


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_mailchimp_available() -> bool:
    s = get_settings()
    return bool(
        s.resolve("mailchimp_api_key", default="")
        and s.resolve("mailchimp_server", default="")
    )


def _api_key() -> str:
    return get_settings().resolve("mailchimp_api_key", default="")


def _server() -> str:
    s = get_settings().resolve("mailchimp_server", default="")
    if s:
        return s
    # Auto-detect from API key format: xxxxx-us6 → us6
    key = _api_key()
    if "-" in key:
        return key.split("-")[-1]
    return "us1"


def _list_id() -> str:
    return get_settings().resolve("mailchimp_list_id", default="")


def _base_url() -> str:
    return f"https://{_server()}.api.mailchimp.com/3.0"


def _headers() -> dict[str, str]:
    creds = base64.b64encode(f"anystring:{_api_key()}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{_base_url()}/{path.lstrip('/')}{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = f"{_base_url()}/{path.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _put(path: str, body: dict) -> dict:
    url = f"{_base_url()}/{path.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _patch(path: str, body: dict) -> dict:
    url = f"{_base_url()}/{path.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _subscriber_hash(email: str) -> str:
    import hashlib
    return hashlib.md5(email.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

def add_subscriber(
    email: str,
    first_name: str = "",
    last_name: str = "",
    tags: list[str] | None = None,
    list_id: str | None = None,
    status: str = "subscribed",
    merge_fields: dict | None = None,
) -> dict[str, Any]:
    """Add or update a subscriber in an audience list.

    Args:
        email: Subscriber email.
        first_name: First name (maps to FNAME merge field).
        last_name: Last name (maps to LNAME merge field).
        tags: Tags to apply immediately.
        list_id: Audience list ID (falls back to MAILCHIMP_LIST_ID).
        status: 'subscribed' | 'pending' | 'unsubscribed' | 'cleaned'
        merge_fields: Extra merge fields dict.

    Returns: Member resource dict.
    """
    lid = list_id or _list_id()
    h = _subscriber_hash(email)

    mf = {"FNAME": first_name, "LNAME": last_name}
    if merge_fields:
        mf.update(merge_fields)

    body: dict[str, Any] = {
        "email_address": email,
        "status_if_new": status,
        "merge_fields": mf,
    }
    member = _put(f"lists/{lid}/members/{h}", body)

    if tags:
        add_tags(email, tags, list_id=lid)

    return member


def get_subscriber(email: str, list_id: str | None = None) -> dict[str, Any]:
    """Fetch a subscriber's record."""
    lid = list_id or _list_id()
    h = _subscriber_hash(email)
    return _get(f"lists/{lid}/members/{h}")


def update_subscriber_status(email: str, status: str, list_id: str | None = None) -> dict[str, Any]:
    """Change a subscriber's status.

    Args:
        status: 'subscribed' | 'unsubscribed' | 'pending'
    """
    lid = list_id or _list_id()
    h = _subscriber_hash(email)
    return _patch(f"lists/{lid}/members/{h}", {"status": status})


def unsubscribe(email: str, list_id: str | None = None) -> dict[str, Any]:
    """Unsubscribe a member from a list."""
    return update_subscriber_status(email, "unsubscribed", list_id=list_id)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def add_tags(email: str, tags: list[str], list_id: str | None = None) -> bool:
    """Add tags to a subscriber.

    Args:
        email: Subscriber email.
        tags: List of tag names to add.
    """
    lid = list_id or _list_id()
    h = _subscriber_hash(email)
    body = {"tags": [{"name": t, "status": "active"} for t in tags]}
    try:
        _post(f"lists/{lid}/members/{h}/tags", body)
        return True
    except Exception as e:
        logger.warning("Failed to add tags: %s", e)
        return False


def remove_tags(email: str, tags: list[str], list_id: str | None = None) -> bool:
    """Remove tags from a subscriber."""
    lid = list_id or _list_id()
    h = _subscriber_hash(email)
    body = {"tags": [{"name": t, "status": "inactive"} for t in tags]}
    try:
        _post(f"lists/{lid}/members/{h}/tags", body)
        return True
    except Exception as e:
        logger.warning("Failed to remove tags: %s", e)
        return False


# ---------------------------------------------------------------------------
# Lists (Audiences)
# ---------------------------------------------------------------------------

def list_audiences() -> list[dict[str, Any]]:
    """Get all audience lists.

    Returns: List of {id, name, stats{member_count}, date_created}.
    """
    resp = _get("lists", {"count": 50})
    return [
        {
            "id": l.get("id"),
            "name": l.get("name"),
            "member_count": l.get("stats", {}).get("member_count", 0),
            "date_created": l.get("date_created", ""),
        }
        for l in resp.get("lists", [])
    ]


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def list_campaigns(count: int = 10) -> list[dict[str, Any]]:
    """Get recent campaigns.

    Returns: List of {id, subject_line, status, send_time, opens_total}.
    """
    resp = _get("campaigns", {"count": count, "sort_field": "send_time", "sort_dir": "DESC"})
    return [
        {
            "id": c.get("id"),
            "subject": c.get("settings", {}).get("subject_line", ""),
            "status": c.get("status"),
            "send_time": c.get("send_time", ""),
            "opens": c.get("report_summary", {}).get("opens", 0),
            "clicks": c.get("report_summary", {}).get("clicks", 0),
        }
        for c in resp.get("campaigns", [])
    ]


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by pinging the account info endpoint."""
    try:
        resp = _get("/")
        return {
            "success": True,
            "account_name": resp.get("account_name"),
            "email": resp.get("email"),
            "total_subscribers": resp.get("total_subscribers", 0),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
