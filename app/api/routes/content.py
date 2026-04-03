"""Nova content routes (Level 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.nova.nova_brain import NovaBrain
from agents.nova.content_creator import NovaContentCreator
from app.database.connection import DatabaseConnectionError, SupabaseService

router = APIRouter(prefix="/agents/nova", tags=["nova"])

creator = NovaContentCreator()
nova_brain = NovaBrain()


class ListingPostRequest(BaseModel):
    owner_id: str
    property_data: dict[str, Any]
    platforms: list[str] | None = None


class MarketUpdateRequest(BaseModel):
    owner_id: str
    market_area: str
    month: str


class JustSoldRequest(BaseModel):
    owner_id: str
    property_data: dict[str, Any]
    sale_price: str
    days_on_market: int


class WeeklyCalendarRequest(BaseModel):
    owner_id: str
    week_start: str


class ApproveContentRequest(BaseModel):
    scheduled_for: str | None = None


class RejectContentRequest(BaseModel):
    reason: str


class BatchApproveRequest(BaseModel):
    content_ids: list[str]
    scheduled_for: str | None = None


class RescheduleContentRequest(BaseModel):
    scheduled_for: str


class NovaLearnRequest(BaseModel):
    owner_id: str


@router.get("/status")
def nova_status() -> dict[str, str]:
    """Health check for Nova routes."""
    return {"status": "nova router ready"}


@router.get("/content-status")
def nova_content_status() -> dict[str, Any]:
    """Checks whether the content table is reachable in the current database."""
    db = SupabaseService()
    try:
        rows = db.fetch_all("content")
        return {"status": "ok", "content_table_accessible": True, "row_count": len(rows)}
    except DatabaseConnectionError as error:
        return {
            "status": "error",
            "content_table_accessible": False,
            "detail": str(error),
        }


@router.post("/listing-post")
def create_listing_post(payload: ListingPostRequest) -> dict[str, Any]:
    """Creates listing content drafts for requested platforms."""
    try:
        return creator.create_listing_post(
            property_data=payload.property_data,
            owner_id=payload.owner_id,
            platforms=payload.platforms,
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/market-update")
def create_market_update(payload: MarketUpdateRequest) -> dict[str, Any]:
    """Creates market update social and newsletter drafts."""
    try:
        return creator.create_market_update(
            owner_id=payload.owner_id,
            market_area=payload.market_area,
            month=payload.month,
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/just-sold")
def create_just_sold(payload: JustSoldRequest) -> dict[str, Any]:
    """Creates celebratory just-sold drafts."""
    try:
        return creator.create_just_sold_post(
            property_data=payload.property_data,
            sale_price=payload.sale_price,
            days_on_market=payload.days_on_market,
            owner_id=payload.owner_id,
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/weekly-calendar")
def create_weekly_calendar(payload: WeeklyCalendarRequest) -> dict[str, Any]:
    """Creates 7-day content calendar drafts."""
    try:
        return creator.generate_weekly_content_calendar(
            owner_id=payload.owner_id,
            week_start=payload.week_start,
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/content")
def list_content(owner_id: str, status: str | None = None) -> dict[str, Any]:
    """Lists content queue rows for an owner."""
    db = SupabaseService()
    filters: dict[str, Any] = {"owner_id": owner_id}
    if status:
        filters["status"] = status
    try:
        rows = db.fetch_all("content", filters)
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"content": rows, "count": len(rows)}


@router.post("/content/{content_id}/approve")
def approve_content(content_id: str, payload: ApproveContentRequest) -> dict[str, Any]:
    """Approves a draft and queues it for publishing."""
    db = SupabaseService()
    update_payload: dict[str, Any] = {"status": "queued"}
    if payload.scheduled_for:
        update_payload["scheduled_for"] = payload.scheduled_for

    rows = db.update_many("content", {"id": content_id}, update_payload)
    if not rows:
        raise HTTPException(status_code=404, detail="Content item not found.")
    return {"status": "queued", "content_id": content_id}


@router.post("/content/{content_id}/reject")
def reject_content(content_id: str, payload: RejectContentRequest) -> dict[str, Any]:
    """Rejects a draft and stores feedback in performance_data."""
    db = SupabaseService()
    items = db.fetch_all("content", {"id": content_id})
    if not items:
        raise HTTPException(status_code=404, detail="Content item not found.")

    current = items[0]
    feedback = dict(current.get("performance_data") or {})
    feedback["rejection_reason"] = payload.reason

    rows = db.update_many(
        "content",
        {"id": content_id},
        {"status": "rejected", "performance_data": feedback},
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Failed to reject content.")
    return {"status": "rejected", "content_id": content_id, "reason": payload.reason}


@router.post("/learn-outcomes")
def nova_learn_outcomes(payload: NovaLearnRequest) -> dict[str, Any]:
    """Runs Nova weekly self-improvement review."""
    try:
        return nova_brain.learn_from_outcomes(owner_id=payload.owner_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/owner-needs")
def nova_owner_needs(payload: NovaLearnRequest) -> dict[str, Any]:
    """Returns proactive suggestions inferred from Nova activity patterns."""
    try:
        return nova_brain.identify_owner_needs(owner_id=payload.owner_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/content/pending")
def list_pending_content(owner_id: str, limit: int = 20) -> dict[str, Any]:
    """Lists all draft content awaiting approval for the approval dashboard."""
    db = SupabaseService()
    try:
        rows = db.fetch_all("content", {"owner_id": owner_id, "status": "draft"})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"content": rows[:limit], "count": len(rows[:limit]), "total": len(rows)}


@router.get("/content/{content_id}")
def get_content_item(content_id: str) -> dict[str, Any]:
    """Retrieves a single content item with full details for the approval modal."""
    db = SupabaseService()
    try:
        items = db.fetch_all("content", {"id": content_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not items:
        raise HTTPException(status_code=404, detail="Content item not found.")
    return items[0]


@router.post("/content/batch-approve")
def batch_approve_content(payload: BatchApproveRequest) -> dict[str, Any]:
    """Approves multiple content drafts in one call for dashboard bulk actions."""
    if not payload.content_ids:
        raise HTTPException(status_code=422, detail="content_ids must not be empty.")
    db = SupabaseService()
    approved: list[str] = []
    failed: list[str] = []
    update_payload: dict[str, Any] = {"status": "queued"}
    if payload.scheduled_for:
        update_payload["scheduled_for"] = payload.scheduled_for

    for cid in payload.content_ids:
        try:
            rows = db.update_many("content", {"id": cid}, update_payload)
            if rows:
                approved.append(cid)
            else:
                failed.append(cid)
        except DatabaseConnectionError:
            failed.append(cid)

    return {"approved": approved, "failed": failed, "approved_count": len(approved)}


@router.put("/content/{content_id}/reschedule")
def reschedule_content(content_id: str, payload: RescheduleContentRequest) -> dict[str, Any]:
    """Updates the scheduled_for date for a queued content item."""
    db = SupabaseService()
    try:
        items = db.fetch_all("content", {"id": content_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not items:
        raise HTTPException(status_code=404, detail="Content item not found.")

    current_status = items[0].get("status")
    if current_status not in ("queued", "draft"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reschedule content with status '{current_status}'.",
        )

    try:
        db.update_many("content", {"id": content_id}, {"scheduled_for": payload.scheduled_for})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {"content_id": content_id, "scheduled_for": payload.scheduled_for, "status": current_status}
