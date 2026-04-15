"""Monday.com API client for ORB Platform.

Agents can use Monday.com to:
  - Create items (tasks/leads/projects) on boards
  - Update item status, assign owners, set due dates
  - Search boards and items
  - Log updates and comments
  - Move items between groups (stages)

Uses Monday's GraphQL API v2.

Requires:
  MONDAY_API_KEY    — API token from Monday.com Profile → API

Docs: https://developer.monday.com/api-reference/docs
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.monday")

MONDAY_URL = "https://api.monday.com/v2"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_monday_available() -> bool:
    return bool(get_settings().resolve("monday_api_key", default=""))


def _api_key() -> str:
    return get_settings().resolve("monday_api_key", default="")


def _headers() -> dict[str, str]:
    return {
        "Authorization": _api_key(),
        "Content-Type": "application/json",
        "API-Version": "2023-10",
    }


# ---------------------------------------------------------------------------
# GraphQL executor
# ---------------------------------------------------------------------------

def _gql(query: str, variables: dict | None = None) -> dict[str, Any]:
    """Execute a GraphQL query/mutation against the Monday API."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode()
    req = urllib.request.Request(MONDAY_URL, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    if "errors" in result:
        raise RuntimeError(f"Monday GraphQL error: {result['errors']}")
    return result.get("data", result)


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

def list_boards(limit: int = 20) -> list[dict[str, Any]]:
    """List all accessible boards.

    Returns: List of {id, name, state, items_count}.
    """
    q = """
    query ($limit: Int) {
      boards(limit: $limit, order_by: created_at) {
        id name state items_count
      }
    }
    """
    data = _gql(q, {"limit": limit})
    return data.get("boards", [])


def get_board_groups(board_id: str) -> list[dict[str, Any]]:
    """Get groups (columns/stages) in a board."""
    q = """
    query ($board_id: [ID!]) {
      boards(ids: $board_id) {
        groups { id title color }
      }
    }
    """
    data = _gql(q, {"board_id": [board_id]})
    boards = data.get("boards", [])
    return boards[0].get("groups", []) if boards else []


# ---------------------------------------------------------------------------
# Items (tasks/leads)
# ---------------------------------------------------------------------------

def list_items(board_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """List items from a board.

    Returns: List of {id, name, state, group_id, column_values}.
    """
    q = """
    query ($board_id: [ID!], $limit: Int) {
      boards(ids: $board_id) {
        items_page(limit: $limit) {
          items {
            id name state group { id title }
            column_values { id text value }
          }
        }
      }
    }
    """
    data = _gql(q, {"board_id": [board_id], "limit": limit})
    boards = data.get("boards", [])
    if not boards:
        return []
    return boards[0].get("items_page", {}).get("items", [])


def create_item(
    board_id: str,
    item_name: str,
    group_id: str | None = None,
    column_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new item on a board.

    Args:
        board_id: Target board ID.
        item_name: Item title.
        group_id: Group to place item in (optional, defaults to first group).
        column_values: Dict of column_id → value, e.g. {"status": {"label": "Done"}, "date4": "2026-05-01"}

    Returns: Created item {id, name}.
    """
    col_vals_json = json.dumps(column_values or {})

    if group_id:
        q = """
        mutation ($board_id: ID!, $item_name: String!, $group_id: String!, $column_values: JSON) {
          create_item(board_id: $board_id, item_name: $item_name,
                      group_id: $group_id, column_values: $column_values) {
            id name
          }
        }
        """
        data = _gql(q, {
            "board_id": board_id,
            "item_name": item_name,
            "group_id": group_id,
            "column_values": col_vals_json,
        })
    else:
        q = """
        mutation ($board_id: ID!, $item_name: String!, $column_values: JSON) {
          create_item(board_id: $board_id, item_name: $item_name, column_values: $column_values) {
            id name
          }
        }
        """
        data = _gql(q, {
            "board_id": board_id,
            "item_name": item_name,
            "column_values": col_vals_json,
        })

    return data.get("create_item", {})


def update_item(item_id: str, board_id: str, column_id: str, value: str) -> dict[str, Any]:
    """Update a single column value on an item.

    Args:
        item_id: Item ID.
        board_id: Board ID.
        column_id: Column ID to update.
        value: New value as JSON string.
    """
    q = """
    mutation ($board_id: ID!, $item_id: ID!, $column_id: String!, $value: JSON!) {
      change_column_value(board_id: $board_id, item_id: $item_id,
                          column_id: $column_id, value: $value) {
        id
      }
    }
    """
    data = _gql(q, {
        "board_id": board_id,
        "item_id": item_id,
        "column_id": column_id,
        "value": value,
    })
    return data.get("change_column_value", {})


def move_item_to_group(item_id: str, group_id: str) -> dict[str, Any]:
    """Move an item to a different group (stage)."""
    q = """
    mutation ($item_id: ID!, $group_id: String!) {
      move_item_to_group(item_id: $item_id, group_id: $group_id) {
        id name
      }
    }
    """
    data = _gql(q, {"item_id": item_id, "group_id": group_id})
    return data.get("move_item_to_group", {})


def search_items(board_id: str, query: str) -> list[dict[str, Any]]:
    """Search items on a board by name."""
    q = """
    query ($board_id: [ID!], $query: String) {
      boards(ids: $board_id) {
        items_page(query_params: {rules: [{column_id: "name", compare_value: [$query]}]}) {
          items { id name group { id title } }
        }
      }
    }
    """
    try:
        data = _gql(q, {"board_id": [board_id], "query": query})
        boards = data.get("boards", [])
        return boards[0].get("items_page", {}).get("items", []) if boards else []
    except Exception:
        # Fallback: fetch all and filter
        all_items = list_items(board_id, limit=100)
        return [i for i in all_items if query.lower() in i.get("name", "").lower()]


# ---------------------------------------------------------------------------
# Updates (comments)
# ---------------------------------------------------------------------------

def post_update(item_id: str, body: str) -> dict[str, Any]:
    """Post an update (comment) on an item."""
    q = """
    mutation ($item_id: ID!, $body: String!) {
      create_update(item_id: $item_id, body: $body) {
        id body
      }
    }
    """
    data = _gql(q, {"item_id": item_id, "body": body})
    return data.get("create_update", {})


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the authenticated user."""
    try:
        q = "query { me { id name email account { name } } }"
        data = _gql(q)
        user = data.get("me", {})
        return {
            "success": True,
            "name": user.get("name"),
            "email": user.get("email"),
            "account": user.get("account", {}).get("name"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
