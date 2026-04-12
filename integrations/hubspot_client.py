"""HubSpot CRM integration client for ORB Platform.

Allows Commander and agents to:
- Create and update contacts
- Create deals in the pipeline
- Log notes and activities
- Search contacts by email or name
- Get pipeline and deal stage info
- Track lead status

Requires: HUBSPOT_API_KEY (Private App token) in Railway env vars.
Free tier: Up to 1M API calls/day on free HubSpot plan.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("orb.integrations.hubspot")

HUBSPOT_BASE = "https://api.hubapi.com"


def _headers() -> dict[str, str]:
    from config.settings import get_settings
    token = get_settings().resolve("hubspot_api_key")
    if not token:
        raise RuntimeError("HUBSPOT_API_KEY not configured.")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def is_hubspot_available() -> bool:
    try:
        from config.settings import get_settings
        return get_settings().is_configured("hubspot_api_key")
    except Exception:
        return False


def _request(method: str, path: str, body: dict | None = None) -> Any:
    url = f"{HUBSPOT_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_text = e.read().decode()
        logger.error("HubSpot API %s %s failed: %s", method, path, error_text)
        raise RuntimeError(f"HubSpot error {e.code}: {error_text[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"HubSpot error: {e}") from e


def search_contacts(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search contacts by email, name, or phone.

    Returns: [{id, email, firstname, lastname, company, phone, lifecycle_stage}]
    """
    body = {
        "query": query,
        "limit": limit,
        "properties": ["email", "firstname", "lastname", "company", "phone", "lifecyclestage"],
    }
    result = _request("POST", "/crm/v3/objects/contacts/search", body)
    contacts = []
    for item in result.get("results", []):
        props = item.get("properties", {})
        contacts.append({
            "id": item.get("id"),
            "email": props.get("email", ""),
            "firstname": props.get("firstname", ""),
            "lastname": props.get("lastname", ""),
            "company": props.get("company", ""),
            "phone": props.get("phone", ""),
            "lifecycle_stage": props.get("lifecyclestage", ""),
        })
    return contacts


def get_contact_by_email(email: str) -> dict[str, Any] | None:
    """Fetch a single contact by email address."""
    results = search_contacts(email, limit=1)
    return results[0] if results else None


def create_contact(
    email: str,
    firstname: str = "",
    lastname: str = "",
    company: str = "",
    phone: str = "",
    lifecycle_stage: str = "lead",
    custom_props: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new HubSpot contact.

    Args:
        email: Contact's email (required).
        firstname, lastname, company, phone: Standard fields.
        lifecycle_stage: lead | subscriber | opportunity | customer | evangelist.
        custom_props: Any additional HubSpot property names and values.

    Returns: {id, email, url}
    """
    props: dict[str, str] = {
        "email": email,
        "firstname": firstname,
        "lastname": lastname,
        "company": company,
        "phone": phone,
        "lifecyclestage": lifecycle_stage,
    }
    if custom_props:
        props.update(custom_props)

    result = _request("POST", "/crm/v3/objects/contacts", {"properties": props})
    contact_id = result.get("id")
    logger.info("HubSpot contact created: %s (%s)", email, contact_id)
    return {
        "id": contact_id,
        "email": email,
        "url": f"https://app.hubspot.com/contacts/contact/{contact_id}",
    }


def update_contact(contact_id: str, updates: dict[str, str]) -> bool:
    """Update a contact's properties by ID."""
    _request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", {"properties": updates})
    return True


def create_deal(
    deal_name: str,
    amount: float = 0.0,
    pipeline: str = "default",
    deal_stage: str = "appointmentscheduled",
    contact_ids: list[str] | None = None,
    close_date: str | None = None,
) -> dict[str, Any]:
    """Create a deal in the CRM pipeline.

    Args:
        deal_name: Name of the deal.
        amount: Deal value in dollars.
        pipeline: Pipeline ID (default = "default").
        deal_stage: Stage ID within the pipeline.
        contact_ids: List of contact IDs to associate.
        close_date: Expected close date in YYYY-MM-DD format.

    Returns: {id, deal_name, url}
    """
    props: dict[str, Any] = {
        "dealname": deal_name,
        "amount": str(amount),
        "pipeline": pipeline,
        "dealstage": deal_stage,
    }
    if close_date:
        props["closedate"] = close_date

    body: dict[str, Any] = {"properties": props}

    # Associate contacts
    if contact_ids:
        body["associations"] = [
            {
                "to": {"id": cid},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
            }
            for cid in contact_ids
        ]

    result = _request("POST", "/crm/v3/objects/deals", body)
    deal_id = result.get("id")
    logger.info("HubSpot deal created: %s (%s)", deal_name, deal_id)
    return {
        "id": deal_id,
        "deal_name": deal_name,
        "url": f"https://app.hubspot.com/contacts/deals/{deal_id}",
    }


def log_note(
    contact_id: str,
    note_body: str,
) -> dict[str, Any]:
    """Log an activity note on a contact."""
    from datetime import datetime, timezone
    props = {
        "hs_note_body": note_body,
        "hs_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body: dict[str, Any] = {
        "properties": props,
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}],
            }
        ],
    }
    result = _request("POST", "/crm/v3/objects/notes", body)
    return {"id": result.get("id")}


def get_recent_deals(limit: int = 10) -> list[dict[str, Any]]:
    """Get the most recently modified deals."""
    result = _request(
        "GET",
        f"/crm/v3/objects/deals?limit={limit}&properties=dealname,amount,dealstage,closedate&sort=-hs_lastmodifieddate",
    )
    deals = []
    for item in result.get("results", []):
        props = item.get("properties", {})
        deals.append({
            "id": item.get("id"),
            "name": props.get("dealname", ""),
            "amount": props.get("amount", "0"),
            "stage": props.get("dealstage", ""),
            "close_date": props.get("closedate", ""),
        })
    return deals


def test_connection() -> tuple[bool, str]:
    """Verify HubSpot token by fetching account info."""
    try:
        result = _request("GET", "/account-info/v3/details")
        portal_id = result.get("portalId", "unknown")
        return True, f"Connected to HubSpot portal {portal_id}"
    except Exception as e:
        return False, f"HubSpot connection failed: {e}"
