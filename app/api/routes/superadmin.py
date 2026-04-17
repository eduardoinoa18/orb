"""Super admin routes for platform-wide operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.api.middleware.superadmin import require_superadmin
from app.database.connection import DatabaseConnectionError, SupabaseService
from app.runtime.preflight import build_preflight_report
from app.ui_shell import render_admin_dashboard
from config.settings import get_settings

router = APIRouter(prefix="/admin", tags=["superadmin"])


class PlanUpdatePayload(BaseModel):
    plan: str = Field(min_length=2)
    reason: str = Field(min_length=3)


class FeatureFlagUpdatePayload(BaseModel):
    is_enabled: bool
    enabled_for_plans: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)


class BillingStatusUpdatePayload(BaseModel):
    status: str = Field(pattern="^(active|inactive|past_due|cancelled|trialing|paused)$")
    plan: str | None = None
    reason: str = Field(min_length=3)


def _stripe_ready() -> stripe:
    settings = get_settings()
    if not settings.stripe_secret_key.strip():
        raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY is not configured.")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _app_base_url() -> str:
    settings = get_settings()
    domain = (settings.next_public_api_url or f"https://{settings.platform_domain}").strip()
    return domain.rstrip("/")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


@router.get("/")
def admin_home(request: Request, owner: dict[str, Any] = Depends(require_superadmin)) -> Any:
    if "text/html" in (request.headers.get("accept") or ""):
        summary = {
            "owner_email": owner.get("email"),
            "role": owner.get("role") or "superadmin",
        }
        return render_admin_dashboard(summary)
    return JSONResponse(
        content={
            "status": "ok",
            "message": "Super admin working.",
            "owner_email": owner.get("email"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/users")
def admin_users(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        owners = db.fetch_all("owners")
        agents = db.fetch_all("agents")
        activity = db.fetch_all("activity_log")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    agent_count_by_owner: dict[str, int] = {}
    for row in agents:
        owner_id = str(row.get("owner_id") or "")
        if owner_id:
            agent_count_by_owner[owner_id] = agent_count_by_owner.get(owner_id, 0) + 1

    cost_by_owner: dict[str, int] = {}
    last_active_by_owner: dict[str, str] = {}
    for row in activity:
        owner_id = str(row.get("owner_id") or "")
        if not owner_id:
            continue
        cost_by_owner[owner_id] = cost_by_owner.get(owner_id, 0) + _safe_int(row.get("cost_cents"))
        created_at = str(row.get("created_at") or "")
        if created_at and created_at > last_active_by_owner.get(owner_id, ""):
            last_active_by_owner[owner_id] = created_at

    rows = []
    for row in owners:
        owner_id = str(row.get("id") or "")
        amount = _safe_int(
            row.get("subscription_amount_cents")
            or row.get("monthly_amount_cents")
            or row.get("mrr_cents")
        )
        rows.append(
            {
                "owner_id": owner_id,
                "email": row.get("email"),
                "name": row.get("name") or row.get("full_name") or "",
                "role": row.get("role") or "user",
                "is_superadmin": bool(row.get("is_superadmin")),
                "plan": row.get("plan") or row.get("subscription_plan") or "free",
                "status": row.get("subscription_status") or "unknown",
                "mrr_cents": amount,
                "agent_count": agent_count_by_owner.get(owner_id, 0),
                "total_ai_spend_cents": cost_by_owner.get(owner_id, 0),
                "last_active": last_active_by_owner.get(owner_id) or row.get("updated_at") or row.get("created_at"),
            }
        )

    rows.sort(key=lambda item: str(item.get("last_active") or ""), reverse=True)
    return {
        "count": len(rows),
        "users": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/users/{owner_id}")
def admin_user_detail(owner_id: str, owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        users = db.fetch_all("owners", {"id": owner_id})
        agents = db.fetch_all("agents", {"owner_id": owner_id})
        activity = db.fetch_all("activity_log", {"owner_id": owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not users:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "user": users[0],
        "agents": agents,
        "activity": activity[-50:],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/users/{owner_id}/plan")
def admin_user_plan_update(
    owner_id: str,
    payload: PlanUpdatePayload,
    actor: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    try:
        db = SupabaseService()
        updates = {
            "plan": payload.plan,
            "subscription_plan": payload.plan,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = db.update_many("owners", {"id": owner_id}, updates)
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="admin_plan_override",
            description=(
                f"Plan overridden to '{payload.plan}' by {actor.get('email') or 'superadmin'}. "
                f"Reason: {payload.reason}"
            ),
            cost_cents=0,
            outcome="success",
            metadata={
                "actor_email": actor.get("email"),
                "reason": payload.reason,
            },
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "status": "ok",
        "owner_id": owner_id,
        "plan": payload.plan,
        "reason": payload.reason,
        "updated_at": updates["updated_at"],
    }


@router.get("/platform/health")
def admin_platform_health(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    report = build_preflight_report()
    try:
        db = SupabaseService()
        owners = db.fetch_all("owners")
        agents = db.fetch_all("agents")
        activity = db.fetch_all("activity_log")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "preflight": report,
        "counts": {
            "owners": len(owners),
            "agents": len(agents),
            "activity_events": len(activity),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/feature-flags")
def admin_feature_flags(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        rows = db.fetch_all("feature_flags")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    rows.sort(key=lambda row: str(row.get("flag_name") or ""))
    return {
        "count": len(rows),
        "flags": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/feature-flags/{flag_name}")
def admin_feature_flag_update(
    flag_name: str,
    payload: FeatureFlagUpdatePayload,
    actor: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    try:
        db = SupabaseService()
        updates = {
            "is_enabled": payload.is_enabled,
            "enabled_for_plans": payload.enabled_for_plans,
            "description": payload.description,
            "updated_by": actor.get("email") or "superadmin",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = db.update_many("feature_flags", {"flag_name": flag_name}, updates)
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not rows:
        raise HTTPException(status_code=404, detail="Feature flag not found.")

    return {
        "status": "ok",
        "flag_name": flag_name,
        "flag": rows[0],
        "updated_at": updates["updated_at"],
    }


@router.get("/audit-log")
def admin_audit_log(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        rows = db.fetch_all("activity_log")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    entries = [
        {
            "action_type": r.get("action_type") or "",
            "description": r.get("description") or "",
            "created_at": str(r.get("created_at") or ""),
            "owner_id": str(r.get("owner_id") or ""),
            "agent_id": str(r.get("agent_id") or ""),
            "outcome": r.get("outcome") or "",
        }
        for r in rows[:200]
    ]
    return {
        "count": len(entries),
        "entries": entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/costs/summary")
def admin_costs_summary(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        rows = db.fetch_all("activity_log")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    total_cents = sum(_safe_int(r.get("cost_cents")) for r in rows)
    by_owner: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    for r in rows:
        oid = str(r.get("owner_id") or "")
        aid = str(r.get("agent_id") or "")
        cost = _safe_int(r.get("cost_cents"))
        if oid:
            by_owner[oid] = by_owner.get(oid, 0) + cost
        if aid:
            by_agent[aid] = by_agent.get(aid, 0) + cost

    return {
        "total_cost_cents": total_cents,
        "total_cost_usd": round(total_cents / 100, 2),
        "by_owner": [{"owner_id": k, "cost_cents": v} for k, v in sorted(by_owner.items(), key=lambda x: -x[1])[:50]],
        "by_agent": [{"agent_id": k, "cost_cents": v} for k, v in sorted(by_agent.items(), key=lambda x: -x[1])[:50]],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/billing/subscriptions")
def admin_billing_subscriptions(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        owners = db.fetch_all("owners")
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    rows = []
    for row in owners:
        rows.append(
            {
                "owner_id": str(row.get("id") or ""),
                "email": row.get("email"),
                "name": row.get("name") or row.get("full_name") or "",
                "plan": row.get("plan") or row.get("subscription_plan") or "free",
                "status": row.get("subscription_status") or "inactive",
                "trial_ends_at": row.get("trial_ends_at"),
                "next_billing_date": row.get("subscription_current_period_end"),
                "amount_cents": _safe_int(row.get("subscription_amount_cents")),
                "stripe_customer_id": row.get("stripe_customer_id") or None,
                "stripe_subscription_id": row.get("stripe_subscription_id") or None,
                "billing_exempt": bool(row.get("billing_exempt") or False),
            }
        )
    rows.sort(key=lambda item: str(item.get("email") or ""))
    return {"count": len(rows), "subscriptions": rows, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/billing/subscriptions/{owner_id}/status")
def admin_billing_update_status(
    owner_id: str,
    payload: BillingStatusUpdatePayload,
    actor: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    try:
        db = SupabaseService()
        updates: dict[str, Any] = {
            "subscription_status": payload.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if payload.plan:
            updates["plan"] = payload.plan
            updates["subscription_plan"] = payload.plan
        rows = db.update_many("owners", {"id": owner_id}, updates)
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="admin_billing_status_update",
            description=(
                f"Billing status changed to '{payload.status}' by {actor.get('email') or 'superadmin'}. "
                f"Reason: {payload.reason}"
            ),
            outcome="success",
            metadata={"actor_email": actor.get("email"), "reason": payload.reason, "plan": payload.plan},
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not rows:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "ok", "owner_id": owner_id, "updated": rows[0]}


@router.post("/billing/subscriptions/{owner_id}/portal")
def admin_billing_portal(owner_id: str, owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    try:
        db = SupabaseService()
        rows = db.fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not rows:
        raise HTTPException(status_code=404, detail="User not found.")

    customer_id = str(rows[0].get("stripe_customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=404, detail="Owner has no Stripe customer.")

    stripe_client = _stripe_ready()
    session = stripe_client.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{_app_base_url()}/admin/billing",
    )
    return {"owner_id": owner_id, "portal_url": session.get("url"), "customer_id": customer_id}


@router.get("/billing/stripe-recommended-events")
def admin_billing_stripe_recommended_events(owner: dict[str, Any] = Depends(require_superadmin)) -> dict[str, Any]:
    del owner
    events = [
        {"event": "checkout.session.completed", "why": "Activate subscriptions and wallet top-ups after checkout."},
        {"event": "customer.subscription.updated", "why": "Sync plan/status and period boundaries."},
        {"event": "customer.subscription.deleted", "why": "Handle cancellations and deprovision paid features."},
        {"event": "invoice.paid", "why": "Confirm successful recurring payment and clear dunning state."},
        {"event": "invoice.payment_failed", "why": "Mark past_due and trigger owner follow-up."},
        {"event": "invoice.upcoming", "why": "Pre-billing reminder and spend/limit visibility."},
        {"event": "customer.subscription.trial_will_end", "why": "Trial conversion prompts and billing reminder workflows."},
        {"event": "charge.refunded", "why": "Reconcile wallet/subscription adjustments and audit logs."},
    ]
    return {
        "count": len(events),
        "events": events,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
