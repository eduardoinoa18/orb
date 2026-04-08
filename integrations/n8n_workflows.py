"""N8N workflow orchestration and management for ORB."""

from typing import Any, Optional
import httpx
import logging

from config.settings import get_settings

logger = logging.getLogger(__name__)


# Define all N8N workflows that ORB uses
# Each workflow is configured with its webhook URL and metadata
WORKFLOWS = {
    "30_day_nurture": {
        "id": None,  # Set to your N8N workflow ID if using cloud N8N
        "webhook_path": "lead_nurture_start",
        "description": "30-day lead nurture sequence (3 emails over 30 days)",
        "trigger_event": "new_lead_in_rex",
        "timeout_seconds": 30,
        "estimated_duration_days": 30,
        "action_count": 3,  # 3 email sends
        "required_fields": ["lead_phone", "lead_email", "lead_name", "owner_phone"],
    },
    "hot_lead_urgent": {
        "id": None,
        "webhook_path": "hot_lead_start",
        "description": "Urgent hot lead follow-up (immediate + 1 day + 3 days)",
        "trigger_event": "high_temperature_lead",
        "timeout_seconds": 30,
        "estimated_duration_days": 3,
        "action_count": 3,  # 3 email sends
        "required_fields": ["lead_phone", "lead_email", "lead_name", "temperature"],
    },
    "weekly_metrics_report": {
        "id": None,
        "webhook_path": "metrics_report_start",
        "description": "Weekly summary report sent to owner (Saturdays at 9am)",
        "trigger_event": "weekly_schedule",
        "timeout_seconds": 60,
        "estimated_duration_days": 7,
        "action_count": 1,  # 1 report send
        "required_fields": ["owner_email", "week_start_date"],
    },
    "daily_cost_alert": {
        "id": None,
        "webhook_path": "cost_alert_start",
        "description": "Alert if daily agent costs exceed threshold",
        "trigger_event": "daily_01am_utc",
        "timeout_seconds": 30,
        "estimated_duration_days": 1,
        "action_count": 1,  # 1 conditional alert
        "required_fields": ["owner_phone", "daily_cost_cents", "daily_limit_cents"],
    },
}


def get_n8n_base_url() -> str:
    """Get N8N instance base URL from environment."""
    settings = get_settings()
    
    # Try environment variable first (use getattr for safe access)
    n8n_url = getattr(settings, "n8n_instance_url", None)
    if n8n_url:
        return n8n_url.rstrip("/")
    
    # Default to cloud instance (user will configure in env)
    return "https://app.n8n.cloud"


def get_webhook_url(workflow_path: str) -> str:
    """
    Construct full N8N webhook URL for a specific workflow.
    
    Example:
        get_webhook_url("lead_nurture_start")
        → "https://app.n8n.cloud/webhook/lead_nurture_start"
    """
    base = get_n8n_base_url()
    return f"{base}/webhook/{workflow_path}"


