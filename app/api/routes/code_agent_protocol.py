"""Code Agent Protocol — Bi-directional VS Code / Claude Code Bridge.

Extends the platform_tasks queue with a real-time messaging protocol so the
code agent isn't just a dumb task picker. It can now:

  1. Send progress updates mid-task ("Working on file X, 40% done")
  2. Ask Commander a clarifying question ("Should I use FastAPI or Flask?")
  3. Receive Eduardo's answer and continue
  4. Report blockers ("Can't find the DB schema — can you point me to it?")
  5. Propose partial implementations before full submission
  6. Receive feedback from Eduardo mid-task without rejecting the whole thing

This turns the code agent into a true AI collaborator, not just a task runner.

Endpoints:
  POST   /code-agent/heartbeat              — agent signals it's alive + current task
  POST   /code-agent/tasks/{id}/progress   — post a progress update
  POST   /code-agent/tasks/{id}/question   — agent asks Commander a question
  GET    /code-agent/tasks/{id}/answers    — agent polls for Eduardo's answers
  POST   /code-agent/tasks/{id}/propose    — agent proposes partial implementation
  POST   /code-agent/tasks/{id}/blocker    — agent reports a blocker
  GET    /code-agent/status                — full agent status + current task

Auth: Uses ORB_CODE_AGENT_KEY env var (header: X-Agent-Key or query param agent_key).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.code_agent")

router = APIRouter(prefix="/code-agent", tags=["Code Agent Protocol"])

_AGENT_KEY_ENV = "ORB_CODE_AGENT_KEY"


def _require_agent_key(
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
) -> None:
    """Validates the code agent's shared API key."""
    key = agent_key or x_agent_key
    expected = os.environ.get(_AGENT_KEY_ENV, "")
    if not expected:
        return  # No key configured — allow for development
    if not key or key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing agent key")


def _get_db() -> SupabaseService:
    return SupabaseService()


def _get_admin_id(db: SupabaseService) -> str | None:
    try:
        rows = db.client.table("business_profiles") \
            .select("owner_id") \
            .eq("is_platform_admin", True) \
            .limit(1) \
            .execute()
        return rows.data[0]["owner_id"] if rows.data else None
    except Exception:
        return None


# ── Models ────────────────────────────────────────────────────────────────────

class AgentHeartbeat(BaseModel):
    agent_id: str = "vscode_agent"
    current_task_id: Optional[str] = None
    status: str = "idle"              # idle | working | blocked | waiting_answer
    capabilities: list[str] = []     # ["python", "typescript", "react", "fastapi"]
    version: Optional[str] = None


class ProgressUpdate(BaseModel):
    message: str                     # "Implementing create_task endpoint, 60% done"
    percent_complete: Optional[int] = None   # 0-100
    files_touched: list[str] = []
    next_step: Optional[str] = None


class AgentQuestion(BaseModel):
    question: str
    context: Optional[str] = None    # Why the agent is asking
    options: list[str] = []          # If the agent has suggestions, list them
    blocking: bool = False           # True = agent paused waiting for answer


class PartialProposal(BaseModel):
    description: str                 # What this partial implementation covers
    code_snippet: str                # The actual partial code
    files_affected: list[str] = []
    questions_before_continuing: list[str] = []


class BlockerReport(BaseModel):
    blocker_description: str
    blocker_type: str = "unknown"    # "missing_schema" | "unclear_spec" | "dependency" | "permission" | "other"
    suggested_resolution: Optional[str] = None
    needs_human_action: bool = False


class QuestionAnswer(BaseModel):
    answer: str
    approved_to_continue: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/heartbeat")
