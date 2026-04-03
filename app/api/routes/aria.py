"""Aria routes — executive assistant API endpoints.

Handles task management, briefing preview, and scheduling.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agents.aria.briefing_engine import AriaBriefingEngine
from agents.aria.aria_brain import AriaBrain
from agents.aria.task_manager import AriaTaskManager
import integrations.google_client as google_client


router = APIRouter(prefix="/aria", tags=["aria"])

briefing = AriaBriefingEngine()
tasks_mgr = AriaTaskManager()
aria_brain = AriaBrain()


# ─── Request/Response Models ────────────────────────────────────


class TaskCreate(BaseModel):
    """Task creation request."""
    title: str
    description: Optional[str] = None
    priority: str = "normal"  # high, normal, low
    due_at: Optional[str] = None
    related_lead_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """Task update request."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_at: Optional[str] = None


class BriefingSendNowRequest(BaseModel):
    """Optional override destination for manual briefing tests."""
    to_number: Optional[str] = None


class AriaLearnRequest(BaseModel):
    """Owner context for Aria weekly learning."""
    owner_id: str


class GoogleConnectRequest(BaseModel):
    """Auth code returned by Google after owner approves access."""
    code: str


# ─── Briefing Endpoints ────────────────────────────────────────


@router.get("/briefing/preview")
def get_briefing_preview():
    """
    Get preview of what the daily briefing will say.
    Does NOT send SMS — just shows the text.
    """
    try:
        preview = briefing.get_briefing_preview()
        return {
            "status": "preview_ready",
            "briefing_text": preview,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/briefing/send-now")
def send_briefing_now(payload: BriefingSendNowRequest | None = None):
    """
    Manually trigger the daily briefing.
    Pulls all data and sends SMS immediately.
    """
    try:
        result = briefing.generate_and_send_briefing(
            to_number=payload.to_number if payload else None,
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=503,
                detail=result.get("send_error") or "Failed to send briefing SMS"
            )
        
        return {
            "status": "briefing_sent",
            "sent_to": result.get("sent_to"),
            "preview": result["briefing_text"],
            "tasks_included": result["tasks_included"],
            "trading_summary": result["trading_summary"],
            "leads_summary": result["leads_summary"],
            "daily_cost": result["daily_cost"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Task Endpoints ────────────────────────────────────────────


@router.post("/tasks")
def create_task(payload: TaskCreate):
    """
    Create a new task for today.
    Used in dashboard to set priorities.
    """
    result = tasks_mgr.create_task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        related_lead_id=payload.related_lead_id,
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    
    return result


@router.get("/tasks")
def list_tasks(status: Optional[str] = None, priority: Optional[str] = None):
    """
    List all tasks with optional filters.
    Filters: status (pending, completed), priority (high, normal, low)
    """
    items = tasks_mgr.get_tasks(status=status, priority=priority)
    return {
        "status": "ok",
        "tasks": items,
        "count": len(items),
    }


@router.get("/tasks/by-priority")
def list_tasks_by_priority():
    """
    Get all pending tasks organized by priority.
    Useful for dashboard display.
    """
    organized = tasks_mgr.get_tasks_by_priority()
    return {
        "status": "ok",
        "by_priority": organized,
        "total": sum(len(tasks) for tasks in organized.values()),
    }


@router.put("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate):
    """Update a specific task."""
    result = tasks_mgr.update_task(
        task_id=task_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        due_at=payload.due_at,
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    
    return result


@router.put("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    """Mark a task as completed."""
    result = tasks_mgr.complete_task(task_id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    
    return {"status": "task_completed", "task_id": task_id}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task."""
    result = tasks_mgr.delete_task(task_id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    
    return {"status": "task_deleted", "task_id": task_id}


# ─── Briefing Summary Endpoint ────────────────────────────────


@router.get("/briefing/summary")
def get_briefing_summary():
    """
    Get the components that make up today's briefing.
    Useful for dashboard display.
    """
    try:
        tasks = briefing.get_todays_tasks()
        trading = briefing.get_trading_summary()
        leads = briefing.get_leads_summary()
        cost = briefing.get_daily_cost()
        
        return {
            "status": "ready",
            "tasks": {
                "pending": tasks,
                "count": len(tasks),
            },
            "trading": trading,
            "leads": leads,
            "daily_cost_dollars": cost,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn-outcomes")
def learn_outcomes(payload: AriaLearnRequest):
    """Runs Aria weekly self-improvement review."""
    try:
        return aria_brain.learn_from_outcomes(owner_id=payload.owner_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn-owner-style")
def learn_owner_style(payload: AriaLearnRequest):
    """Adapts Aria communication style to owner preference patterns."""
    try:
        return aria_brain.learn_owner_style(owner_id=payload.owner_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Google OAuth Endpoints ────────────────────────────────────


@router.get("/google/status")
def google_auth_status():
    """
    Check whether Aria is connected to Google (Gmail + Calendar).
    Returns authorized=True if a valid token file exists on disk.
    """
    authorized = google_client.is_authorized()
    return {
        "authorized": authorized,
        "scopes": google_client.SCOPES if authorized else [],
        "message": (
            "Connected to Google. Email and Calendar data will appear in briefings."
            if authorized
            else "Not connected. Visit /aria/google/authorize to set up Gmail + Calendar."
        ),
    }


@router.get("/google/authorize")
def google_authorize():
    """
    Generate the Google OAuth2 authorization URL.

    Owner opens this URL in a browser, signs in with their Google account,
    approves Gmail + Calendar access, and is redirected with a code parameter.
    Then POST /aria/google/connect with that code to complete the connection.
    """
    try:
        auth_url = google_client.get_auth_url()
        return {
            "auth_url": auth_url,
            "instructions": (
                "1. Open the auth_url in your browser.\n"
                "2. Sign in with the Gmail account Aria should use.\n"
                "3. Click 'Allow'.\n"
                "4. Copy the 'code' value from the redirect URL.\n"
                "5. POST {'code': '<paste here>'} to /aria/google/connect"
            ),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not build auth URL: {exc}. "
                "Check that GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and "
                "GOOGLE_REDIRECT_URI are set in your .env file."
            ),
        )


@router.post("/google/connect")
def google_connect(payload: GoogleConnectRequest):
    """
    Exchange an authorization code for Google credentials and save them.
    After this call succeeds, Aria's morning briefings will include Gmail + Calendar.

    Body: {"code": "<code from Google redirect URL>"}
    """
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="code must not be empty")

    result = google_client.exchange_code(payload.code.strip())

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=f"Google authorization failed: {result.get('error', 'unknown error')}",
        )

    return {
        "status": "connected",
        "email": result.get("email", ""),
        "message": "Google connected! Aria will now include Gmail and Calendar in your morning briefings.",
    }


@router.delete("/google/disconnect")
def google_disconnect():
    """
    Remove stored Google credentials.
    Aria will stop reading Gmail and Calendar until re-authorized.
    """
    token_path = google_client.TOKEN_PATH
    if token_path.exists():
        token_path.unlink()
        return {"status": "disconnected", "message": "Google credentials removed."}
    return {"status": "not_connected", "message": "No Google credentials were stored."}
