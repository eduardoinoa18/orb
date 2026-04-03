"""Low-cost market data helpers for Orion.

Uses free public endpoints first and falls back to deterministic mock data
for local development and tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

YAHOO_SYMBOL_MAP = {
    "ES": "ES=F",
    "NQ": "NQ=F",
    "YM": "YM=F",
    "RTY": "RTY=F",
}


def _normalize_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    return YAHOO_SYMBOL_MAP.get(clean, clean)


def _fallback_quote(symbol: str) -> dict[str, Any]:
    base = 100 + (sum(ord(ch) for ch in symbol) % 50)
    move_seed = ((sum(ord(ch) * (i + 1) for i, ch in enumerate(symbol)) % 17) - 8) / 10
    last = round(base + move_seed, 2)
    prev_close = round(base, 2)
    momentum_pct = round(((last - prev_close) / prev_close) * 100, 2)
    return {
        "symbol": symbol,
        "last_price": last,
        "previous_close": prev_close,
        "high": round(last * 1.003, 2),
        "low": round(last * 0.997, 2),
        "volume": 100000,
        "momentum_pct": momentum_pct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "fallback",
    }


def _fetch_yahoo_chart(symbol: str) -> dict[str, Any]:
    normalized = _normalize_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{normalized}"
    params = {"interval": "1m", "range": "1d"}

    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError("No market data returned.")

    node = result[0]
    meta = node.get("meta") or {}
    quote = ((node.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    last_price = meta.get("regularMarketPrice")
    if last_price is None:
        closes_clean = [value for value in closes if value is not None]
        last_price = closes_clean[-1] if closes_clean else None
    if last_price is None:
        raise ValueError("Missing last price in market response.")

    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose") or last_price
    high = meta.get("regularMarketDayHigh") or last_price
    low = meta.get("regularMarketDayLow") or last_price

    if previous_close:
        momentum_pct = round(((float(last_price) - float(previous_close)) / float(previous_close)) * 100, 2)
    else:
        momentum_pct = 0.0

    volumes_clean = [int(v) for v in volumes if v is not None]
    volume = volumes_clean[-1] if volumes_clean else int(meta.get("regularMarketVolume") or 0)

    return {
        "symbol": symbol.upper(),
        "last_price": round(float(last_price), 4),
        "previous_close": round(float(previous_close), 4),
        "high": round(float(high), 4),
        "low": round(float(low), 4),
        "volume": volume,
        "momentum_pct": momentum_pct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "yahoo",
    }


def get_market_snapshot(symbols: list[str]) -> dict[str, Any]:
    """Returns quote snapshots for a list of symbols with robust fallbacks."""
    quotes: list[dict[str, Any]] = []

    for symbol in symbols:
        if not symbol or not symbol.strip():
            continue
        clean_symbol = symbol.strip().upper()
        try:
            quotes.append(_fetch_yahoo_chart(clean_symbol))
        except Exception:
            quotes.append(_fallback_quote(clean_symbol))

    return {
        "quotes": quotes,
        "count": len(quotes),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