async def agent_heartbeat(
    body: AgentHeartbeat,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent signals it's alive and reports its current state.

    Called on startup and periodically to let the platform know the agent
    is running and ready. Eduardo can see this in the Code Tasks dashboard.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        db.client.table("code_agent_status").upsert({
            "agent_id": body.agent_id,
            "status": body.status,
            "current_task_id": body.current_task_id,
            "capabilities": body.capabilities,
            "version": body.version,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="agent_id").execute()
        return {
            "status": "acknowledged",
            "agent_id": body.agent_id,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        # Non-fatal — agent keeps working even if heartbeat fails
        logger.warning("Heartbeat persist failed: %s", e)
        return {"status": "acknowledged", "warning": str(e)}


@router.post("/tasks/{task_id}/progress")
async def post_progress(
    task_id: str,
    body: ProgressUpdate,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent posts a progress update on the current task.

    Eduardo sees this in real-time in the Code Tasks dashboard.
    Progress updates are stored as task_events with type='progress'.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        # Store as task event
        db.client.table("task_events").insert({
            "task_id": task_id,
            "event_type": "progress",
            "message": body.message,
            "payload": {
                "percent_complete": body.percent_complete,
                "files_touched": body.files_touched,
                "next_step": body.next_step,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        # Update task's last_activity
        db.client.table("platform_tasks").update({
            "last_agent_activity": datetime.now(timezone.utc).isoformat(),
            "agent_progress": body.percent_complete,
        }).eq("id", task_id).execute()
        logger.info("Task %s progress: %s (%s%%)", task_id, body.message[:60], body.percent_complete)
        return {"status": "logged", "task_id": task_id}
    except Exception as e:
        logger.warning("Progress update failed for task %s: %s", task_id, e)
        return {"status": "logged", "warning": str(e)}


@router.post("/tasks/{task_id}/question")
async def ask_question(
    task_id: str,
    body: AgentQuestion,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent asks Eduardo a clarifying question about the task.

    If blocking=True, Commander is notified immediately via agent_messages.
    Eduardo can answer directly from his Commander or from the dashboard.
    The agent polls GET /tasks/{id}/answers to pick up the response.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        # Store the question as a task event
        event = db.client.table("task_events").insert({
            "task_id": task_id,
            "event_type": "question",
            "message": body.question,
            "payload": {
                "context": body.context,
                "options": body.options,
                "blocking": body.blocking,
                "answered": False,
                "answer": None,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        question_id = event.data[0]["id"] if event.data else None

        # Notify Eduardo's Commander via agent_messages
        admin_id = _get_admin_id(db)
        if admin_id:
            options_str = ""
            if body.options:
                options_str = "\nOptions:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(body.options))
            db.client.table("agent_messages").insert({
                "from_owner_id": admin_id,
                "to_owner_id": admin_id,
                "from_agent_type": "code_agent",
                "to_agent_type": "commander",
                "message_type": "question",
                "subject": f"🤖 Code Agent Question — Task {task_id[:8]}",
                "body": (
                    f"The code agent needs your input:\n\n{body.question}"
                    + (f"\n\nContext: {body.context}" if body.context else "")
                    + options_str
                    + ("\n\n⚠️ BLOCKING: Agent is paused waiting for your answer." if body.blocking else "")
                ),
                "payload": {
                    "task_id": task_id,
                    "question_id": question_id,
                    "blocking": body.blocking,
                    "options": body.options,
                },
                "thread_id": task_id,
            }).execute()

        if body.blocking:
            db.client.table("platform_tasks").update({
                "status": "waiting_answer",
            }).eq("id", task_id).execute()

        return {
            "status": "question_posted",
            "question_id": question_id,
            "blocking": body.blocking,
            "admin_notified": bool(admin_id),
        }
    except Exception as e:
        logger.error("Failed to post question for task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/answers")
async def get_answers(
    task_id: str,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent polls this to get Eduardo's answers to its questions.

    Returns all answered questions for this task. The agent should mark
    questions as 'consumed' via the payload field to avoid re-processing.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        rows = db.client.table("task_events") \
            .select("*") \
            .eq("task_id", task_id) \
            .eq("event_type", "answer") \
            .order("created_at", desc=True) \
            .limit(20) \
            .execute()
        return {
            "task_id": task_id,
            "answers": rows.data or [],
            "count": len(rows.data or []),
        }
    except Exception as e:
        logger.error("Failed to fetch answers for task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/answer")
async def post_answer(task_id: str, question_id: str, body: QuestionAnswer):
    """Eduardo answers a code agent question (called from Commander tool or dashboard).

    This is NOT restricted to agent key — Eduardo's Commander calls this.
    After answering, the task status returns to 'picked_up' so the agent continues.
    """
    try:
        db = _get_db()
        # Store the answer
        db.client.table("task_events").insert({
            "task_id": task_id,
            "event_type": "answer",
            "message": body.answer,
            "payload": {
                "question_id": question_id,
                "approved_to_continue": body.approved_to_continue,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        # Resume task if it was waiting
        if body.approved_to_continue:
            db.client.table("platform_tasks").update({
                "status": "picked_up",
                "last_agent_activity": datetime.now(timezone.utc).isoformat(),
            }).eq("id", task_id).eq("status", "waiting_answer").execute()

        return {
            "status": "answered",
            "task_id": task_id,
            "question_id": question_id,
            "agent_can_continue": body.approved_to_continue,
        }
    except Exception as e:
        logger.error("Failed to post answer for task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/propose")
async def propose_partial(
    task_id: str,
    body: PartialProposal,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent proposes a partial implementation for Eduardo's quick review.

    Useful for large tasks where the agent wants early feedback before completing
    the full implementation. Eduardo can comment and the agent adjusts course.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        db.client.table("task_events").insert({
            "task_id": task_id,
            "event_type": "partial_proposal",
            "message": body.description,
            "payload": {
                "code_snippet": body.code_snippet[:10000],
                "files_affected": body.files_affected,
                "questions_before_continuing": body.questions_before_continuing,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        admin_id = _get_admin_id(db)
        if admin_id:
            db.client.table("agent_messages").insert({
                "from_owner_id": admin_id,
                "to_owner_id": admin_id,
                "from_agent_type": "code_agent",
                "to_agent_type": "commander",
                "message_type": "partial_proposal",
                "subject": f"📋 Code Agent Partial Proposal — Task {task_id[:8]}",
                "body": (
                    f"The code agent has a partial implementation ready for your review:\n\n"
                    f"{body.description}\n\nFiles affected: {', '.join(body.files_affected)}"
                    + (f"\n\nQuestions: " + "; ".join(body.questions_before_continuing)
                       if body.questions_before_continuing else "")
                ),
                "payload": {"task_id": task_id},
                "thread_id": task_id,
            }).execute()

        return {"status": "proposed", "task_id": task_id, "admin_notified": bool(admin_id)}
    except Exception as e:
        logger.error("Failed to post partial proposal for task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/blocker")
async def report_blocker(
    task_id: str,
    body: BlockerReport,
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Code agent reports a blocker that's preventing task completion.

    Eduardo is notified immediately and the task status is set to 'blocked'.
    """
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        db.client.table("task_events").insert({
            "task_id": task_id,
            "event_type": "blocker",
            "message": body.blocker_description,
            "payload": {
                "blocker_type": body.blocker_type,
                "suggested_resolution": body.suggested_resolution,
                "needs_human_action": body.needs_human_action,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        db.client.table("platform_tasks").update({
            "status": "blocked",
            "last_agent_activity": datetime.now(timezone.utc).isoformat(),
        }).eq("id", task_id).execute()

        admin_id = _get_admin_id(db)
        if admin_id:
            db.client.table("agent_messages").insert({
                "from_owner_id": admin_id,
                "to_owner_id": admin_id,
                "from_agent_type": "code_agent",
                "to_agent_type": "commander",
                "message_type": "blocker",
                "subject": f"🚫 Code Agent Blocked — Task {task_id[:8]}",
                "body": (
                    f"The code agent is blocked on a task:\n\n"
                    f"Type: {body.blocker_type}\n"
                    f"Problem: {body.blocker_description}"
                    + (f"\n\nSuggested fix: {body.suggested_resolution}" if body.suggested_resolution else "")
                    + ("\n\n⚠️ Needs your action to unblock." if body.needs_human_action else "")
                ),
                "payload": {
                    "task_id": task_id,
                    "blocker_type": body.blocker_type,
                    "needs_human_action": body.needs_human_action,
                },
                "thread_id": task_id,
            }).execute()

        return {"status": "blocker_reported", "task_id": task_id, "admin_notified": bool(admin_id)}
    except Exception as e:
        logger.error("Failed to report blocker for task %s: %s", task_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_agent_status(
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Returns the current agent status, active task info, and pending answers."""
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        # Agent heartbeat status
        try:
            status_rows = db.client.table("code_agent_status") \
                .select("*") \
                .order("last_seen", desc=True) \
                .limit(5) \
                .execute()
            agents = status_rows.data or []
        except Exception:
            agents = []

        # Current queue
        queue_rows = db.client.table("platform_tasks") \
            .select("id,title,status,priority,created_at") \
            .in_("status", ["pending", "picked_up", "needs_review", "blocked", "waiting_answer"]) \
            .order("created_at") \
            .limit(10) \
            .execute()

        return {
            "agents": agents,
            "queue": queue_rows.data or [],
            "queue_size": len(queue_rows.data or []),
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/events")
async def get_task_events(
    task_id: str,
    event_type: Optional[str] = Query(None),
    agent_key: Optional[str] = Query(None),
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
):
    """Returns all events for a task (progress, questions, answers, blockers)."""
    _require_agent_key(agent_key, x_agent_key)
    try:
        db = _get_db()
        q = db.client.table("task_events").select("*").eq("task_id", task_id)
        if event_type:
            q = q.eq("event_type", event_type)
        rows = q.order("created_at").limit(100).execute()
        return {"task_id": task_id, "events": rows.data or [], "count": len(rows.data or [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
