"""Zapier webhook client for ORB Platform.

Agents can trigger ANY Zapier workflow by hitting a Zap's webhook URL.
This connects ORB to 6,000+ apps without writing custom integrations.

Common patterns:
  - "New lead captured" → triggers Zap → adds to Google Sheets + sends email
  - "Deal closed" → triggers Zap → notifies team in Teams + creates invoice in QuickBooks
  - "Agent task complete" → triggers Zap → updates CRM + logs to Airtable

Setup: In Zapier, create a Zap with "Webhooks by Zapier" as the trigger.
       Copy the webhook URL and store as ZAPIER_WEBHOOK_URL (default) or
       per-workflow as ZAPIER_WEBHOOK_{NAME} e.g. ZAPIER_WEBHOOK_NEW_LEAD.

Requires:
  ZAPIER_WEBHOOK_URL  — Default webhook URL (optional if using named webhooks)

Docs: https://zapier.com/apps/webhook/integrations
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.zapier")


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_zapier_available() -> bool:
    s = get_settings()
    return bool(s.resolve("zapier_webhook_url", default=""))


def _get_webhook_url(workflow: str | None = None) -> str:
    """Resolve webhook URL — named workflow or default."""
    s = get_settings()
    if workflow:
        # Try ZAPIER_WEBHOOK_{WORKFLOW} first
        key = f"zapier_webhook_{workflow.lower().replace(' ', '_').replace('-', '_')}"
        named = s.resolve(key, default="")
        if named:
            return named
    return s.resolve("zapier_webhook_url", default="")


# ---------------------------------------------------------------------------
# Core trigger
# ---------------------------------------------------------------------------

def trigger(
    event: str,
    data: dict[str, Any],
    workflow: str | None = None,
) -> dict[str, Any]:
    """Fire a Zapier webhook trigger.

    Args:
        event: Short event name for identification e.g. 'new_lead', 'deal_closed'.
        data: Dict of fields to pass to the Zap (will appear as webhook payload).
        workflow: Optional named webhook key (looks up ZAPIER_WEBHOOK_{WORKFLOW}).

    Returns: Response dict from Zapier (usually {"status": "success"}).

    Example:
        trigger("new_lead", {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "source": "follow_up_boss",
            "stage": "New",
        })
    """
    url = _get_webhook_url(workflow)
    if not url:
        raise ValueError(
            "No Zapier webhook URL configured. "
            "Set ZAPIER_WEBHOOK_URL or ZAPIER_WEBHOOK_{WORKFLOW_NAME}."
        )

    payload = {
        "event": event,
        "source": "orb_platform",
        **data,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        try:
            return json.loads(resp.read())
        except Exception:
            return {"status": "sent", "http_status": resp.status}


# ---------------------------------------------------------------------------
# Pre-built event helpers
# ---------------------------------------------------------------------------

def trigger_new_lead(
    name: str,
    email: str,
    phone: str = "",
    source: str = "",
    stage: str = "New",
    notes: str = "",
) -> dict[str, Any]:
    """Fire a 'new_lead' Zapier event."""
    return trigger("new_lead", {
        "name": name,
        "email": email,
        "phone": phone,
        "source": source,
        "stage": stage,
        "notes": notes,
    })


def trigger_deal_closed(
    contact_name: str,
    deal_name: str,
    amount: float,
    contact_email: str = "",
    agent_name: str = "",
) -> dict[str, Any]:
    """Fire a 'deal_closed' Zapier event."""
    return trigger("deal_closed", {
        "contact_name": contact_name,
        "deal_name": deal_name,
        "amount": amount,
        "contact_email": contact_email,
        "agent_name": agent_name,
    })


def trigger_task_completed(
    task_name: str,
    completed_by: str,
    contact_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Fire a 'task_completed' Zapier event."""
    return trigger("task_completed", {
        "task_name": task_name,
        "completed_by": completed_by,
        "contact_name": contact_name,
        "notes": notes,
    })


def trigger_appointment_booked(
    contact_name: str,
    contact_email: str,
    appointment_time: str,
    meeting_type: str = "Consultation",
) -> dict[str, Any]:
    """Fire an 'appointment_booked' Zapier event."""
    return trigger("appointment_booked", {
        "contact_name": contact_name,
        "contact_email": contact_email,
        "appointment_time": appointment_time,
        "meeting_type": meeting_type,
    })


def trigger_agent_alert(
    agent_name: str,
    alert_type: str,
    message: str,
    severity: str = "info",
) -> dict[str, Any]:
    """Fire an agent alert event (errors, warnings, milestones)."""
    return trigger("agent_alert", {
        "agent_name": agent_name,
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
    })


def trigger_custom(workflow: str, data: dict[str, Any]) -> dict[str, Any]:
    """Trigger a named custom Zapier workflow.

    Args:
        workflow: Workflow name matching ZAPIER_WEBHOOK_{WORKFLOW} env var.
        data: Payload fields.
    """
    return trigger(workflow, data, workflow=workflow)


# ---------------------------------------------------------------------------
# Multi-webhook fan-out
# ---------------------------------------------------------------------------

def trigger_all(event: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Fire the same event to ALL configured Zapier webhook URLs.

    Scans for all ZAPIER_WEBHOOK_* environment variables and fires each.
    Useful for broadcasting a single event to multiple Zaps.
    """
    results = []
    webhook_urls: set[str] = set()

    # Collect all ZAPIER_WEBHOOK_* env vars
    for key, val in os.environ.items():
        if key.upper().startswith("ZAPIER_WEBHOOK_") and val.startswith("https://"):
            webhook_urls.add(val)

    if not webhook_urls:
        raise ValueError("No Zapier webhook URLs found. Set ZAPIER_WEBHOOK_* environment variables.")

    payload = json.dumps({"event": event, "source": "orb_platform", **data}).encode()
    for url in webhook_urls:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                try:
                    results.append(json.loads(resp.read()))
                except Exception:
                    results.append({"status": "sent", "url": url[:50]})
        except Exception as e:
            results.append({"status": "error", "url": url[:50], "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by sending a ping event to the default webhook."""
    try:
        result = trigger("ping", {"message": "ORB Platform connection test"})
        return {"success": True, "response": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
