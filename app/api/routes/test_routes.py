"""Level 2 test endpoints for ORB.

These routes let you manually verify that each external integration is wired
up correctly before building the agents that depend on them.

IMPORTANT: These endpoints are intentionally unprotected during development
so you can hit them easily with a browser or curl. Remove or protect them
before going to production (Level 9).

Test endpoints:
  POST /test/claude     — asks Claude a question, returns the answer
  POST /test/sms        — sends a test SMS to your own phone number
  POST /test/database   — writes a test row to activity_log and reads it back
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger("orb.test_routes")

router = APIRouter(prefix="/test", tags=["test — Level 2"])


# ── Request body models ────────────────────────────────────────────────────────

class ClaudeTestRequest(BaseModel):
    """Body for POST /test/claude"""
    prompt: str = "What is ORB? Give a one-sentence answer about an AI agent platform."


class SmsTestRequest(BaseModel):
    """Body for POST /test/sms — send to YOUR phone number to verify it works."""
    to: str
    message: str = "ORB test message — your Twilio integration is working correctly."


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/claude")
def test_claude(body: ClaudeTestRequest) -> dict[str, Any]:
    """
    Asks Claude a question and returns the full response.

    How to use: POST /test/claude with JSON body {"prompt": "your question here"}
    This confirms your ANTHROPIC_API_KEY is valid and Claude is reachable.
    """
    from integrations.anthropic_client import ask_claude

    try:
        result = ask_claude(
            prompt=body.prompt,
            system="You are a helpful assistant for the ORB AI agent platform.",
        )
        return {
            "success": True,
            "prompt": body.prompt,
            "response": result["text"],
            "model": result["model"],
            "tokens_used": result["input_tokens"] + result["output_tokens"],
            "cost_cents": result["cost_cents"],
        }
    except RuntimeError as error:
        # API key not configured yet
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("Claude test failed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Claude API error: {error}",
        ) from error


@router.post("/sms")
def test_sms(body: SmsTestRequest) -> dict[str, Any]:
    """
    Sends a test SMS to a phone number you specify.

    How to use: POST /test/sms with JSON body {"to": "+12125551234"}
    Replace with your own phone number. This confirms Twilio is working.

    WARNING: This sends a real SMS. Twilio charges ~1 cent per message.
    """
    from integrations.twilio_client import send_sms

    try:
        result = send_sms(to=body.to, message=body.message)
        return {
            "success": True,
            "sid": result["sid"],
            "status": result["status"],
            "to": result["to"],
            "from": result["from_number"],
            "message": result["body"],
            "cost_cents": result["cost_cents"],
        }
    except RuntimeError as error:
        # Twilio credentials not configured yet
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("SMS test failed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Twilio API error: {error}",
        ) from error


@router.post("/database")
def test_database(request: Request) -> dict[str, Any]:
    """
    Writes a test row to the activity_log table and reads it back.

    How to use: POST /test/database (no body needed)
    This confirms your SUPABASE_URL and SUPABASE_SERVICE_KEY are valid AND
    that you have run the schema.sql file in your Supabase project.

    Expected response: shows "write" and "read" both succeed with the same row.
    """
    from app.database.activity_log import get_recent_activity, log_activity

    request_id: str | None = getattr(request.state, "request_id", None)

    try:
        # Step 1 — write a test row
        written = log_activity(
            agent_id=None,
            action_type="test",
            description="Level 2 database connectivity test",
            outcome="test_write",
            cost_cents=0,
            request_id=request_id,
        )

        # Check if the write failed silently (database not connected yet)
        if written.get("id") is None:
            return {
                "success": False,
                "stage": "write",
                "detail": (
                    "Database write returned no ID. "
                    "Check that SUPABASE_URL and SUPABASE_SERVICE_KEY are set "
                    "and that you have run schema.sql in your Supabase project."
                ),
            }

        # Step 2 — read it back to confirm persistence
        recent = get_recent_activity(limit=5)
        test_rows = [r for r in recent if r.get("action_type") == "test"]

        return {
            "success": True,
            "write_result": {
                "id": written.get("id"),
                "action_type": written.get("action_type"),
                "created_at": written.get("created_at"),
            },
            "read_result": {
                "total_rows_found": len(test_rows),
                "most_recent": test_rows[0] if test_rows else None,
            },
        }

    except Exception as error:
        logger.exception("Database test failed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Database error: {error}. "
                "Make sure SUPABASE_URL and SUPABASE_SERVICE_KEY are set in .env "
                "and that you have run schema.sql in your Supabase project."
            ),
        ) from error
