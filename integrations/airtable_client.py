"""Airtable client for ORB Platform.

Agents can use Airtable as a flexible database for leads, properties,
projects, tasks, content calendars, or any custom business data.

Capabilities:
  - Read records from any table / view
  - Create and update records
  - Search / filter with formula queries
  - Delete records
  - List tables and fields in a base

Requires:
  AIRTABLE_API_KEY  — Personal Access Token (starts with 'pat...')
  AIRTABLE_BASE_ID  — Base ID from the Airtable URL (starts with 'app...')

Docs: https://airtable.com/developers/web/api/introduction
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.airtable")

BASE_URL = "https://api.airtable.com/v0"
META_URL = "https://api.airtable.com/v0/meta"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_airtable_available() -> bool:
    s = get_settings()
    return bool(
        s.resolve("airtable_api_key", default="")
        and s.resolve("airtable_base_id", default="")
    )


def _api_key() -> str:
    return get_settings().resolve("airtable_api_key", default="")


def _base_id() -> str:
    return get_settings().resolve("airtable_base_id", default="")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    url = f"{BASE_URL}/{_base_id()}/{path}{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{_base_id()}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _patch(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{_base_id()}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _delete(path: str) -> dict:
    url = f"{BASE_URL}/{_base_id()}/{path}"
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def list_records(
    table: str,
    view: str | None = None,
    filter_formula: str | None = None,
    max_records: int = 50,
    sort: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Fetch records from a table.

    Args:
        table: Table name or ID.
        view: Optional view name/ID to scope records.
        filter_formula: Airtable formula string e.g. "{Status}='Active'"
        max_records: Max records to return (up to 100 per page).
        sort: List of sort specs e.g. [{"field": "Name", "direction": "asc"}]

    Returns: List of records — each has {id, fields, createdTime}.
    """
    params: dict[str, Any] = {"maxRecords": max_records}
    if view:
        params["view"] = view
    if filter_formula:
        params["filterByFormula"] = filter_formula
    if sort:
        for i, s in enumerate(sort):
            params[f"sort[{i}][field]"] = s["field"]
            params[f"sort[{i}][direction]"] = s.get("direction", "asc")

    encoded = urllib.parse.quote(table)
    resp = _get(encoded, params)
    return resp.get("records", [])


def get_record(table: str, record_id: str) -> dict[str, Any]:
    """Get a single record by ID."""
    encoded = urllib.parse.quote(table)
    return _get(f"{encoded}/{record_id}")


def create_record(table: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create a new record.

    Args:
        table: Table name.
        fields: Dict of field_name → value.

    Returns: Created record with {id, fields, createdTime}.
    """
    encoded = urllib.parse.quote(table)
    resp = _post(encoded, {"fields": fields})
    return resp


def create_records(table: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bulk create up to 10 records.

    Args:
        table: Table name.
        records: List of field dicts.
    """
    encoded = urllib.parse.quote(table)
    payload = {"records": [{"fields": r} for r in records[:10]]}
    resp = _post(encoded, payload)
    return resp.get("records", [])


def update_record(table: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Update fields on an existing record (PATCH — only named fields changed).

    Args:
        table: Table name.
        record_id: Record ID (starts with 'rec...').
        fields: Fields to update.
    """
    encoded = urllib.parse.quote(table)
    return _patch(f"{encoded}/{record_id}", {"fields": fields})


def upsert_records(table: str, records: list[dict], match_on: list[str]) -> dict[str, Any]:
    """Upsert (create or update) records matched on specific field names.

    Args:
        table: Table name.
        records: List of field dicts.
        match_on: List of field names to match existing records on.

    Returns: {createdRecords, updatedRecords} counts.
    """
    encoded = urllib.parse.quote(table)
    payload = {
        "performUpsert": {"fieldsToMergeOn": match_on},
        "records": [{"fields": r} for r in records[:10]],
    }
    return _patch(encoded, payload)


def delete_record(table: str, record_id: str) -> bool:
    """Delete a record by ID. Returns True on success."""
    encoded = urllib.parse.quote(table)
    result = _delete(f"{encoded}/{record_id}")
    return result.get("deleted", False)


def search_records(table: str, field: str, value: str) -> list[dict[str, Any]]:
    """Convenience wrapper: filter records where field = value.

    Args:
        table: Table name.
        field: Field name.
        value: Value to match (string comparison).
    """
    formula = f"{{{field}}}='{value}'"
    return list_records(table, filter_formula=formula)


# ---------------------------------------------------------------------------
# Schema / metadata
# ---------------------------------------------------------------------------

def list_tables() -> list[dict[str, Any]]:
    """List all tables in the base with their fields.

    Returns: List of {id, name, fields[]} dicts.
    """
    url = f"{META_URL}/bases/{_base_id()}/tables"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("tables", [])


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching table schema from the base."""
    try:
        tables = list_tables()
        return {
            "success": True,
            "base_id": _base_id(),
            "tables": [t["name"] for t in tables],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