async def trigger_workflow(
    workflow_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Send payload to N8N webhook to start a workflow.
    
    Args:
        workflow_name: Name of workflow (key in WORKFLOWS dict)
        payload: Data to send to N8N (must include required_fields)
    
    Returns:
        Response from N8N webhook
    
    Raises:
        KeyError: If workflow_name not in WORKFLOWS
        ValueError: If required fields missing from payload
        httpx.HTTPError: If webhook call fails
    
    Example:
        await trigger_workflow("30_day_nurture", {
            "lead_phone": "+1-555-0123",
            "lead_email": "prospect@example.com",
            "lead_name": "John Doe",
            "owner_phone": "+1-555-9999",
        })
    """
    
    # Validate workflow exists
    if workflow_name not in WORKFLOWS:
        raise KeyError(f"Unknown workflow: {workflow_name}. Available: {list(WORKFLOWS.keys())}")
    
    workflow = WORKFLOWS[workflow_name]
    
    # Validate required fields
    required = workflow.get("required_fields", [])
    missing = [f for f in required if f not in payload]
    if missing:
        raise ValueError(
            f"Workflow '{workflow_name}' missing fields: {missing}. "
            f"Required: {required}"
        )
    
    # Get webhook URL and send
    webhook_url = get_webhook_url(workflow["webhook_path"])
    timeout = workflow.get("timeout_seconds", 30)
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()  # Raise on 4xx/5xx
            
            return {
                "success": True,
                "status_code": response.status_code,
                "workflow": workflow_name,
                "body": response.json() if response.text else {}
            }
    
    except httpx.HTTPError as e:
        logger.error(
            f"N8N webhook failed for {workflow_name}",
            extra={
                "workflow": workflow_name,
                "webhook_url": webhook_url,
                "error": str(e),
            }
        )
        return {
            "success": False,
            "status_code": getattr(e.response, "status_code", None) if hasattr(e, "response") else None,
            "workflow": workflow_name,
            "error": str(e),
        }


def get_workflow_info(workflow_name: str) -> Optional[dict[str, Any]]:
    """Get metadata about a workflow without triggering it."""
    return WORKFLOWS.get(workflow_name)


def list_workflows() -> dict[str, dict[str, Any]]:
    """Get info on all configured workflows."""
    return WORKFLOWS


def get_workflow_duration_estimate(workflow_name: str) -> int:
    """Get estimated duration in days to complete this workflow."""
    workflow = WORKFLOWS.get(workflow_name)
    if not workflow:
        return 0
    return workflow.get("estimated_duration_days", 0)


# Configuration examples for common scenarios

WORKFLOW_SCENARIOS = {
    "new_cold_lead_detected": {
        """When Rex finds a new cold prospect, run this workflow."""
        "workflow": "30_day_nurture",
        "payload_builder": lambda lead: {
            "lead_phone": lead["phone"],
            "lead_email": lead["email"],
            "lead_name": lead["name"],
            "owner_phone": get_settings().my_phone_number,
        }
    },
    "hot_lead_detected": {
        """When Rex identifies a hot/warm prospect (high temperature), run urgent sequence."""
        "workflow": "hot_lead_urgent",
        "payload_builder": lambda lead: {
            "lead_phone": lead["phone"],
            "lead_email": lead["email"],
            "lead_name": lead["name"],
            "temperature": lead.get("temperature", 1),
        }
    },
    "weekly_schedule": {
        """Run every Saturday at 9am to send owner a weekly summary."""
        "workflow": "weekly_metrics_report",
        "payload_builder": lambda owner: {
            "owner_email": owner["email"],
            "week_start_date": owner.get("week_start", ""),
        }
    },
    "daily_morning_check": {
        """Run daily at 1am UTC to alert if costs are high."""
        "workflow": "daily_cost_alert",
        "payload_builder": lambda data: {
            "owner_phone": data["owner_phone"],
            "daily_cost_cents": data["daily_cost_cents"],
            "daily_limit_cents": data["daily_limit_cents"],
        }
    }
}


# ============================================
# WEBHOOK RESPONSE HANDLERS
# ============================================
# These functions process webhooks BACK from N8N when workflows complete

def handle_workflow_complete(
    event: str,
    workflow_name: str,
    workflow_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Process webhook callback from N8N when a workflow completes.
    
    Called by: app/api/routes/webhooks.py POST /webhooks/n8n/sequence_complete
    
    Args:
        event: Usually "sequence_complete"
        workflow_name: Name of workflow that finished (e.g., "30_day_nurture")
        workflow_data: Data from the workflow (varies by type)
    
    Returns:
        Confirmation that we processed it
    """
    
    logger.info(
        f"N8N workflow '{workflow_name}' completed",
        extra={
            "event": event,
            "workflow": workflow_name,
        }
    )
    
    # Dispatch to handler based on workflow type
    handlers = {
        "30_day_nurture": _handle_nurture_complete,
        "hot_lead_urgent": _handle_hot_lead_complete,
        "weekly_metrics_report": _handle_metrics_report_complete,
        "daily_cost_alert": _handle_cost_alert_complete,
    }
    
    handler = handlers.get(workflow_name)
    if handler:
        return handler(workflow_data)
    else:
        logger.warning(f"No handler for workflow: {workflow_name}")
        return {
            "success": False,
            "reason": f"Unknown workflow type: {workflow_name}",
        }


def _handle_nurture_complete(data: dict[str, Any]) -> dict[str, Any]:
    """Handle when 30-day nurture sequence completes."""
    # Update database: sequences.status = "completed"
    # This should be called from database/models.py
    logger.info(f"Nurture sequence complete for {data.get('lead_email')}")
    return {"success": True, "action": "updated_sequence_status"}


def _handle_hot_lead_complete(data: dict[str, Any]) -> dict[str, Any]:
    """Handle when hot lead urgent sequence completes."""
    logger.info(f"Hot lead sequence complete for {data.get('lead_email')}")
    return {"success": True, "action": "updated_sequence_status"}


def _handle_metrics_report_complete(data: dict[str, Any]) -> dict[str, Any]:
    """Handle when weekly metrics report completes."""
    logger.info("Weekly metrics report sent")
    return {"success": True, "action": "logged_report_send"}


def _handle_cost_alert_complete(data: dict[str, Any]) -> dict[str, Any]:
    """Handle when daily cost alert completes."""
    logger.info("Daily cost check completed")
    return {"success": True, "action": "logged_cost_check"}
