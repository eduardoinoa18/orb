"""Stripe billing routes for checkout, portal access, and subscription status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class BillingControlsPayload(BaseModel):
    """Payload for owner-level token governance and PAYG behavior."""

    hourly_token_cap: int = Field(ge=0, le=500000)
    daily_token_cap: int = Field(ge=0, le=5000000)
    weekly_token_cap: int = Field(ge=0, le=20000000)
    monthly_token_cap: int = Field(ge=0, le=100000000)
    payg_enabled: bool = True
    auto_refill_enabled: bool = False
    auto_refill_threshold_tokens: int = Field(default=0, ge=0, le=50000000)
    auto_refill_amount_usd: int = Field(default=0, ge=0, le=10000)


class TokenUsageRecordPayload(BaseModel):
    """Model-level usage record for token accounting."""

    owner_id: str = Field(min_length=2)
    agent_slug: str | None = None
    model_name: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_cents: int = Field(default=0, ge=0)
    source: str = Field(default="runtime")
    request_id: str | None = None
    enforce_limits: bool = True
    auto_debit_wallet: bool = True


class WalletTopupPayload(BaseModel):
    """Payload for Stripe wallet top-up checkout sessions."""

    owner_id: str = Field(min_length=2)
    amount_usd: int = Field(ge=5, le=5000)


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


def _token_allowance_for_plan(plan: str) -> int | None:
    normalized = (plan or "").strip().lower()
    if normalized == "starter":
        return 50000
    if normalized == "professional":
        return 200000
    if normalized == "full_team":
        # Treated as effectively unlimited for governance views.
        return None
    return 10000


def _tokens_from_cents(cents: int) -> int:
    # Conservative conversion used for live governance meter when model-level token
    # telemetry is not available yet: $1 ~= 10k tokens.
    return max(0, int(cents) * 100)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _week_start(dt: datetime) -> datetime:
    # Monday start
    monday = dt.weekday()
    anchored = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return anchored - timedelta(days=monday)


def _safe_fetch_owner_controls(owner_id: str) -> dict[str, Any] | None:
    db = _get_db()
    try:
        response = (
            db.client.table("owner_billing_controls")
            .select("*")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _default_controls_from_plan(plan: str) -> dict[str, Any]:
    allowance = _token_allowance_for_plan(plan)
    monthly_cap = allowance if allowance is not None else 2000000
    return {
        "hourly_token_cap": min(25000, monthly_cap),
        "daily_token_cap": min(100000, monthly_cap),
        "weekly_token_cap": min(500000, monthly_cap),
        "monthly_token_cap": monthly_cap,
        "payg_enabled": True,
        "auto_refill_enabled": False,
        "auto_refill_threshold_tokens": 0,
        "auto_refill_amount_usd": 0,
    }


def _effective_controls(owner: dict[str, Any]) -> dict[str, Any]:
    plan = str(owner.get("plan") or owner.get("subscription_plan") or "free").lower()
    defaults = _default_controls_from_plan(plan)
    stored = _safe_fetch_owner_controls(str(owner.get("id") or ""))
    if not stored:
        return defaults
    for key in list(defaults.keys()):
        if key in stored and stored[key] is not None:
            defaults[key] = stored[key]
    return defaults


def _activity_spend_since(owner_id: str, since: datetime) -> int:
    db = _get_db()
    try:
        response = (
            db.client.table("activity_log")
            .select("cost_cents")
            .eq("owner_id", owner_id)
            .gte("created_at", since.isoformat())
            .execute()
        )
        rows = response.data or []
        total = 0
        for row in rows:
            try:
                total += int(row.get("cost_cents") or 0)
            except (TypeError, ValueError):
                continue
        return max(0, total)
    except Exception:
        return 0


def _token_usage_since(owner_id: str, since: datetime) -> tuple[int, int, int]:
    """Returns (tokens, cost_cents, row_count) from token_usage_ledger since timestamp."""
    db = _get_db()
    try:
        response = (
            db.client.table("token_usage_ledger")
            .select("total_tokens,cost_cents")
            .eq("owner_id", owner_id)
            .gte("created_at", since.isoformat())
            .execute()
        )
        rows = response.data or []
        total_tokens = 0
        total_cost = 0
        for row in rows:
            try:
                total_tokens += int(row.get("total_tokens") or 0)
                total_cost += int(row.get("cost_cents") or 0)
            except (TypeError, ValueError):
                continue
        return max(0, total_tokens), max(0, total_cost), len(rows)
    except Exception:
        return 0, 0, 0


def _safe_wallet_row(owner_id: str) -> dict[str, Any] | None:
    db = _get_db()
    try:
        response = (
            db.client.table("owner_wallets")
            .select("*")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _ensure_wallet(owner_id: str) -> dict[str, Any] | None:
    row = _safe_wallet_row(owner_id)
    if row:
        return row
    db = _get_db()
    payload = {
        "owner_id": owner_id,
        "balance_cents": 0,
        "currency": "usd",
        "updated_at": _utc_now().isoformat(),
        "created_at": _utc_now().isoformat(),
    }
    try:
        inserted = db.insert_one("owner_wallets", payload)
        return inserted
    except Exception:
        return None


def _credit_wallet(owner_id: str, amount_cents: int, reason: str, stripe_reference: str | None = None) -> bool:
    if amount_cents <= 0:
        return False
    wallet = _ensure_wallet(owner_id)
    if not wallet:
        return False
    db = _get_db()
    try:
        wallet_id = wallet.get("id")
        current_balance = int(wallet.get("balance_cents") or 0)
        new_balance = current_balance + int(amount_cents)
        db.update_many(
            "owner_wallets",
            {"id": wallet_id},
            {"balance_cents": new_balance, "updated_at": _utc_now().isoformat()},
        )
        db.insert_one(
            "wallet_transactions",
            {
                "owner_id": owner_id,
                "wallet_id": wallet_id,
                "direction": "credit",
                "amount_cents": int(amount_cents),
                "reason": reason,
                "stripe_reference": stripe_reference,
                "metadata": {},
                "created_at": _utc_now().isoformat(),
            },
        )
        return True
    except Exception:
        return False


def _debit_wallet(owner_id: str, amount_cents: int, reason: str, metadata: dict[str, Any] | None = None) -> bool:
    if amount_cents <= 0:
        return True
    wallet = _ensure_wallet(owner_id)
    if not wallet:
        return False
    db = _get_db()
    try:
        wallet_id = wallet.get("id")
        current_balance = int(wallet.get("balance_cents") or 0)
        if current_balance < int(amount_cents):
            return False
        new_balance = current_balance - int(amount_cents)
        db.update_many(
            "owner_wallets",
            {"id": wallet_id},
            {"balance_cents": new_balance, "updated_at": _utc_now().isoformat()},
        )
        db.insert_one(
            "wallet_transactions",
            {
                "owner_id": owner_id,
                "wallet_id": wallet_id,
                "direction": "debit",
                "amount_cents": int(amount_cents),
                "reason": reason,
                "stripe_reference": None,
                "metadata": metadata or {},
                "created_at": _utc_now().isoformat(),
            },
        )
        return True
    except Exception:
        return False


def _try_upsert_controls(owner_id: str, payload: BillingControlsPayload) -> bool:
    db = _get_db()
    data = {
        "owner_id": owner_id,
        "hourly_token_cap": payload.hourly_token_cap,
        "daily_token_cap": payload.daily_token_cap,
        "weekly_token_cap": payload.weekly_token_cap,
        "monthly_token_cap": payload.monthly_token_cap,
        "payg_enabled": payload.payg_enabled,
        "auto_refill_enabled": payload.auto_refill_enabled,
        "auto_refill_threshold_tokens": payload.auto_refill_threshold_tokens,
        "auto_refill_amount_usd": payload.auto_refill_amount_usd,
        "updated_at": _utc_now().isoformat(),
    }
    try:
        existing = _safe_fetch_owner_controls(owner_id)
        if existing and existing.get("id"):
            db.update_many("owner_billing_controls", {"id": existing["id"]}, data)
        else:
            data["created_at"] = _utc_now().isoformat()
            db.insert_one("owner_billing_controls", data)
        return True
    except Exception:
        return False


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
    plans = _plan_catalog()
    plans_list = [
        {
            "name": name,
            "display": name.replace("_", " ").title(),
            "price_monthly": details["monthly"],
            "price_annual": details["annual"],
            "included_agents": details["included_agents"],
            "features": details["features"],
            "agents": details["features"],
        }
        for name, details in plans.items()
    ]
    return {"plans": plans_list, "plans_by_key": plans, "addons": _addon_price_map()}


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
    plan = owner.get("plan") or owner.get("subscription_plan") or "free"
    return {
        "owner_id": owner_id,
        "plan": plan,
        "status": owner.get("subscription_status") or "inactive",
        "next_billing_date": _serialize_timestamp(owner.get("subscription_current_period_end")),
        "trial_ends_at": _serialize_timestamp(owner.get("trial_ends_at")),
        "amount": owner.get("subscription_amount_cents") or 0,
        "card_last_4": owner.get("stripe_card_last4") or None,
        "stripe_customer_id": owner.get("stripe_customer_id") or None,
        "stripe_subscription_id": owner.get("stripe_subscription_id") or None,
        "included_tokens": _token_allowance_for_plan(str(plan)),
        "spend_limit_cents": owner.get("spend_limit_cents") or owner.get("monthly_ai_budget_cents") or 0,
    }


@router.get("/trial-status/{owner_id}")
def get_trial_status(owner_id: str) -> dict[str, Any]:
    """Returns trial countdown and conversion status for owner billing UX."""
    owner = _get_owner(owner_id)
    trial_raw = owner.get("trial_ends_at")
    now = _utc_now()

    trial_dt: datetime | None = None
    if isinstance(trial_raw, datetime):
        trial_dt = trial_raw if trial_raw.tzinfo else trial_raw.replace(tzinfo=timezone.utc)
    elif isinstance(trial_raw, str) and trial_raw.strip():
        parsed = trial_raw.replace("Z", "+00:00")
        try:
            trial_dt = datetime.fromisoformat(parsed)
            if trial_dt.tzinfo is None:
                trial_dt = trial_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            trial_dt = None

    days_left = 0
    is_trial = False
    if trial_dt is not None:
        delta = trial_dt - now
        days_left = max(0, int(delta.total_seconds() // 86400))
        is_trial = delta.total_seconds() > 0

    return {
        "owner_id": owner_id,
        "is_trial": is_trial,
        "trial_ends_at": _serialize_timestamp(trial_raw),
        "days_left": days_left,
        "subscription_status": owner.get("subscription_status") or "inactive",
    }


@router.get("/usage/{owner_id}")
def get_usage(owner_id: str) -> dict[str, Any]:
    """Returns token/cost consumption against owner-defined usage controls."""
    owner = _get_owner(owner_id)
    plan = str(owner.get("plan") or owner.get("subscription_plan") or "free").lower()
    controls = _effective_controls(owner)

    now = _utc_now()
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = _week_start(now)
    month_start = _month_start(now)

    hourly_tokens, hourly_spend_cents, hour_rows = _token_usage_since(owner_id, hour_start)
    daily_tokens, daily_spend_cents, day_rows = _token_usage_since(owner_id, day_start)
    weekly_tokens, weekly_spend_cents, week_rows = _token_usage_since(owner_id, week_start)
    monthly_tokens, monthly_spend_cents, month_rows = _token_usage_since(owner_id, month_start)

    # Backward compatibility fallback when token ledger is not yet populated.
    if hour_rows == 0:
        hourly_spend_cents = _activity_spend_since(owner_id, hour_start)
        hourly_tokens = _tokens_from_cents(hourly_spend_cents)
    if day_rows == 0:
        daily_spend_cents = _activity_spend_since(owner_id, day_start)
        daily_tokens = _tokens_from_cents(daily_spend_cents)
    if week_rows == 0:
        weekly_spend_cents = _activity_spend_since(owner_id, week_start)
        weekly_tokens = _tokens_from_cents(weekly_spend_cents)
    if month_rows == 0:
        monthly_spend_cents = _activity_spend_since(owner_id, month_start)
        monthly_tokens = _tokens_from_cents(monthly_spend_cents)

    included_tokens = _token_allowance_for_plan(plan)
    remaining = None if included_tokens is None else max(0, included_tokens - monthly_tokens)

    return {
        "owner_id": owner_id,
        "plan": plan,
        "included_tokens_month": included_tokens,
        "tokens_used": {
            "hour": hourly_tokens,
            "day": daily_tokens,
            "week": weekly_tokens,
            "month": monthly_tokens,
        },
        "cost_used_cents": {
            "hour": hourly_spend_cents,
            "day": daily_spend_cents,
            "week": weekly_spend_cents,
            "month": monthly_spend_cents,
        },
        "tokens_remaining": remaining,
        "limits": controls,
        "payg_active": bool(controls.get("payg_enabled") and remaining == 0 if remaining is not None else controls.get("payg_enabled")),
        "usage_source": "token_ledger" if month_rows > 0 else "cost_fallback",
    }


@router.post("/usage/record")
def record_usage(payload: TokenUsageRecordPayload) -> dict[str, Any]:
    """Records model-level token usage for accurate allowance accounting."""
    owner = _get_owner(payload.owner_id)
    db = _get_db()
    total_tokens = payload.total_tokens if payload.total_tokens is not None else payload.input_tokens + payload.output_tokens

    controls = _effective_controls(owner)
    now = _utc_now()
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = _week_start(now)
    month_start = _month_start(now)

    hour_tokens, _, _ = _token_usage_since(payload.owner_id, hour_start)
    day_tokens, _, _ = _token_usage_since(payload.owner_id, day_start)
    week_tokens, _, _ = _token_usage_since(payload.owner_id, week_start)
    month_tokens, _, _ = _token_usage_since(payload.owner_id, month_start)

    projected_hour = hour_tokens + max(0, int(total_tokens))
    projected_day = day_tokens + max(0, int(total_tokens))
    projected_week = week_tokens + max(0, int(total_tokens))
    projected_month = month_tokens + max(0, int(total_tokens))

    limit_violations: list[str] = []
    if projected_hour > int(controls.get("hourly_token_cap") or 0):
        limit_violations.append("hourly_token_cap")
    if projected_day > int(controls.get("daily_token_cap") or 0):
        limit_violations.append("daily_token_cap")
    if projected_week > int(controls.get("weekly_token_cap") or 0):
        limit_violations.append("weekly_token_cap")
    if projected_month > int(controls.get("monthly_token_cap") or 0):
        limit_violations.append("monthly_token_cap")

    if payload.enforce_limits and limit_violations:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Usage blocked by token governance limits.",
                "violations": limit_violations,
            },
        )

    plan = str(owner.get("plan") or owner.get("subscription_plan") or "free").lower()
    included_tokens = _token_allowance_for_plan(plan)
    would_overrun_included = included_tokens is not None and projected_month > included_tokens
    payg_enabled = bool(controls.get("payg_enabled"))

    wallet_debited = False
    wallet_charge_cents = int(payload.cost_cents or 0)
    if would_overrun_included and payload.auto_debit_wallet:
        if not payg_enabled:
            raise HTTPException(status_code=402, detail="Included tokens exhausted and PAYG is disabled.")
        wallet_debited = _debit_wallet(
            owner_id=payload.owner_id,
            amount_cents=wallet_charge_cents,
            reason="payg_usage",
            metadata={
                "request_id": payload.request_id,
                "agent_slug": payload.agent_slug,
                "tokens": max(0, int(total_tokens)),
            },
        )
        if not wallet_debited:
            raise HTTPException(status_code=402, detail="Insufficient wallet balance for PAYG usage.")

    try:
        row = db.insert_one(
            "token_usage_ledger",
            {
                "owner_id": payload.owner_id,
                "agent_slug": payload.agent_slug,
                "model_name": payload.model_name,
                "input_tokens": payload.input_tokens,
                "output_tokens": payload.output_tokens,
                "total_tokens": max(0, int(total_tokens)),
                "cost_cents": payload.cost_cents,
                "source": payload.source,
                "request_id": payload.request_id,
                "created_at": _utc_now().isoformat(),
            },
        )
    except Exception as error:
        if payload.request_id:
            try:
                existing = (
                    db.client.table("token_usage_ledger")
                    .select("*")
                    .eq("request_id", payload.request_id)
                    .limit(1)
                    .execute()
                )
                rows = existing.data or []
                if rows:
                    return {
                        "success": True,
                        "record": rows[0],
                        "limits_checked": True,
                        "violations": limit_violations,
                        "payg_applied": False,
                        "wallet_charge_cents": 0,
                        "idempotent_replay": True,
                    }
            except Exception:
                pass
        raise HTTPException(
            status_code=503,
            detail=f"Token usage ledger is not ready. Run billing migration patch. ({error})",
        ) from error
    return {
        "success": True,
        "record": row,
        "limits_checked": True,
        "violations": limit_violations,
        "payg_applied": bool(wallet_debited),
        "wallet_charge_cents": wallet_charge_cents if wallet_debited else 0,
    }


@router.get("/wallet/{owner_id}")
def get_wallet(owner_id: str) -> dict[str, Any]:
    """Returns current PAYG wallet balance for owner."""
    _get_owner(owner_id)
    row = _ensure_wallet(owner_id)
    if not row:
        raise HTTPException(status_code=503, detail="Wallet storage is not ready. Run billing migration patch.")
    return {
        "owner_id": owner_id,
        "balance_cents": int(row.get("balance_cents") or 0),
        "currency": str(row.get("currency") or "usd").upper(),
        "updated_at": _serialize_timestamp(row.get("updated_at")),
    }


@router.get("/wallet-transactions/{owner_id}")
def get_wallet_transactions(owner_id: str) -> dict[str, Any]:
    """Returns wallet top-up/debit transaction history for owner."""
    _get_owner(owner_id)
    db = _get_db()
    try:
        response = (
            db.client.table("wallet_transactions")
            .select("id,direction,amount_cents,reason,stripe_reference,created_at")
            .eq("owner_id", owner_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        rows = response.data or []
    except Exception:
        rows = []
    return {"owner_id": owner_id, "transactions": rows}


@router.post("/wallet/topup-checkout")
def create_wallet_topup_checkout(payload: WalletTopupPayload) -> dict[str, Any]:
    """Creates a Stripe Checkout session for wallet top-ups (PAYG credit)."""
    owner = _get_owner(payload.owner_id)
    stripe_client = _stripe_client_ready()
    amount_cents = int(payload.amount_usd) * 100
    session = stripe_client.checkout.Session.create(
        customer=owner.get("stripe_customer_id") or None,
        customer_email=owner.get("email"),
        mode="payment",
        allow_promotion_codes=False,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "ORB PAYG wallet top-up"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        success_url=f"{_app_base_url()}/dashboard/billing?wallet_topup=success",
        cancel_url=f"{_app_base_url()}/dashboard/billing?wallet_topup=cancel",
        metadata={
            "owner_id": payload.owner_id,
            "wallet_topup": "true",
            "amount_cents": str(amount_cents),
        },
    )
    return {
        "checkout_url": session.get("url"),
        "session_id": session.get("id"),
        "amount_cents": amount_cents,
    }


@router.get("/controls/{owner_id}")
def get_billing_controls(owner_id: str) -> dict[str, Any]:
    """Returns current token controls and PAYG behavior for an owner."""
    owner = _get_owner(owner_id)
    controls = _effective_controls(owner)
    return {"owner_id": owner_id, "controls": controls}


@router.post("/controls/{owner_id}")
def update_billing_controls(owner_id: str, payload: BillingControlsPayload) -> dict[str, Any]:
    """Persists owner-level usage caps and PAYG settings."""
    _get_owner(owner_id)
    if payload.monthly_token_cap and payload.weekly_token_cap > payload.monthly_token_cap:
        raise HTTPException(status_code=400, detail="Weekly cap cannot exceed monthly cap.")
    if payload.weekly_token_cap and payload.daily_token_cap > payload.weekly_token_cap:
        raise HTTPException(status_code=400, detail="Daily cap cannot exceed weekly cap.")
    if payload.daily_token_cap and payload.hourly_token_cap > payload.daily_token_cap:
        raise HTTPException(status_code=400, detail="Hourly cap cannot exceed daily cap.")

    if not _try_upsert_controls(owner_id, payload):
        raise HTTPException(
            status_code=503,
            detail="Billing controls storage is not ready. Run the latest billing migration patch.",
        )

    return {"success": True, "owner_id": owner_id, "controls": payload.model_dump()}


@router.get("/payment-methods/{owner_id}")
def get_payment_methods(owner_id: str) -> dict[str, Any]:
    """Returns saved Stripe payment methods for owner self-serve billing."""
    owner = _get_owner(owner_id)
    customer_id = str(owner.get("stripe_customer_id") or "").strip()
    if not customer_id:
        return {"owner_id": owner_id, "payment_methods": [], "default_payment_method": None}

    stripe_client = _stripe_client_ready()
    try:
        customer = stripe_client.Customer.retrieve(customer_id)
        default_id = None
        invoice_settings = customer.get("invoice_settings") or {}
        if isinstance(invoice_settings, dict):
            default_id = invoice_settings.get("default_payment_method")

        methods = stripe_client.PaymentMethod.list(customer=customer_id, type="card", limit=10)
        serialized = []
        for method in (methods.data or []):
            card = method.get("card") or {}
            serialized.append(
                {
                    "id": method.get("id"),
                    "brand": card.get("brand"),
                    "last4": card.get("last4"),
                    "exp_month": card.get("exp_month"),
                    "exp_year": card.get("exp_year"),
                    "is_default": method.get("id") == default_id,
                }
            )
        return {
            "owner_id": owner_id,
            "payment_methods": serialized,
            "default_payment_method": default_id,
        }
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Could not fetch payment methods: {error}") from error


@router.get("/charges/{owner_id}")
def get_recent_charges(owner_id: str) -> dict[str, Any]:
    """Returns recent Stripe invoices or a usage-cost fallback ledger."""
    owner = _get_owner(owner_id)
    customer_id = str(owner.get("stripe_customer_id") or "").strip()

    if customer_id:
        stripe_client = _stripe_client_ready()
        try:
            invoices = stripe_client.Invoice.list(customer=customer_id, limit=20)
            rows = []
            for inv in invoices.data or []:
                rows.append(
                    {
                        "id": inv.get("id"),
                        "amount_cents": inv.get("amount_paid") or inv.get("amount_due") or 0,
                        "currency": (inv.get("currency") or "usd").upper(),
                        "status": inv.get("status") or "unknown",
                        "description": inv.get("description") or "ORB subscription charge",
                        "created_at": _serialize_timestamp(inv.get("created")),
                        "invoice_pdf": inv.get("invoice_pdf"),
                    }
                )
            return {"owner_id": owner_id, "charges": rows, "source": "stripe"}
        except Exception:
            # Continue to fallback below.
            pass

    db = _get_db()
    try:
        response = (
            db.client.table("activity_log")
            .select("id,cost_cents,description,created_at")
            .eq("owner_id", owner_id)
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        rows = response.data or []
    except Exception:
        rows = []

    charges = [
        {
            "id": row.get("id"),
            "amount_cents": row.get("cost_cents") or 0,
            "currency": "USD",
            "status": "posted",
            "description": row.get("description") or "ORB metered usage",
            "created_at": _serialize_timestamp(row.get("created_at")),
            "invoice_pdf": None,
        }
        for row in rows
        if int(row.get("cost_cents") or 0) > 0
    ]
    return {"owner_id": owner_id, "charges": charges, "source": "usage_log"}
