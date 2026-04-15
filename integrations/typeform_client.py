"""Typeform client for ORB Platform.

Agents can use Typeform to:
  - Retrieve form submissions as structured leads
  - List forms and their response counts
  - Get specific responses with all answers
  - Generate pre-filled form links (for targeted outreach)
  - Monitor for new responses

This is powerful for real estate lead capture — build a buyer/seller
questionnaire in Typeform and agents automatically process each submission.

Requires:
  TYPEFORM_API_KEY   — Personal access token from Typeform Account → Developer

Docs: https://www.typeform.com/developers/create/
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.typeform")

BASE_URL = "https://api.typeform.com"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_typeform_available() -> bool:
    return bool(get_settings().resolve("typeform_api_key", default=""))


def _api_key() -> str:
    return get_settings().resolve("typeform_api_key", default="")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE_URL}/{path.lstrip('/')}{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

def list_forms(page_size: int = 20) -> list[dict[str, Any]]:
    """List all Typeform forms.

    Returns: List of {id, title, response_count, last_updated, link}.
    """
    resp = _get("forms", {"page_size": page_size})
    return [
        {
            "id": f.get("id"),
            "title": f.get("title"),
            "response_count": f.get("_links", {}).get("responses", ""),
            "last_updated": f.get("last_updated_at", ""),
            "link": f.get("_links", {}).get("display", ""),
        }
        for f in resp.get("items", [])
    ]


def get_form(form_id: str) -> dict[str, Any]:
    """Get form details including all fields/questions."""
    return _get(f"forms/{form_id}")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

def get_responses(
    form_id: str,
    page_size: int = 25,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """Get form responses as structured lead records.

    Args:
        form_id: Typeform form ID.
        page_size: Max responses per call.
        since: ISO timestamp — only responses after this date.
        until: ISO timestamp — only responses before this date.

    Returns: List of normalized response dicts with {response_id, submitted_at, answers}.
    """
    params: dict[str, Any] = {"page_size": page_size}
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    resp = _get(f"forms/{form_id}/responses", params)
    results = []
    for r in resp.get("items", []):
        answers: dict[str, str] = {}
        for ans in r.get("answers", []):
            field_ref = ans.get("field", {}).get("ref", ans.get("field", {}).get("id", ""))
            field_type = ans.get("type", "")
            # Extract value based on answer type
            if field_type in ("short_text", "long_text", "email", "url", "number"):
                answers[field_ref] = str(ans.get(field_type, ""))
            elif field_type == "choice":
                answers[field_ref] = ans.get("choice", {}).get("label", "")
            elif field_type == "choices":
                answers[field_ref] = ", ".join(
                    c.get("label", "") for c in ans.get("choices", {}).get("labels", [])
                )
            elif field_type == "boolean":
                answers[field_ref] = "Yes" if ans.get("boolean") else "No"
            elif field_type == "phone_number":
                answers[field_ref] = ans.get("phone_number", "")
            elif field_type == "date":
                answers[field_ref] = ans.get("date", "")
            else:
                answers[field_ref] = str(ans.get(field_type, ""))

        results.append({
            "response_id": r.get("response_id"),
            "submitted_at": r.get("submitted_at"),
            "answers": answers,
            "score": r.get("calculated", {}).get("score"),
        })
    return results


def get_latest_responses(form_id: str, count: int = 10) -> list[dict[str, Any]]:
    """Get the most recent responses (convenience wrapper)."""
    return get_responses(form_id, page_size=count)


def get_response_count(form_id: str) -> int:
    """Get total number of responses for a form."""
    try:
        resp = _get(f"forms/{form_id}/responses", {"page_size": 1})
        return resp.get("total_items", 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Pre-filled links
# ---------------------------------------------------------------------------

def create_prefilled_link(form_id: str, prefill: dict[str, str]) -> str:
    """Generate a pre-filled Typeform link.

    Args:
        form_id: Form ID.
        prefill: Dict of field_ref → value to pre-fill.

    Returns: URL with query params for pre-filling.

    Example:
        create_prefilled_link("abc123", {"name": "Jane", "email": "jane@example.com"})
    """
    base = f"https://form.typeform.com/to/{form_id}"
    if not prefill:
        return base
    qs = urllib.parse.urlencode({f"#{k}": v for k, v in prefill.items()})
    return f"{base}?{qs}"


# ---------------------------------------------------------------------------
# Webhook management
# ---------------------------------------------------------------------------

def list_webhooks(form_id: str) -> list[dict[str, Any]]:
    """List webhooks configured for a form."""
    resp = _get(f"forms/{form_id}/webhooks")
    return resp.get("items", [])


def create_webhook(form_id: str, url: str, tag: str = "orb_platform") -> dict[str, Any]:
    """Add a webhook to a form so ORB gets notified on new responses.

    Args:
        form_id: Form to watch.
        url: Your ORB webhook endpoint URL.
        tag: Identifier tag for the webhook.
    """
    import urllib.request as ur
    webhook_url = f"{BASE_URL}/forms/{form_id}/webhooks/{tag}"
    body = json.dumps({"url": url, "enabled": True}).encode()
    req = ur.Request(webhook_url, data=body, headers={**_headers(), "Content-Type": "application/json"}, method="PUT")
    with ur.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the account profile."""
    try:
        resp = _get("me")
        return {
            "success": True,
            "alias": resp.get("alias"),
            "email": resp.get("email"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
