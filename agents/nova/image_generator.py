"""Nova image-generation helpers."""

from __future__ import annotations

from typing import Any

from integrations.openai_client import generate_image


def generate_listing_graphic(
    property_address: str,
    price: str,
    beds: str,
    baths: str,
    agent_name: str,
) -> dict[str, Any]:
    """Creates a listing promo image or returns a placeholder when unavailable."""
    prompt = (
        "Create a clean real-estate social media graphic. "
        f"Property: {property_address}. Price: {price}. Beds/Baths: {beds}/{baths}. "
        f"Agent: {agent_name}. Style: modern, bright, premium, readable text."
    )
    try:
        result = generate_image(prompt=prompt, size="1024x1024")
        return {
            "image_url": result.get("url"),
            "prompt_used": result.get("prompt_used", prompt),
            "cost_cents": 4,
            "provider": "dall-e-3",
        }
    except Exception:
        return {
            "image_url": "",
            "prompt_used": prompt,
            "cost_cents": 0,
            "provider": "fallback",
        }


def generate_market_update_graphic(area_name: str, stats_data: dict[str, Any]) -> dict[str, Any]:
    """Creates a market update visual concept for social posting."""
    prompt = (
        f"Create a modern market stats infographic for {area_name}. "
        f"Stats: {stats_data}. Use clean typography and clear hierarchy."
    )
    try:
        result = generate_image(prompt=prompt, size="1024x1024")
        return {
            "image_url": result.get("url"),
            "prompt_used": result.get("prompt_used", prompt),
            "cost_cents": 4,
            "provider": "dall-e-3",
        }
    except Exception:
        return {
            "image_url": "",
            "prompt_used": prompt,
            "cost_cents": 0,
            "provider": "fallback",
        }
