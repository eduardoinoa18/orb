"""Nova listing copy helpers."""

from __future__ import annotations

from typing import Any

from agents.nova.nova_brain import compose_caption


def write_listing_description(property_data: dict[str, Any], style: str = "professional") -> str:
    """Builds an MLS-friendly listing description from property data."""
    address = property_data.get("address", "this property")
    beds = property_data.get("beds", "?")
    baths = property_data.get("baths", "?")
    sqft = property_data.get("sqft", "?")
    features = property_data.get("key_features", []) or []
    features_line = ", ".join(str(item) for item in features[:5])

    prompt = (
        f"Write a {style} real-estate listing description for {address}. "
        f"Specs: {beds} beds, {baths} baths, {sqft} sqft. "
        f"Highlight features: {features_line}. Keep under 500 words."
    )
    result = compose_caption(prompt=prompt, platform="linkedin", long_form=True)
    return result["text"]


def generate_listing_headline(property_data: dict[str, Any]) -> list[str]:
    """Returns a small set of listing headline options."""
    address = str(property_data.get("address", "Prime Property"))
    city = str(property_data.get("city", "Great Location"))
    return [
        f"New Opportunity in {city}: {address}",
        f"Just Listed - {address}",
        f"Move-In Ready at {address}",
        f"Investor-Friendly Value: {address}",
        f"Tour This {city} Home at {address}",
    ]
