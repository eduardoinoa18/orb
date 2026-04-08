"""Stripe billing routes for checkout, portal access, and subscription status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutPayload(BaseModel):
    """Payload for creating a Stripe Checkout session."""

    plan: str = Field(pattern="^(starter|professional|full_team)$")
    billing: str = Field(pattern="^(monthly|annual)$")
    owner_id: str = Field(min_length=2)
    trial_days: int = Field(default=14, ge=0, le=30)


class PortalPayload(BaseModel):
    """Payload for creating a Stripe customer portal session."""

    owner_id: str = Field(min_length=2)


class AddonCheckoutPayload(BaseModel):
    """Payload for adding an individual agent as a Stripe subscription add-on."""

    owner_id: str = Field(min_length=2)
    agent: str = Field(pattern="^(rex|aria|nova|orion|sage|atlas|commander)$")


def _get_db() -> SupabaseService:
    return SupabaseService()


def _get_owner(owner_id: str) -> dict[str, Any]:
    try:
        rows = _get_db().fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not rows:
        raise HTTPException(status_code=404, detail="Owner not found.")
    return rows[0]


def _stripe_client_ready() -> stripe:
    settings = get_settings()
    if not settings.stripe_secret_key.strip():
        raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY is not configured yet.")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _build_price_map() -> dict[tuple[str, str], str]:
    settings = get_settings()
    return {
        ("starter", "monthly"): settings.stripe_price_starter_monthly,
        ("starter", "annual"): settings.stripe_price_starter_annual,
        ("professional", "monthly"): settings.stripe_price_pro_monthly,
        ("professional", "annual"): settings.stripe_price_pro_annual,
        ("full_team", "monthly"): settings.stripe_price_full_team_monthly,
        ("full_team", "annual"): settings.stripe_price_full_team_annual,
    }


def _addon_price_map() -> dict[str, str]:
    settings = get_settings()
    return {
        "rex": settings.stripe_price_rex_monthly,
        "aria": settings.stripe_price_aria_monthly,
        "nova": settings.stripe_price_nova_monthly,
        "orion": settings.stripe_price_orion_monthly,
        "sage": settings.stripe_price_sage_monthly,
        "atlas": settings.stripe_price_atlas_monthly,
        "commander": settings.stripe_price_commander_monthly,
    }


def _plan_catalog() -> dict[str, Any]:
    return {
        "starter": {
            "monthly": 49,
            "annual": 39,
            "included_agents": 1,
            "includes_commander": True,
            "features": ["1 agent identity", "Commander AI included", "50,000 AI tokens/month", "SMS + email included"],
        },
        "professional": {
            "monthly": 149,
            "annual": 119,
            "included_agents": 3,
            "includes_commander": True,
            "features": ["3 agent identities", "Commander AI + full team chat", "200,000 AI tokens/month", "Voice calls included"],
        },
        "full_team": {
            "monthly": 299,
            "annual": 239,
            "included_agents": 7,
            "includes_commander": True,
            "features": ["All agents", "Cross-agent workflows", "Unlimited AI tokens", "Computer use enabled"],
        },
    }


def _required_plan_for_agent(agent: str) -> str:
    return {
        "rex": "professional",
        "aria": "professional",
        "nova": "full_team",
        "orion": "full_team",
        "sage": "full_team",
        "atlas": "full_team",
        "commander": "starter",
    }[agent]


def _app_base_url() -> str:
    settings = get_settings()
    domain = (settings.next_public_api_url or f"https://{settings.platform_domain}").strip()
    return domain.rstrip("/")


def _serialize_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return str(value)


@router.post("/create-checkout")
def create_checkout(payload: CheckoutPayload) -> dict[str, Any]:
    """Creates a Stripe Checkout session for subscription signup."""
    owner = _get_owner(payload.owner_id)
    price_map = _build_price_map()
    price_id = price_map.get((payload.plan, payload.billing), "").strip()
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Stripe price ID missing for {payload.plan}/{payload.billing}.")

    stripe_client = _stripe_client_ready()
    success_url = f"{_app_base_url()}/dashboard?activated=true"
    cancel_url = f"{_app_base_url()}/pricing"

    session = stripe_client.checkout.Session.create(
        customer_email=owner.get("email"),
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        allow_promotion_codes=True,
        subscription_data={"trial_period_days": payload.trial_days},
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"owner_id": payload.owner_id, "plan": payload.plan, "billing": payload.billing},
    )

    return {
        "checkout_url": session.get("url"),
        "session_id": session.get("id"),
        "plan": payload.plan,
        "billing": payload.billing,
        "trial_days": payload.trial_days,
    }


@router.post("/create-portal-session")
def create_portal_session(payload: PortalPayload) -> dict[str, Any]:
    """Creates a Stripe customer portal session so owner can self-manage billing."""
    owner = _get_owner(payload.owner_id)
    customer_id = str(owner.get("stripe_customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=404, detail="Owner does not have a Stripe customer yet.")

    stripe_client = _stripe_client_ready()
    session = stripe_client.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{_app_base_url()}/dashboard/settings/billing",
    )

    return {"portal_url": session.get("url"), "customer_id": customer_id}


@router.get("/plans")
def billing_plans() -> dict[str, Any]:
    """Returns pricing catalog for dashboard and marketing integrations."""
    return {"plans": _plan_catalog(), "addons": _addon_price_map()}


@router.get("/upgrade-preview/{owner_id}")
def billing_upgrade_preview(owner_id: str, agent: str) -> dict[str, Any]:
    """Explains which plan includes a requested agent and the add-on alternative."""
    normalized_agent = agent.strip().lower()
    addon_prices = _addon_price_map()
    if normalized_agent not in addon_prices:
        raise HTTPException(status_code=404, detail="Unknown agent add-on.")

    owner = _get_owner(owner_id)
    current_plan = str(owner.get("plan") or owner.get("subscription_plan") or "free").lower()
    required_plan = _required_plan_for_agent(normalized_agent)
    plans = _plan_catalog()
    prompt = (
        f"{normalized_agent.capitalize()} is included in the {required_plan.replace('_', ' ')} plan. "
        f"You are currently on {current_plan}."
    )
    return {
        "owner_id": owner_id,
        "agent": normalized_agent,
        "current_plan": current_plan,
        "required_plan": required_plan,
        "upgrade_prompt": prompt,
        "upgrade_monthly_price": plans[required_plan]["monthly"],
        "addon_monthly_price_id": addon_prices[normalized_agent],
    }


@router.post("/create-addon-checkout")
def create_addon_checkout(payload: AddonCheckoutPayload) -> dict[str, Any]:
    """Creates a Stripe checkout session for an individual paid add-on agent."""
    owner = _get_owner(payload.owner_id)
    customer_id = str(owner.get("stripe_customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=404, detail="Owner does not have a Stripe customer yet.")

    addon_prices = _addon_price_map()
    price_id = addon_prices.get(payload.agent, "").strip()
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Stripe add-on price missing for {payload.agent}.")

    stripe_client = _stripe_client_ready()
    session = stripe_client.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        allow_promotion_codes=True,
        success_url=f"{_app_base_url()}/dashboard/settings/billing?addon=activated",
        cancel_url=f"{_app_base_url()}/pricing",
        metadata={"owner_id": payload.owner_id, "addon_agent": payload.agent},
    )
    return {"checkout_url": session.get("url"), "session_id": session.get("id"), "agent": payload.agent}


@router.get("/subscription/{owner_id}")
def get_subscription(owner_id: str) -> dict[str, Any]:
    """Returns current billing/subscription status for an owner."""
    owner = _get_owner(owner_id)
    return {
        "owner_id": owner_id,
        "plan": owner.get("plan") or owner.get("subscription_plan") or "free",
        "status": owner.get("subscription_status") or "inactive",
        "next_billing_date": _serialize_timestamp(owner.get("subscription_current_period_end")),
        "trial_ends_at": _serialize_timestamp(owner.get("trial_ends_at")),
        "amount": owner.get("subscription_amount_cents") or 0,
        "card_last_4": owner.get("stripe_card_last4") or None,
        "stripe_customer_id": owner.get("stripe_customer_id") or None,
        "stripe_subscription_id": owner.get("stripe_subscription_id") or None,
    }
