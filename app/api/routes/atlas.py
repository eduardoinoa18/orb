"""Atlas developer agent API routes — Module 1.

Endpoints:
    POST /agents/atlas/generate      — Generate code for a feature
    POST /agents/atlas/diagnose      — Diagnose an error and propose a fix
    POST /agents/atlas/advise        — Architecture advice before coding
    POST /agents/atlas/security-scan — OWASP vulnerability scan on a code snippet
    GET  /agents/atlas/status        — Health check
    GET  /agents/atlas/build-history — Recent Atlas activity log
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("orb.atlas.routes")

router = APIRouter(prefix="/agents/atlas", tags=["atlas"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class GenerateFeatureRequest(BaseModel):
    feature_description: str = Field(..., min_length=10, max_length=2000)
    owner_id: str = Field(..., min_length=1, max_length=200)
    context_files: list[str] = Field(default_factory=list, max_length=5)


class DiagnoseErrorRequest(BaseModel):
    error_message: str = Field(..., min_length=1, max_length=2000)
    stack_trace: str = Field(default="", max_length=5000)
    context: str = Field(default="", max_length=1000)
    agent_id: str = Field(default="", max_length=100)


class AdviseFeatureRequest(BaseModel):
    feature_request: str = Field(..., min_length=10, max_length=2000)
    owner_id: str = Field(..., min_length=1, max_length=200)


class SecurityScanRequest(BaseModel):
    code_snippet: str = Field(..., min_length=10, max_length=20000)
    file_path: str = Field(default="", max_length=300)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
def atlas_status() -> dict[str, str]:
    """Atlas is online and ready."""
    return {
        "status": "online",
        "agent": "Atlas",
        "role": "Senior Developer Agent",
        "capabilities": "generate_feature, diagnose_error, advise_on_feature, security_scan",
    }


@router.post("/generate")
def generate_feature(payload: GenerateFeatureRequest) -> dict[str, Any]:
    """Generate production Python code for a described feature.

    Atlas uses Claude Sonnet with your context files to produce:
    - Complete implementation code
    - Plain-English explanation
    - Matching pytest tests
    """
    try:
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain()
        return brain.generate_feature(
            feature_description=payload.feature_description,
            owner_id=payload.owner_id,
            context_files=payload.context_files,
        )
    except Exception as exc:
        logger.error("Atlas /generate error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Atlas code generation failed: {exc}") from exc


@router.post("/diagnose")
def diagnose_error(payload: DiagnoseErrorRequest) -> dict[str, Any]:
    """Diagnose a Python error and return a concrete fix suggestion.

    Pass the error message and stack trace. Atlas will identify the root
    cause and tell you exactly what to change.
    """
    try:
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain()
        return brain.diagnose_error(
            error_message=payload.error_message,
            stack_trace=payload.stack_trace,
            context=payload.context,
            agent_id=payload.agent_id,
        )
    except Exception as exc:
        logger.error("Atlas /diagnose error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Atlas diagnosis failed: {exc}") from exc


@router.post("/advise")
def advise_on_feature(payload: AdviseFeatureRequest) -> dict[str, Any]:
    """Get architecture advice before you start building a feature.

    Atlas uses Claude Opus to reason about design trade-offs, risks,
    effort estimate, and the best implementation approach.
    """
    try:
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain()
        return brain.advise_on_feature(
            feature_request=payload.feature_request,
            owner_id=payload.owner_id,
        )
    except Exception as exc:
        logger.error("Atlas /advise error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Atlas advice failed: {exc}") from exc


@router.post("/security-scan")
def security_scan(payload: SecurityScanRequest) -> dict[str, Any]:
    """Scan a code snippet for OWASP Top 10 vulnerabilities.

    Atlas reviews the code for injection, broken auth, sensitive data
    exposure, and other common security flaws.
    """
    try:
        from agents.atlas.atlas_brain import AtlasBrain
        brain = AtlasBrain()
        return brain.security_scan(
            code_snippet=payload.code_snippet,
            file_path=payload.file_path,
        )
    except Exception as exc:
        logger.error("Atlas /security-scan error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Atlas security scan failed: {exc}") from exc


@router.get("/build-history")
def build_history() -> dict[str, Any]:
    """Return the last 20 Atlas actions from the activity log."""
    try:
        from app.database.connection import SupabaseService
        db = SupabaseService()
        result = (
            db.client.table("agent_activity")
            .select("*")
            .eq("agent_id", "atlas")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return {"history": result.data or [], "count": len(result.data or [])}
    except Exception as exc:
        logger.warning("Atlas /build-history DB unavailable: %s", exc)
        return {"history": [], "count": 0, "note": "Database unavailable"}
