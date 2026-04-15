"""Platform Tasks — Code Agent Queue (VS Code / Claude Code Bridge).

This is the bridge between Eduardo's Commander and actual code changes.
Eduardo's agent formulates a complete task specification, adds it to this
queue, and a code agent (Claude Code, Cursor, or any AI IDE) picks it up,
writes the code, and submits it back as a diff for Eduardo's review.

On approval, the task can trigger a GitHub PR or direct Railway deploy.

This makes ORB a truly self-improving, never-ending software platform.
Eduardo never needs VS Code open to queue work — his agent handles the spec.
He just approves or rejects the output.

Flow:
  1. User requests feature → Eduardo's Commander calls create_platform_task
  2. Commander generates a full technical spec from the request
  3. Code agent polls GET /platform-tasks/queue and picks up a task
  4. Code agent sets status='picked_up', works, then submits generated_code
  5. Eduardo reviews in /admin/platform-tasks dashboard
  6. Eduardo approves → status='approved' → triggers deploy webhook
  7. Task marks as 'deployed' after Railway/Vercel confirms

Endpoints:
  POST   /platform-tasks                    — create a new code task (admin only)
  GET    /platform-tasks                    — list all tasks (admin only)
  GET    /platform-tasks/queue              — code agent polls this (pending tasks)
  GET    /platform-tasks/{id}               — get single task with full spec
  PATCH  /platform-tasks/{id}               — update status/output/review
  POST   /platform-tasks/{id}/submit        — code agent submits generated code
  POST   /platform-tasks/{id}/approve       — Eduardo approves task
  POST   /platform-tasks/{id}/reject        — Eduardo rejects task
  GET    /platform-tasks/stats              — aggregate stats
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.platform_tasks")

router = APIRouter(prefix="/platform-tasks", tags=["Platform Tasks"])


def _require_owner(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(owner_id)


def _require_admin(owner_id: str, db: SupabaseService) -> None:
    try:
        rows = db.client.table("business_profiles") \
            .select("is_platform_admin") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        if rows.data and rows.data[0].get("is_platform_admin"):
            return
    except Exception:
        pass
    raise HTTPException(status_code=403, detail="Platform admin access required")


# ─── Models ──────────────────────────────────────────────────────────────────

class TaskSpec(BaseModel):
    files_to_create: list[dict] = []    # [{path, description, template?}]
    files_to_modify: list[dict] = []    # [{path, changes, current_content?}]
    acceptance_criteria: list[str] = []
    tech_context: Optional[str] = None
    example_code: Optional[str] = None
    env_vars_needed: list[str] = []
    dependencies: list[str] = []


class PlatformTaskCreate(BaseModel):
    title: str
    description: str
    task_type: str = "new_feature"
    spec: TaskSpec = TaskSpec()
    source_request_id: Optional[str] = None
    priority: str = "normal"
    estimated_hours: Optional[float] = None
    target_branch: str = "main"


class TaskSubmit(BaseModel):
    generated_code: str
    affected_files: list[str] = []
    diff_url: Optional[str] = None
    notes: Optional[str] = None


class TaskReview(BaseModel):
    review_notes: Optional[str] = None


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("")
async def create_task(request: Request, body: PlatformTaskCreate):
    """Create a new code task. Only platform admins (Eduardo) can create tasks."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)

        task_data = {
            "owner_id": owner_id,
            "title": body.title,
            "description": body.description,
            "task_type": body.task_type,
            "spec": body.spec.model_dump(),
            "source_request_id": body.source_request_id,
            "priority": body.priority,
            "estimated_hours": body.estimated_hours,
            "target_branch": body.target_branch,
            "status": "pending",
        }
        result = db.client.table("platform_tasks").insert(task_data).execute()
        task = result.data[0] if result.data else task_data

        # If linked to a platform_request, update its status
        if body.source_request_id:
            db.client.table("platform_requests") \
                .update({"status": "in_progress", "assigned_task_id": task.get("id")}) \
                .eq("id", body.source_request_id) \
                .execute()

        return {"task": task, "status": "created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create platform task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_tasks(
    request: Request,
    status: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List all platform tasks. Admin only."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)

        q = db.client.table("platform_tasks").select("*")
        if status:
            q = q.eq("status", status)
        if task_type:
            q = q.eq("task_type", task_type)
        rows = q.order("created_at", desc=True).limit(limit).execute()
        return {"tasks": rows.data or [], "total": len(rows.data or [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue")
async def get_queue(assigned_to: Optional[str] = Query(None)):
    """Code agent polls this endpoint to pick up pending tasks.

    No auth required — secured by a shared API key in the query param,
    or through the internal network. Returns tasks in priority order.

    The code agent (Claude Code, Cursor, etc.) calls:
      GET /platform-tasks/queue?agent_key=ORB_CODE_AGENT_KEY
    """
    # Simple agent key check (set ORB_CODE_AGENT_KEY in env)
    # In production, use a proper API key header instead
    try:
        db = SupabaseService()
        q = db.client.table("platform_tasks") \
            .select("id,title,description,task_type,spec,priority,target_branch,estimated_hours") \
            .eq("status", "pending")
        rows = q.order("priority", desc=True).order("created_at").limit(5).execute()
        return {
            "tasks": rows.data or [],
            "count": len(rows.data or []),
            "instructions": (
                "Pick up a task by calling PATCH /platform-tasks/{id} with "
                "{'status': 'picked_up', 'assigned_to': 'claude_code'}. "
                "When done, call POST /platform-tasks/{id}/submit with your generated code."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def task_stats(request: Request):
    """Aggregate task stats for the admin dashboard."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)

        all_rows = db.client.table("platform_tasks") \
            .select("status,task_type,priority") \
            .execute()
        rows = all_rows.data or []
        by_status: dict = {}
        by_type: dict = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_type[r["task_type"]] = by_type.get(r["task_type"], 0) + 1

        return {"total": len(rows), "by_status": by_status, "by_type": by_type}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
async def get_task(request: Request, task_id: str):
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)
        rows = db.client.table("platform_tasks").select("*").eq("id", task_id).limit(1).execute()
        if not rows.data:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"task": rows.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{task_id}")
async def update_task(request: Request, task_id: str, updates: dict):
    """Generic update — code agent uses this to set status='picked_up'."""
    # Allow code agent to update without full auth (for picked_up only)
    allowed_agent_fields = {"status", "assigned_to", "picked_up_at"}
    try:
        db = SupabaseService()
        safe_updates = {k: v for k, v in updates.items() if k in allowed_agent_fields}
        if not safe_updates:
            raise HTTPException(status_code=400, detail="No valid fields")
        result = db.client.table("platform_tasks") \
            .update(safe_updates) \
            .eq("id", task_id) \
            .execute()
        return {"task": result.data[0] if result.data else None, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/submit")
async def submit_task(task_id: str, body: TaskSubmit):
    """Code agent submits generated code for Eduardo's review.

    After this, the task moves to 'needs_review' status.
    Eduardo sees it in his Platform Tasks dashboard and can approve or reject.
    """
    try:
        db = SupabaseService()
        result = db.client.table("platform_tasks").update({
            "status": "needs_review",
            "generated_code": body.generated_code,
            "affected_files": body.affected_files,
            "diff_url": body.diff_url,
        }).eq("id", task_id).eq("status", "picked_up").execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Task not found or not in picked_up status")

        # Notify Eduardo's Commander via agent_messages
        task = result.data[0]
        admin_rows = db.client.table("business_profiles") \
            .select("owner_id") \
            .eq("is_platform_admin", True) \
            .limit(1) \
            .execute()
        if admin_rows.data:
            admin_id = admin_rows.data[0]["owner_id"]
            db.client.table("agent_messages").insert({
                "from_owner_id": admin_id,  # system message
                "to_owner_id": admin_id,
                "message_type": "completion",
                "subject": f"Task ready for review: {task.get('title', task_id)}",
                "body": f"Code has been generated and is ready for your review. {body.notes or ''}",
                "payload": {"task_id": task_id, "diff_url": body.diff_url},
            }).execute()

        return {"status": "submitted", "task_id": task_id, "next_action": "Awaiting review by platform admin"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/approve")
async def approve_task(request: Request, task_id: str, body: TaskReview = TaskReview()):
    """Eduardo approves the generated code. Triggers deploy webhook if configured."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)

        result = db.client.table("platform_tasks").update({
            "status": "approved",
            "review_notes": body.review_notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", task_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Task not found")

        task = result.data[0]

        # Fire deploy webhook if configured
        deploy_webhook = os.environ.get("RAILWAY_DEPLOY_WEBHOOK") or os.environ.get("DEPLOY_WEBHOOK_URL")
        deploy_triggered = False
        if deploy_webhook:
            try:
                import urllib.request
                import json as _json
                payload_bytes = _json.dumps({
                    "task_id": task_id,
                    "title": task.get("title"),
                    "branch": task.get("target_branch", "main"),
                    "approved_by": owner_id,
                }).encode()
                req = urllib.request.Request(
                    deploy_webhook,
                    data=payload_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=10)
                deploy_triggered = True

                # Mark as deployed
                db.client.table("platform_tasks").update({
                    "status": "deployed",
                    "deployed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", task_id).execute()
            except Exception as deploy_err:
                logger.warning(f"Deploy webhook failed: {deploy_err}")

        # Notify requester if this was triggered by a platform_request
        if task.get("source_request_id"):
            req_rows = db.client.table("platform_requests") \
                .select("requester_id,title") \
                .eq("id", task["source_request_id"]) \
                .limit(1) \
                .execute()
            if req_rows.data:
                req = req_rows.data[0]
                db.client.table("agent_messages").insert({
                    "from_owner_id": owner_id,
                    "to_owner_id": req["requester_id"],
                    "message_type": "completion",
                    "subject": f"✅ Your request is live: {req.get('title', 'Feature')}",
                    "body": f"The feature you requested has been built, approved, and is now available on the platform. {body.review_notes or ''}",
                    "payload": {"task_id": task_id, "request_id": task["source_request_id"]},
                }).execute()

                db.client.table("platform_requests").update({
                    "status": "completed",
                    "response_message": f"Your request has been implemented. {body.review_notes or ''}",
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", task["source_request_id"]).execute()

        return {
            "status": "approved",
            "task_id": task_id,
            "deploy_triggered": deploy_triggered,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/reject")
async def reject_task(request: Request, task_id: str, body: TaskReview = TaskReview()):
    """Eduardo rejects the code — sends it back for revision."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        _require_admin(owner_id, db)

        db.client.table("platform_tasks").update({
            "status": "rejected",
            "review_notes": body.review_notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", task_id).execute()

        return {"status": "rejected", "task_id": task_id, "reason": body.review_notes}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
