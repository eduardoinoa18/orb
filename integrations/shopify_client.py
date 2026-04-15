"""Shopify Admin API client for ORB Platform.

Agents can use Shopify to:
  - Monitor orders (new, paid, shipped, cancelled)
  - Look up customers and their order history
  - Update product inventory
  - Create discount codes
  - Get store revenue analytics
  - Send order fulfillment updates

Requires:
  SHOPIFY_STORE_DOMAIN  — Your store domain e.g. 'my-store.myshopify.com'
  SHOPIFY_ACCESS_TOKEN  — Admin API access token (from Shopify Custom App)

Docs: https://shopify.dev/docs/api/admin-rest
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.shopify")

API_VERSION = "2024-01"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_shopify_available() -> bool:
    s = get_settings()
    return bool(
        s.resolve("shopify_store_domain", default="")
        and s.resolve("shopify_access_token", default="")
    )


def _domain() -> str:
    return get_settings().resolve("shopify_store_domain", default="")


def _token() -> str:
    return get_settings().resolve("shopify_access_token", default="")


def _base_url() -> str:
    return f"https://{_domain()}/admin/api/{API_VERSION}"


def _headers() -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": _token(),
        "Content-Type": "application/json",
    }


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


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def list_orders(
    status: str = "any",
    limit: int = 20,
    financial_status: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent orders.

    Args:
        status: 'open' | 'closed' | 'cancelled' | 'any'
        limit: Max orders to return (max 250).
        financial_status: 'paid' | 'pending' | 'refunded' | 'partially_refunded'

    Returns: List of {id, order_number, total_price, status, customer_name, created_at}.
    """
    params: dict[str, Any] = {"status": status, "limit": min(limit, 250)}
    if financial_status:
        params["financial_status"] = financial_status

    resp = _get("orders.json", params)
    return [
        {
            "id": o.get("id"),
            "order_number": o.get("order_number"),
            "total_price": o.get("total_price"),
            "financial_status": o.get("financial_status"),
            "fulfillment_status": o.get("fulfillment_status"),
            "customer_name": f"{o.get('customer', {}).get('first_name', '')} {o.get('customer', {}).get('last_name', '')}".strip() if o.get("customer") else "Guest",
            "email": o.get("email", ""),
            "created_at": o.get("created_at", ""),
            "items": len(o.get("line_items", [])),
        }
        for o in resp.get("orders", [])
    ]


def get_order(order_id: int) -> dict[str, Any]:
    """Get a single order with full detail."""
    resp = _get(f"orders/{order_id}.json")
    return resp.get("order", resp)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def search_customers(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search customers by name, email, or phone."""
    resp = _get("customers/search.json", {"query": query, "limit": limit})
    return [
        {
            "id": c.get("id"),
            "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "email": c.get("email", ""),
            "phone": c.get("phone", ""),
            "orders_count": c.get("orders_count", 0),
            "total_spent": c.get("total_spent", "0.00"),
        }
        for c in resp.get("customers", [])
    ]


def get_customer_orders(customer_id: int) -> list[dict[str, Any]]:
    """Get order history for a specific customer."""
    resp = _get("orders.json", {"customer_id": customer_id, "status": "any", "limit": 50})
    return resp.get("orders", [])


# ---------------------------------------------------------------------------
# Products & inventory
# ---------------------------------------------------------------------------

def list_products(limit: int = 20) -> list[dict[str, Any]]:
    """List products in the store."""
    resp = _get("products.json", {"limit": min(limit, 250)})
    return [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "status": p.get("status"),
            "variants_count": len(p.get("variants", [])),
            "inventory": sum(v.get("inventory_quantity", 0) for v in p.get("variants", [])),
        }
        for p in resp.get("products", [])
    ]


def update_inventory(inventory_item_id: int, quantity: int, location_id: int | None = None) -> bool:
    """Update inventory level for a variant.

    Args:
        inventory_item_id: Get from product variants.
        quantity: New quantity.
        location_id: Shopify location ID (fetched from /locations.json if needed).
    """
    try:
        # Get location if not provided
        if not location_id:
            locations = _get("locations.json")
            locs = locations.get("locations", [])
            if locs:
                location_id = locs[0]["id"]
            else:
                return False

        _post("inventory_levels/set.json", {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": quantity,
        })
        return True
    except Exception as e:
        logger.warning("Failed to update inventory: %s", e)
        return False


# ---------------------------------------------------------------------------
# Discount codes
# ---------------------------------------------------------------------------

def create_discount_code(
    code: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    minimum_order_amount: float = 0,
    usage_limit: int | None = None,
) -> dict[str, Any]:
    """Create a discount code.

    Args:
        code: The discount code string (e.g. 'WELCOME10').
        discount_type: 'percentage' | 'fixed_amount' | 'free_shipping'
        value: Discount value (% or $ amount).
        minimum_order_amount: Minimum order subtotal required.
        usage_limit: Max uses (None = unlimited).
    """
    price_rule_body: dict[str, Any] = {
        "price_rule": {
            "title": code,
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "value_type": "percentage" if discount_type == "percentage" else "fixed_amount",
            "value": f"-{value}",
            "customer_selection": "all",
            "starts_at": "2024-01-01T00:00:00Z",
        }
    }
    if minimum_order_amount > 0:
        price_rule_body["price_rule"]["prerequisite_subtotal_range"] = {
            "greater_than_or_equal_to": str(minimum_order_amount)
        }
    if usage_limit:
        price_rule_body["price_rule"]["usage_limit"] = usage_limit

    rule = _post("price_rules.json", price_rule_body)
    rule_id = rule.get("price_rule", {}).get("id")
    if not rule_id:
        return rule

    # Create the actual discount code
    code_resp = _post(f"price_rules/{rule_id}/discount_codes.json", {
        "discount_code": {"code": code}
    })
    return {
        "code": code,
        "price_rule_id": rule_id,
        "discount_code_id": code_resp.get("discount_code", {}).get("id"),
        "type": discount_type,
        "value": value,
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_store_summary() -> dict[str, Any]:
    """Get a quick store health summary."""
    try:
        # Get total orders count and revenue
        resp = _get("orders/count.json", {"status": "any"})
        total_orders = resp.get("count", 0)

        recent_orders = list_orders(limit=50, status="any", financial_status="paid")
        total_revenue = sum(float(o.get("total_price", 0)) for o in recent_orders)

        products = _get("products/count.json")
        customers = _get("customers/count.json")

        return {
            "total_orders": total_orders,
            "recent_paid_orders": len(recent_orders),
            "recent_revenue_usd": round(total_revenue, 2),
            "total_products": products.get("count", 0),
            "total_customers": customers.get("count", 0),
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching shop info."""
    try:
        resp = _get("shop.json")
        shop = resp.get("shop", {})
        return {
            "success": True,
            "shop_name": shop.get("name"),
            "domain": shop.get("domain"),
            "currency": shop.get("currency"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
