"""Unit tests for Nova listing post creation logic."""

from unittest.mock import patch

from agents.nova.content_creator import NovaContentCreator


def _sample_property() -> dict:
    return {
        "address": "123 Main St",
        "city": "Tampa",
        "price": "$450,000",
        "beds": 3,
        "baths": 2,
        "sqft": 1850,
        "key_features": ["Pool", "Updated kitchen", "Large backyard"],
    }


def test_listing_post_defaults_to_three_platforms() -> None:
    """When platforms is None, creator should generate 3 listing drafts."""
    creator = NovaContentCreator()

    with patch("agents.nova.content_creator.write_listing_description", return_value="Great property"):
        with patch("agents.nova.content_creator.generate_listing_headline", return_value=["Just Listed"]):
            with patch("agents.nova.content_creator.generate_listing_graphic", return_value={"image_url": "x", "cost_cents": 4}):
                with patch("agents.nova.content_creator.compose_caption", return_value={"text": "caption", "model": "haiku", "cost_cents": 2}):
                    with patch.object(creator, "_save_content", return_value={"id": "c1", "performance_data": {"cost_cents": 6}}) as mock_save:
                        with patch("agents.nova.content_creator.log_activity"):
                            with patch.object(creator, "_notify_owner"):
                                result = creator.create_listing_post(_sample_property(), owner_id="owner-1")

    assert result["created"] == 3
    assert mock_save.call_count == 3


def test_listing_post_normalizes_platforms_and_dedupes() -> None:
    """Unsupported platforms are dropped and duplicates are removed."""
    creator = NovaContentCreator()

    with patch("agents.nova.content_creator.write_listing_description", return_value="Great property"):
        with patch("agents.nova.content_creator.generate_listing_headline", return_value=["Just Listed"]):
            with patch("agents.nova.content_creator.generate_listing_graphic", return_value={"image_url": "x", "cost_cents": 4}):
                with patch("agents.nova.content_creator.compose_caption", return_value={"text": "caption", "model": "haiku", "cost_cents": 2}):
                    with patch.object(creator, "_save_content", return_value={"id": "c1", "performance_data": {"cost_cents": 6}}) as mock_save:
                        with patch("agents.nova.content_creator.log_activity"):
                            with patch.object(creator, "_notify_owner"):
                                creator.create_listing_post(
                                    _sample_property(),
                                    owner_id="owner-1",
                                    platforms=["Instagram", "instagram", "x", "linkedin"],
                                )

    assert mock_save.call_count == 2


def test_listing_post_uses_fallback_when_caption_empty() -> None:
    """If AI returns blank text, creator should use deterministic fallback copy."""
    creator = NovaContentCreator()

    captured_bodies: list[str] = []

    def _capture_save(**kwargs):
        captured_bodies.append(kwargs["body"])
        return {"id": "c1", "performance_data": {"cost_cents": 4}}

    with patch("agents.nova.content_creator.write_listing_description", return_value="Great property"):
        with patch("agents.nova.content_creator.generate_listing_headline", return_value=["Just Listed"]):
            with patch("agents.nova.content_creator.generate_listing_graphic", return_value={"image_url": "x", "cost_cents": 4}):
                with patch("agents.nova.content_creator.compose_caption", return_value={"text": "", "model": "haiku", "cost_cents": 2}):
                    with patch.object(creator, "_save_content", side_effect=_capture_save):
                        with patch("agents.nova.content_creator.log_activity"):
                            with patch.object(creator, "_notify_owner"):
                                creator.create_listing_post(
                                    _sample_property(),
                                    owner_id="owner-1",
                                    platforms=["instagram"],
                                )

    assert len(captured_bodies) == 1
    assert "Just listed" in captured_bodies[0]
    assert "#JustListed" in captured_bodies[0]


def test_listing_post_handles_minimal_property_data() -> None:
    """Missing optional property fields should not crash listing generation."""
    creator = NovaContentCreator()

    minimal_property = {"address": "Unknown", "price": "$0"}

    with patch("agents.nova.content_creator.write_listing_description", return_value="Property"):
        with patch("agents.nova.content_creator.generate_listing_headline", return_value=["Headline"]):
            with patch("agents.nova.content_creator.generate_listing_graphic", return_value={"image_url": "", "cost_cents": 0}):
                with patch("agents.nova.content_creator.compose_caption", return_value={"text": "caption", "model": "haiku", "cost_cents": 1}):
                    with patch.object(creator, "_save_content", return_value={"id": "c1", "performance_data": {"cost_cents": 1}}):
                        with patch("agents.nova.content_creator.log_activity"):
                            with patch.object(creator, "_notify_owner"):
                                result = creator.create_listing_post(minimal_property, owner_id="owner-1", platforms=["facebook"])

    assert result["created"] == 1
