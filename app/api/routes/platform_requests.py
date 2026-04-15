"""Platform Requests — User Agents → Eduardo's Admin Agent Pipeline.

When a user's Commander can't do something, it files a platform request.
Eduardo's master Commander sees all requests in a unified inbox and can:
  - Respond with a message back to the user's Commander
  - Create a platform_task to actually build the feature
  - Reject with a reason
  - Ask for more information

This is the "never-ending self-improving" engine at the core of ORB.

Also manages the Agent Messages bus for direct agent-to-agent communication.

Endpoints:
  POST   /platform-requests                     — user agent files a request
  GET    /platform-requests                     — list requests (user sees own, admin sees all)
  GET    /platform-requests/{id}                — get single request
  PATCH  /platform-requests/{id}                — admin updates status/response
  GET    /platform-requests/inbox               — admin inbox (Eduardo only)
  GET    /platform-requests/stats               — aggregate stats

  POST   /agent-messages                        — send message to another agent
  GET    /agent-messages/inbox                  — messages received by this owner's agent
  PATCH  /agent-messages/{id}/read              — mark as read
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.platform_requests")

router = APIRouter(tags=["Platform Intelligence"])

ADMIN_OWNER_IDS: set[str] = set()  # populated from env/DB at startup


def _require_owner(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(owner_id)


def _is_admin(owner_id: str, db: SupabaseService) -> bool:
    """Returns True if this owner has platform admin rights."""
    try:
        rows = db.client.table("business_profiles") \
            .select("is_platform_admin") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        if rows.data:
            return bool(rows.data[0].get("is_platform_admin", False))
    except Exception:
        pass
    return False


# ─── Platform Requests Models ─────────────────────────────────────────────────

class PlatformRequestCreate(BaseModel):
    request_type: str
    title: str
    description: str
    priority: str = "normal"
    context: dict = {}


class PlatformRequestUpdate(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    response_message: Optional[str] = None
    assigned_task_id: Optional[str] = None
    handled_by_owner_id: Optional[str] = None


# ─── Platform Requests Routes ─────────────────────────────────────────────────

@router.post("/platform-requests")
async def file_request(request: Request, body: PlatformRequestCreate):
    """User's Commander files a feature/integration/help request.

    Automatically finds the platform admin to route it to.
    Creates an agent_message to notify the admin's Commander.
    """
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()

        # Find the platform admin (Eduardo)
        admin_rows = db.client.table("business_profiles") \
            .select("owner_id") \
            .eq("is_platform_admin", True) \
            .limit(1) \
            .execute()
        admin_id = admin_rows.data[0]["owner_id"] if admin_rows.data else None

        req_data = {
            "requester_id": owner_id,
            "request_type": body.request_type,
            "title": body.title,
            "description": body.description,
            "priority": body.priority,
            "context": body.context,
            "status": "pending",
            "handled_by_owner_id": admin_id,
        }
        result = db.client.table("platform_requests").insert(req_data).execute()
        req_id = result.data[0]["id"] if result.data else str(uuid4())

        # Notify admin via agent_messages
        if admin_id:
            db.client.table("agent_messages").insert({
                "from_owner_id": owner_id,
                "to_owner_id": admin_id,
                "from_agent_type": "commander",
                "to_agent_type": "commander",
                "message_type": "request",
                "subject": f"[{body.request_type.upper()}] {body.title}",
                "body": body.description,
                "payload": {
                    "request_id": req_id,
                    "priority": body.priority,
                    "context": body.context,
                },
                "thread_id": req_id,
            }).execute()

        return {
            "request_id": req_id,
            "status": "filed",
            "message": "Your request has been filed. The platform team will respond shortly.",
            "routed_to_admin": bool(admin_id),
        }
    except Exception as e:
        logger.error(f"Failed to file platform request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform-requests")
async def list_requests(
    request: Request,
    status: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List platform requests. Admins see all; users see their own."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        is_admin = _is_admin(owner_id, db)

        q = db.client.table("platform_requests").select("*")
        if not is_admin:
            q = q.eq("requester_id", owner_id)
        if status:
            q = q.eq("status", status)
        if request_type:
            q = q.eq("request_type", request_type)
        rows = q.order("created_at", desc=True).limit(limit).execute()
        return {"requests": rows.data or [], "is_admin": is_admin, "total": len(rows.data or [])}
    except Exception as e:
        logger.error(f"Failed to list platform requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform-requests/inbox")
async def admin_inbox(request: Request):
    """Eduardo's unified inbox — all pending requests, sorted by priority."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        if not _is_admin(owner_id, db):
            raise HTTPException(status_code=403, detail="Platform admin access required")

        rows = db.client.table("platform_requests") \
            .select("*, platform_tasks(id,status,title)") \
            .in_("status", ["pending", "acknowledged", "in_progress", "needs_info"]) \
            .order("priority", desc=True) \
            .order("created_at", desc=True) \
            .limit(100) \
            .execute()

        # Unread agent_messages count
        unread = db.client.table("agent_messages") \
            .select("id", count="exact") \
            .eq("to_owner_id", owner_id) \
            .eq("is_read", False) \
            .execute()

        return {
            "inbox": rows.data or [],
            "unread_messages": unread.count or 0,
            "total_pending": len(rows.data or []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load admin inbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform-requests/stats")
async def request_stats(request: Request):
    """Aggregate stats on platform requests for the admin dashboard."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        if not _is_admin(owner_id, db):
            raise HTTPException(status_code=403, detail="Platform admin access required")

        all_rows = db.client.table("platform_requests").select("status,request_type,priority").execute()
        rows = all_rows.data or []
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_type[r["request_type"]] = by_type.get(r["request_type"], 0) + 1

        return {"total": len(rows), "by_status": by_status, "by_type": by_type}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platform-requests/{req_id}")
async def get_request(request: Request, req_id: str):
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        is_admin = _is_admin(owner_id, db)
        rows = db.client.table("platform_requests").select("*").eq("id", req_id).limit(1).execute()
        if not rows.data:
            raise HTTPException(status_code=404, detail="Request not found")
        req = rows.data[0]
        if not is_admin and req["requester_id"] != owner_id:
            raise HTTPException(status_code=403, detail="Access denied")
        return {"request": req}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/platform-requests/{req_id}")
async def update_request(request: Request, req_id: str, body: PlatformRequestUpdate):
    """Admin updates status, adds notes, or sends response back to user's Commander."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        if not _is_admin(owner_id, db):
            raise HTTPException(status_code=403, detail="Platform admin access required")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        if body.response_message:
            updates["responded_at"] = datetime.now(timezone.utc).isoformat()

        result = db.client.table("platform_requests") \
            .update(updates) \
            .eq("id", req_id) \
            .execute()

        # If there's a response, send it back to the requester via agent_messages
        if body.response_message and result.data:
            req = result.data[0]
            db.client.table("agent_messages").insert({
                "from_owner_id": owner_id,
                "to_owner_id": req["requester_id"],
                "from_agent_type": "commander",
                "to_agent_type": "commander",
                "message_type": "response",
                "subject": f"Re: {req.get('title', 'Your request')}",
                "body": body.response_message,
                "payload": {"request_id": req_id, "new_status": body.status},
                "thread_id": req_id,
            }).execute()

        return {"request": result.data[0] if result.data else None, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Agent Messages Routes ────────────────────────────────────────────────────

class AgentMessageCreate(BaseModel):
    to_owner_id: str
    message_type: str = "request"
    subject: Optional[str] = None
    body: str
    payload: dict = {}
    thread_id: Optional[str] = None
    reply_to_id: Optional[str] = None


@router.post("/agent-messages")
async def send_agent_message(request: Request, body: AgentMessageCreate):
    """Send a direct message from this owner's Commander to another owner's Commander."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        thread = body.thread_id or str(uuid4())
        result = db.client.table("agent_messages").insert({
            "from_owner_id": owner_id,
            "to_owner_id": body.to_owner_id,
            "message_type": body.message_type,
            "subject": body.subject,
            "body": body.body,
            "payload": body.payload,
            "thread_id": thread,
            "reply_to_id": body.reply_to_id,
        }).execute()
        return {"message": result.data[0] if result.data else None, "status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent-messages/inbox")
async def agent_inbox(request: Request, unread_only: bool = Query(False)):
    """Get all messages received by this owner's Commander."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        q = db.client.table("agent_messages").select("*").eq("to_owner_id", owner_id)
        if unread_only:
            q = q.eq("is_read", False)
        rows = q.order("created_at", desc=True).limit(50).execute()
        return {"messages": rows.data or [], "unread": sum(1 for r in (rows.data or []) if not r.get("is_read"))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/agent-messages/{msg_id}/read")
async def mark_message_read(request: Request, msg_id: str):
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        db.client.table("agent_messages") \
            .update({"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", msg_id) \
            .eq("to_owner_id", owner_id) \
            .execute()
        return {"status": "read"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
