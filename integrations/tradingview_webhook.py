"""TradingView webhook integration helpers."""

from __future__ import annotations

import json
from typing import Any

from config.settings import get_settings


def validate_tradingview_secret(header_secret: str | None, payload_secret: str | None = None) -> bool:
    """Checks whether the TradingView secret from header or payload matches config."""
    settings = get_settings()
    expected = settings.tradingview_webhook_secret.strip()
    if not expected:
        return False
    candidate = (header_secret or payload_secret or "").strip()
    return bool(candidate) and candidate == expected


def parse_tradingview_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
    """Normalizes TradingView webhook payloads into a predictable dict."""
    raw_payload = json.loads(payload) if isinstance(payload, str) else dict(payload)
    return {
        "symbol": raw_payload.get("symbol") or raw_payload.get("ticker") or raw_payload.get("instrument"),
        "timeframe": raw_payload.get("timeframe") or raw_payload.get("interval"),
        "alert_message": raw_payload.get("alert_message") or raw_payload.get("message") or raw_payload.get("alert"),
        "price": raw_payload.get("price") or raw_payload.get("close") or raw_payload.get("last_price"),
        "volume": raw_payload.get("volume"),
        "direction": raw_payload.get("direction"),
        "agent_id": raw_payload.get("agent_id"),
        "owner_phone_number": raw_payload.get("owner_phone_number"),
        "raw": raw_payload,
    }
