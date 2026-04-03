"""Super admin routes for platform-wide operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.middleware.superadmin import require_superadmin
from app.database.connection import DatabaseConnectionError, SupabaseService
from app.runtime.preflight import build_preflight_report
from app.ui_shell import render_admin_dashboard

router = APIRouter(prefix="/admin", tags=["superadmin"])


class PlanUpdatePayload(BaseModel):
    plan: str = Field(min_length=2)
    reason: str = Field(min_length=3)


class FeatureFlagUpdatePayload(BaseModel):
    is_enabled: bool
    enabled_for_plans: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=300)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


@router.get("/", response_class=HTMLResponse)
def admin_home(request: Request, owner: dict[str, Any] = Depends(require_superadmin)) -> Any:
    if "text/html" in (request.headers.get("accept") or ""):
        summary = {
            "owner_email": owner.get("email"),
            "role": owner.get("role") or "superadmin",
        }
        return render_admin_dashboard(summary)
    return {
        "status": "ok",
        "message": "Super admin working.",
        "owner_email": owner.get("email"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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
