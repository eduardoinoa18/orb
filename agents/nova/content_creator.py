"""Nova content creation workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agents.nova.image_generator import generate_listing_graphic
from agents.nova.listing_writer import generate_listing_headline, write_listing_description
from agents.nova.nova_brain import compose_caption, create_newsletter_blurb
from app.database.activity_log import log_activity
from app.database.connection import SupabaseService
from integrations.twilio_client import send_sms


class NovaContentCreator:
    """Creates and stores marketing content drafts for owner approval."""

    _supported_platforms = ("instagram", "facebook", "linkedin")

    def __init__(self) -> None:
        self.db = SupabaseService()

    def _notify_owner(self, owner_id: str, message: str) -> dict[str, Any] | None:
        """Sends owner SMS when phone is available; returns result or None."""
        owners = self.db.fetch_all("owners", {"id": owner_id})
        if not owners:
            return None
        phone = owners[0].get("phone")
        if not phone:
            return None
        try:
            return send_sms(to=str(phone), message=message)
        except Exception as error:
            return {"success": False, "error": str(error)}

    def _save_content(
        self,
        owner_id: str,
        content_type: str,
        platform: str,
        title: str,
        body: str,
        image_url: str = "",
        status: str = "draft",
        scheduled_for: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Stores one content draft row."""
        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "content_type": content_type,
            "platform": platform,
            "title": title,
            "body": body,
            "image_url": image_url,
            "status": status,
            "scheduled_for": scheduled_for,
            "performance_data": metadata or {},
        }
        return self.db.insert_one("content", payload)

    def _normalize_platforms(self, platforms: list[str] | None) -> list[str]:
        """Normalize requested platforms to supported values and remove duplicates."""
        if not platforms:
            return list(self._supported_platforms)

        normalized: list[str] = []
        for raw in platforms:
            value = str(raw).strip().lower()
            if value in self._supported_platforms and value not in normalized:
                normalized.append(value)

        return normalized or list(self._supported_platforms)

    def _listing_context(self, property_data: dict[str, Any]) -> dict[str, str]:
        """Extracts and normalizes listing fields used across prompt templates."""
        address = str(property_data.get("address") or "New Listing")
        city = str(property_data.get("city") or "your area")
        price = str(property_data.get("price") or "Price on request")
        beds = str(property_data.get("beds") or "?")
        baths = str(property_data.get("baths") or "?")
        sqft = str(property_data.get("sqft") or "?")
        cta = str(property_data.get("cta") or "Message us for a private tour.")
        return {
            "address": address,
            "city": city,
            "price": price,
            "beds": beds,
            "baths": baths,
            "sqft": sqft,
            "cta": cta,
        }

    def _platform_prompt(self, platform: str, listing_description: str, context: dict[str, str]) -> str:
        """Builds platform-specific copy prompt for better listing post quality."""
        if platform == "instagram":
            return (
                f"Write an Instagram listing post for {context['address']} in {context['city']} at {context['price']}. "
                f"Property details: {context['beds']} bed, {context['baths']} bath, {context['sqft']} sqft. "
                f"Use a warm, visual tone, max 120 words, include 4-6 relevant hashtags, and end with CTA: {context['cta']} "
                f"Context: {listing_description}"
            )
        if platform == "facebook":
            return (
                f"Write a Facebook listing post for {context['address']} in {context['city']} at {context['price']}. "
                f"Property details: {context['beds']} bed, {context['baths']} bath, {context['sqft']} sqft. "
                f"Use a neighborly tone, 120-180 words, include one clear CTA: {context['cta']}. "
                f"Context: {listing_description}"
            )
        return (
            f"Write a LinkedIn listing post for {context['address']} in {context['city']} at {context['price']}. "
            f"Property details: {context['beds']} bed, {context['baths']} bath, {context['sqft']} sqft. "
            f"Use a professional advisory tone, 120-180 words, include market positioning and CTA: {context['cta']}. "
            f"Context: {listing_description}"
        )

    def _fallback_listing_caption(self, platform: str, context: dict[str, str]) -> str:
        """Guarantees non-empty copy when upstream model output is missing."""
        if platform == "instagram":
            return (
                f"Just listed: {context['address']} in {context['city']} at {context['price']}. "
                f"{context['beds']} bed | {context['baths']} bath | {context['sqft']} sqft. "
                f"{context['cta']} #JustListed #RealEstate #HomeSearch"
            )
        if platform == "facebook":
            return (
                f"New listing available at {context['address']} in {context['city']}. "
                f"Priced at {context['price']} with {context['beds']} bedrooms and {context['baths']} bathrooms. "
                f"{context['cta']}"
            )
        return (
            f"New listing update: {context['address']} ({context['city']}) is now available at {context['price']}. "
            f"Property profile: {context['beds']} bed, {context['baths']} bath, {context['sqft']} sqft. "
            f"{context['cta']}"
        )

    def create_listing_post(
        self,
        property_data: dict[str, Any],
        owner_id: str,
        platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        """Creates platform-specific listing posts and saves them as drafts."""
        target_platforms = self._normalize_platforms(platforms)
        context = self._listing_context(property_data)
        address = context["address"]
        price = context["price"]

        listing_description = write_listing_description(property_data)
        headlines = generate_listing_headline(property_data)
        image_info = generate_listing_graphic(
            property_address=address,
            price=price,
            beds=context["beds"],
            baths=context["baths"],
            agent_name="Nova",
        )

        rows: list[dict[str, Any]] = []
        for platform in target_platforms:
            prompt = self._platform_prompt(platform=platform, listing_description=listing_description, context=context)
            caption = compose_caption(prompt=prompt, platform=platform, long_form=(platform != "instagram"))
            text = str(caption.get("text") or "").strip() or self._fallback_listing_caption(platform, context)
            row = self._save_content(
                owner_id=owner_id,
                content_type="listing_post",
                platform=platform,
                title=headlines[0],
                body=text,
                image_url=image_info.get("image_url", ""),
                metadata={
                    "headlines": headlines,
                    "model": caption.get("model"),
                    "cost_cents": int(caption.get("cost_cents", 0)) + int(image_info.get("cost_cents", 0)),
                    "property_data": property_data,
                },
            )
            rows.append(row)

        log_activity(
            agent_id=None,
            action_type="content_create",
            description=f"Nova created {len(rows)} listing drafts for {address}",
            outcome="success",
            cost_cents=sum(int((r.get("performance_data") or {}).get("cost_cents", 0)) for r in rows),
        )
        self._notify_owner(owner_id, f"Nova created listing drafts for {address}. Review in dashboard.")

        return {
            "created": len(rows),
            "content": rows,
            "headlines": headlines,
            "image": image_info,
        }

    def create_market_update(self, owner_id: str, market_area: str, month: str) -> dict[str, Any]:
        """Creates a market update post and email draft."""
        prompt = f"Monthly market update for {market_area} in {month}. Include one practical takeaway for sellers."
        social_copy = compose_caption(prompt=prompt, platform="linkedin", long_form=True)
        newsletter = create_newsletter_blurb(prompt)

        rows = [
            self._save_content(
                owner_id=owner_id,
                content_type="market_update",
                platform="linkedin",
                title=f"{market_area} Market Update - {month}",
                body=social_copy["text"],
                metadata={"model": social_copy.get("model"), "cost_cents": social_copy.get("cost_cents", 0)},
            ),
            self._save_content(
                owner_id=owner_id,
                content_type="market_update",
                platform="email",
                title=f"{market_area} Market Update Newsletter - {month}",
                body=newsletter["text"],
                metadata={"model": newsletter.get("model"), "cost_cents": newsletter.get("cost_cents", 0)},
            ),
        ]

        self._notify_owner(owner_id, f"Nova created market update drafts for {market_area}. Review in dashboard.")
        return {"created": len(rows), "content": rows}

    def create_just_sold_post(
        self,
        property_data: dict[str, Any],
        sale_price: str,
        days_on_market: int,
        owner_id: str,
    ) -> dict[str, Any]:
        """Creates celebratory just-sold content across core social channels."""
        address = str(property_data.get("address", "Property"))
        prompt = (
            f"Create a just sold celebration post for {address}. "
            f"Sale price: {sale_price}. Days on market: {days_on_market}. "
            "Highlight trust and results, include one CTA."
        )

        rows: list[dict[str, Any]] = []
        for platform in ["instagram", "facebook", "linkedin"]:
            caption = compose_caption(prompt=prompt, platform=platform, long_form=(platform != "instagram"))
            row = self._save_content(
                owner_id=owner_id,
                content_type="just_sold",
                platform=platform,
                title=f"Just Sold - {address}",
                body=caption["text"],
                metadata={"model": caption.get("model"), "cost_cents": caption.get("cost_cents", 0)},
            )
            rows.append(row)

        self._notify_owner(owner_id, f"Nova created just sold drafts for {address}. Review in dashboard.")
        return {"created": len(rows), "content": rows}

    def generate_weekly_content_calendar(self, owner_id: str, week_start: str) -> dict[str, Any]:
        """Creates 7 days of draft content using a practical posting cadence."""
        topics = [
            ("market_update", "linkedin", "Monday market insight"),
            ("listing_post", "instagram", "Tuesday property showcase"),
            ("educational", "facebook", "Wednesday educational tip"),
            ("community", "facebook", "Thursday local community highlight"),
            ("just_sold", "instagram", "Friday results post"),
            ("home_tip", "linkedin", "Saturday homeowner tip"),
            ("personal_brand", "linkedin", "Sunday motivational post"),
        ]

        try:
            start_date = datetime.fromisoformat(week_start).date()
        except ValueError:
            start_date = datetime.now(timezone.utc).date()

        created: list[dict[str, Any]] = []
        for offset, (content_type, platform, directive) in enumerate(topics):
            run_date = start_date + timedelta(days=offset)
            prompt = f"Create {directive} for real estate audience. Keep it practical and engaging."
            copy = compose_caption(prompt=prompt, platform=platform, long_form=(platform != "instagram"))
            row = self._save_content(
                owner_id=owner_id,
                content_type=content_type,
                platform=platform,
                title=f"{run_date.isoformat()} - {directive.title()}",
                body=copy["text"],
                scheduled_for=f"{run_date.isoformat()}T14:00:00+00:00",
                metadata={"model": copy.get("model"), "cost_cents": copy.get("cost_cents", 0)},
            )
            created.append(row)

        log_activity(
            agent_id=None,
            action_type="content_calendar",
            description=f"Nova generated weekly content calendar with {len(created)} items",
            outcome="success",
            cost_cents=sum(int((row.get("performance_data") or {}).get("cost_cents", 0)) for row in created),
        )
        self._notify_owner(owner_id, "Nova created your weekly content calendar drafts. Approve in dashboard.")

        return {"created": len(created), "content": created}
