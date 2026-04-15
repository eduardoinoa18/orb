"""Pipeline Monitor Routes — CRM Visibility Enhancements for Real Estate Agents.

Endpoints for:
- Get enhanced pipeline view with lead source breakdown, engagement metrics
- Get pipeline alerts (dormant leads, unassigned, high-value opportunities)
- Submit Pipeline Monitor proposal to Approval Tab
- Monitor FUB integration health

This is a Level 8+ feature that extends Commander's basic pipeline metrics
with deep CRM insights for better deal flow management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database.connection import DatabaseConnectionError, SupabaseService

logger = logging.getLogger("orb.api.pipeline_monitor")

router = APIRouter(prefix="/pipeline-monitor", tags=["Pipeline Monitor"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class EnhancedPipelineViewResponse(BaseModel):
    """Enhanced pipeline metrics with source breakdown and engagement data."""
    counts: dict[str, int]  # total, hot, qualified, unassigned, dormant_7d
    sources: dict[str, int]  # source -> count (Zillow, Google, etc.)
    stages: dict[str, dict[str, Any]]  # stage -> {count, avg_days_since_contact, total_deal_value}
    engagement: dict[str, Any]  # avg_days_since_contact, dormant_count, needs_attention
    deals: dict[str, Any]  # total_value, count, avg_deal
    unassigned_leads: list[dict[str, Any]]
    dormant_leads: list[dict[str, Any]]
    next_hot_lead: dict[str, Any] | None


class PipelineAlert(BaseModel):
    """Alert about pipeline issues or opportunities."""
    type: str  # dormant_leads, unassigned_leads, hot_leads_unassigned, deals_at_risk
    severity: str  # critical, high, medium
    message: str
    suggested_action: str
    affected_count: int
    leads: list[dict[str, Any]] | None = None


class PipelineMonitorProposal(BaseModel):
    """Proposal for activating Pipeline Monitor feature."""
    title: str = "Pipeline Monitor: Deep CRM Visibility"
    description: str
    benefits: list[str]
    implementation_steps: list[str]
    data_requirements: list[str]
    approval_type: str = "feature_activation"


# ---------------------------------------------------------------------------
# Helper: Get owner_id from request auth
# ---------------------------------------------------------------------------

def _get_owner_id(request: Request) -> str:
    """Extract owner_id from JWT token payload."""
    payload = getattr(request.state, "token_payload", {})
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing owner_id")
    return str(owner_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
def pipeline_monitor_status() -> dict[str, str]:
    """Health check for Pipeline Monitor routes."""
    return {"status": "pipeline monitor router ready"}


@router.get("/view")
def get_enhanced_pipeline(request: Request) -> EnhancedPipelineViewResponse:
    """Get comprehensive pipeline view with deep CRM metrics.
    
    Returns:
    - Counts: total leads, hot leads, qualified, unassigned, dormant (7+ days)
    - Sources: breakdown by lead source (Zillow, Google, referral, etc.)
    - Stages: deal progression with engagement and value metrics
    - Engagement: average days since last contact, dormant count
    - Deals: total value, count, average deal size
    - Unassigned leads: list of leads without assigned agents
    - Dormant leads: leads inactive for 7+ days
    - Next hot lead: highest temperature unassigned lead
    """
    try:
        owner_id = _get_owner_id(request)
        from agents.nova.pipeline_monitor import get_enhanced_pipeline_view
        
        view_data = get_enhanced_pipeline_view(owner_id)
        return EnhancedPipelineViewResponse(**view_data)
    except ImportError as e:
        logger.error("Pipeline monitor module not found: %s", e)
        raise HTTPException(status_code=503, detail="Pipeline Monitor not available") from e
    except Exception as e:
        logger.error("Failed to fetch enhanced pipeline view: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/alerts")
def get_pipeline_alerts(
    request: Request,
    days_dormant: int = 3,
) -> dict[str, Any]:
    """Get actionable alerts about pipeline issues.
    
    Query params:
    - days_dormant: threshold for marking lead as dormant (default: 3 days)
    
    Returns list of alerts with:
    - type: dormant_leads, unassigned_leads, hot_leads_unassigned, deals_at_risk
    - severity: critical, high, medium
    - message: human-readable description
    - suggested_action: recommended next step
    - affected_count: number of leads involved
    """
    try:
        owner_id = _get_owner_id(request)
        from agents.nova.pipeline_monitor import get_pipeline_alerts
        
        alerts = get_pipeline_alerts(owner_id, days_dormant=days_dormant)
        return {
            "owner_id": owner_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_count": len(alerts),
            "alerts": alerts,
        }
    except ImportError as e:
        logger.error("Pipeline monitor module not found: %s", e)
        raise HTTPException(status_code=503, detail="Pipeline Monitor not available") from e
    except Exception as e:
        logger.error("Failed to fetch pipeline alerts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposal/submit")
def submit_pipeline_monitor_proposal(
    request: Request,
    payload: PipelineMonitorProposal,
) -> dict[str, Any]:
    """Submit Pipeline Monitor activation as an approval proposal.
    
    Creates an activity_log entry with needs_approval=true that will appear
    on the owner's Approval Tab. Includes full details about the feature,
    benefits, implementation steps, and data requirements.
    
    Returns:
    - proposal_id: activity_log id for tracking
    - status: pending_approval
    - next_steps: instructions for approving via dashboard
    """
    try:
        owner_id = _get_owner_id(request)
        db = SupabaseService()
        
        # Create activity_log entry as approval request
        proposal_row = db.insert_one(
            "activity_log",
            {
                "owner_id": owner_id,
                "agent_id": None,
                "action_type": "feature_proposal",
                "description": f"Pipeline Monitor Proposal: {payload.title}",
                "outcome": "pending_approval",
                "needs_approval": True,
                "cost_cents": 0,
                "metadata": {
                    "proposal_type": "pipeline_monitor",
                    "title": payload.title,
                    "description": payload.description,
                    "benefits": payload.benefits,
                    "implementation_steps": payload.implementation_steps,
                    "data_requirements": payload.data_requirements,
                    "submission_time": datetime.now(timezone.utc).isoformat(),
                },
            }
        )
        proposal_id = proposal_row.get("id")
        
        logger.info("Pipeline Monitor proposal submitted (ID: %s, owner: %s)", proposal_id, owner_id)
        
        return {
            "proposal_id": proposal_id,
            "status": "pending_approval",
            "owner_id": owner_id,
            "title": payload.title,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "next_steps": [
                "Review proposal details on your Approval Tab",
                "Approve to enable Pipeline Monitor features",
                "Once approved, enhanced metrics will appear in Commander briefings",
            ],
        }
    except DatabaseConnectionError as e:
        logger.error("Database error submitting proposal: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable") from e
    except Exception as e:
        logger.error("Failed to submit pipeline monitor proposal: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/fub-health")
def check_fub_integration_health() -> dict[str, Any]:
    """Check health and configuration of Follow Up Boss integration.
    
    Returns:
    - connected: true if API key is configured and responding
    - message: status message
    - last_tested_at: ISO timestamp
    - recommended_actions: list of next steps if issues found
    """
    try:
        from integrations.followupboss_client import test_connection
        
        success, message = test_connection()
        
        return {
            "integration": "followupboss",
            "connected": success,
            "message": message,
            "last_tested_at": datetime.now(timezone.utc).isoformat(),
            "recommended_actions": [] if success else [
                "Check FOLLOWUPBOSS_API_KEY configuration in Railway env vars",
                "Visit https://app.followupboss.com/settings/api-keys to verify API key",
                "Test connection via /integrations/test endpoint",
            ],
        }
    except Exception as e:
        logger.error("Failed to check FUB integration health: %s", e)
        return {
            "integration": "followupboss",
            "connected": False,
            "message": f"Health check failed: {str(e)}",
            "last_tested_at": datetime.now(timezone.utc).isoformat(),
            "recommended_actions": [
                "Verify FOLLOWUPBOSS_API_KEY is set in environment",
                "Check platform logs for connection errors",
            ],
        }
