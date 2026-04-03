"""Webhook routes for ORB."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import stripe
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from twilio.request_validator import RequestValidator

from agents.identity.provisioner import deprovision_agent, provision_agent
from agents.trading.market_monitor import analyze_setup
from agents.trading.risk_manager import check_can_trade
from agents.trading.strategy_loader import load_strategy
from agents.trading.trade_executor import handle_trade_reply, request_trade_approval
from app.api.routes.commander import process_mobile_command
from app.database.activity_log import log_activity
from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings
from integrations.email_commander import handle_incoming_email_message
from integrations.n8n_workflows import handle_workflow_complete
from integrations.tradingview_webhook import parse_tradingview_payload, validate_tradingview_secret
from integrations.twilio_client import send_sms
from integrations.whatsapp_commander import handle_incoming_whatsapp_message

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PLAN_AGENT_BLUEPRINTS: dict[str, list[tuple[str, str]]] = {
    "starter": [("Commander", "commander")],
    "professional": [("Commander", "commander"), ("Rex", "sales"), ("Aria", "assistant")],
    "full_team": [
        ("Commander", "commander"),
        ("Rex", "sales"),
        ("Aria", "assistant"),
        ("Nova", "marketing"),
        ("Orion", "research"),
        ("Sage", "platform"),
        ("Atlas", "developer"),
    ],
}


def _is_valid_twilio_request(request_url: str, form_data: dict[str, str], signature: str | None) -> bool:
    """Validates Twilio webhook signatures to block spoofed inbound requests."""
    if signature is None or not signature.strip():
        return False

    try:
        auth_token = get_settings().require("twilio_auth_token")
    except Exception:
        return False

    validator = RequestValidator(auth_token)
    return validator.validate(request_url, form_data, signature)


def _normalize_channel_number(raw: str) -> str:
    value = str(raw or "").strip()
    if value.lower().startswith("whatsapp:"):
        return value.split(":", 1)[1]
    return value


class N8nErrorPayload(BaseModel):
    """Payload emitted by N8N when a workflow fails."""

    workflow_name: str = Field(default="unknown_workflow")
    workflow_id: str | None = None
    execution_id: str | None = None
    error_message: str = Field(default="No error message provided")
    node_name: str | None = None
    severity: str = Field(default="high")
    occurred_at: str | None = None
    source: str = Field(default="n8n")


class N8nCompletePayload(BaseModel):
    """Payload emitted by N8N when a workflow completes successfully."""

    event: str = Field(default="sequence_complete")
    workflow_name: str
    execution_id: str | None = None
    workflow_data: dict = Field(default_factory=dict)
    completed_at: str | None = None
    source: str = Field(default="n8n")


class InboundEmailPayload(BaseModel):
    """Normalized payload for inbound email command webhooks."""

    from_email: str = Field(min_length=3)
    subject: str = Field(default="")
    text: str = Field(default="")
    provider: str = Field(default="generic")


def _get_db() -> SupabaseService | None:
    try:
        return SupabaseService()
    except DatabaseConnectionError:
        return None


def _update_owner_billing(owner_id: str, updates: dict[str, object]) -> None:
    db = _get_db()
    if not db:
        return
    updates = {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        db.update_many("owners", {"id": owner_id}, updates)
    except DatabaseConnectionError:
        return


def _plan_agent_limit(plan: str) -> int:
    if plan == "starter":
        return 1
    if plan == "professional":
        return 3
    if plan == "full_team":
        return 7
    return 0


def _provision_plan_agents(owner_id: str, plan: str) -> list[dict[str, object]]:
    db = _get_db()
    if not db:
        return []
    try:
        existing = db.fetch_all("agents", {"owner_id": owner_id})
    except DatabaseConnectionError:
        return []

    existing_roles = {str(row.get("role") or row.get("agent_type") or "").lower() for row in existing}
    created: list[dict[str, object]] = []
    for agent_name, role in _PLAN_AGENT_BLUEPRINTS.get(plan, []):
        normalized_role = role.lower()
        if normalized_role in existing_roles:
            continue
        try:
            provisioned = provision_agent(
                owner_id=owner_id,
                agent_name=agent_name,
                role=role,
                brain_provider="claude",
            )
            created.append({"name": agent_name, "role": role, "agent_id": provisioned.get("agent_id")})
            existing_roles.add(normalized_role)
        except Exception:
            continue
    return created


def _deprovision_paid_agents(owner_id: str, keep_limit: int) -> list[str]:
    db = _get_db()
    if not db:
        return []
    try:
        existing = db.fetch_all("agents", {"owner_id": owner_id})
    except DatabaseConnectionError:
        return []

    removed: list[str] = []
    for agent in existing[keep_limit:]:
        agent_id = str(agent.get("id") or "")
        if not agent_id:
            continue
        try:
            deprovision_agent(agent_id)
            removed.append(agent_id)
        except Exception:
            continue
    return removed


def _send_owner_billing_sms(owner_id: str, message: str) -> bool:
    db = _get_db()
    if not db:
        return False
    try:
        owners = db.fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError:
        return False
    if not owners:
        return False
    owner_number = str(owners[0].get("phone") or get_settings().my_phone_number or "").strip()
    if not owner_number:
        return False
    try:
        send_sms(to=owner_number, message=message)
        return True
    except Exception:
        return False


def _handle_checkout_completed(event: dict) -> dict[str, object]:
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    owner_id = str(metadata.get("owner_id") or "")
    plan = str(metadata.get("plan") or "starter")
    if not owner_id:
        return {"success": False, "reason": "owner_id missing"}

    _update_owner_billing(
        owner_id,
        {
            "plan": plan,
            "subscription_plan": plan,
            "subscription_status": "active",
            "stripe_customer_id": data.get("customer"),
            "stripe_subscription_id": data.get("subscription"),
            "trial_ends_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    created_agents = _provision_plan_agents(owner_id, plan)
    _send_owner_billing_sms(owner_id, f"Your ORB {plan} plan is active. Your team is being provisioned now.")
    return {"success": True, "owner_id": owner_id, "plan": plan, "provisioned_agents": created_agents}


def _handle_subscription_updated(event: dict) -> dict[str, object]:
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    owner_id = str(metadata.get("owner_id") or "")
    plan = str(metadata.get("plan") or metadata.get("subscription_plan") or "starter")
    if not owner_id:
        return {"success": False, "reason": "owner_id missing"}

    current_period_end = data.get("current_period_end")
    _update_owner_billing(
        owner_id,
        {
            "plan": plan,
            "subscription_plan": plan,
            "subscription_status": str(data.get("status") or "active"),
            "stripe_customer_id": data.get("customer"),
            "stripe_subscription_id": data.get("id"),
            "subscription_current_period_end": datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat() if current_period_end else None,
        },
    )
    created_agents = _provision_plan_agents(owner_id, plan)
    removed_agents = _deprovision_paid_agents(owner_id, _plan_agent_limit(plan))
    return {"success": True, "owner_id": owner_id, "plan": plan, "provisioned_agents": created_agents, "deprovisioned_agents": removed_agents}


def _handle_subscription_deleted(event: dict) -> dict[str, object]:
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    owner_id = str(metadata.get("owner_id") or "")
    if not owner_id:
        return {"success": False, "reason": "owner_id missing"}

    _update_owner_billing(
        owner_id,
        {
            "plan": "free",
            "subscription_plan": "free",
            "subscription_status": "cancelled",
            "grace_period_ends_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
    )
    removed_agents = _deprovision_paid_agents(owner_id, 0)
    _send_owner_billing_sms(owner_id, "Your ORB subscription ended. Paid agents are paused, and your data is retained for 30 days.")
    return {"success": True, "owner_id": owner_id, "deprovisioned_agents": removed_agents}


def _handle_invoice_payment_failed(event: dict) -> dict[str, object]:
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    owner_id = str(metadata.get("owner_id") or "")
    if not owner_id:
        return {"success": False, "reason": "owner_id missing"}

    _update_owner_billing(owner_id, {"subscription_status": "past_due", "grace_period_ends_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()})
    _send_owner_billing_sms(owner_id, "Heads up: your last ORB payment did not go through. Your team is still working, but please update your card within 3 days.")
    return {"success": True, "owner_id": owner_id, "status": "past_due"}


def _handle_trial_will_end(event: dict) -> dict[str, object]:
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    owner_id = str(metadata.get("owner_id") or "")
    if not owner_id:
        return {"success": False, "reason": "owner_id missing"}

    _send_owner_billing_sms(owner_id, "Your ORB trial ends in 3 days. I can help you choose the right plan before anything is interrupted.")
    return {"success": True, "owner_id": owner_id, "status": "trial_will_end"}


def _handle_stripe_event(event: dict) -> dict[str, object]:
    event_type = str(event.get("type") or "")
    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(event)
    if event_type == "customer.subscription.updated":
        return _handle_subscription_updated(event)
    if event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(event)
    if event_type == "invoice.payment_failed":
        return _handle_invoice_payment_failed(event)
    if event_type == "customer.subscription.trial_will_end":
        return _handle_trial_will_end(event)
    return {"success": False, "reason": f"Unhandled event type: {event_type}"}


@router.get("/status")
def webhook_routes_status() -> dict[str, str]:
    """Simple route to confirm the webhook router is loaded."""
    return {"status": "webhooks router ready"}


@router.post("/tradingview")
async def tradingview_webhook(
    request: Request,
    x_tradingview_secret: str | None = Header(default=None),
) -> dict:
    """Accepts TradingView alerts, evaluates them, and creates approval requests when valid."""
    payload = await request.json()
    payload_secret = payload.get("secret") or payload.get("webhook_secret")

    if not validate_tradingview_secret(x_tradingview_secret, payload_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TradingView secret.")

    parsed = parse_tradingview_payload(payload)
    strategy = load_strategy("es_momentum")
    risk_result = check_can_trade(parsed.get("agent_id") or "default-agent")
    analysis = analyze_setup(parsed, strategy)

    approval_result = None
    if parsed.get("agent_id") and risk_result["can_trade"] and analysis.get("approval_required"):
        approval_payload = {
            **analysis,
            "instrument": parsed.get("symbol"),
            "setup_name": strategy.get("name"),
            "strategy_name": strategy.get("name"),
            "direction": parsed.get("direction") or "long",
            "owner_phone_number": parsed.get("owner_phone_number"),
        }
        approval_result = request_trade_approval(approval_payload, parsed["agent_id"])

    return {
        "received": True,
        "parsed": parsed,
        "risk_check": risk_result,
        "analysis": analysis,
        "approval": approval_result,
    }


@router.post("/twilio/sms")
async def twilio_sms_webhook(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> Response:
    """Parses YES/NO/STOP text replies and updates the latest pending trade for the target agent."""
    body = (await request.body()).decode("utf-8")
    form = {key: values[0] for key, values in parse_qs(body).items()}

    if not _is_valid_twilio_request(str(request.url), form, x_twilio_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature.")

    mobile = process_mobile_command(
        from_number=form.get("From", ""),
        message_body=form.get("Body", ""),
    )
    if mobile:
        reply_text = str(mobile.get("message") or "Command received.")
        twiml = f"<Response><Message>{reply_text}</Message></Response>"
        return Response(content=twiml, media_type="application/xml")

    result = handle_trade_reply(
        message_body=form.get("Body", ""),
        to_number=form.get("To", ""),
        from_number=form.get("From", ""),
    )

    message = result.get("detail") or f"Reply processed: {result.get('decision', 'unknown')}"
    twiml = f"<Response><Message>{message}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")


@router.post("/whatsapp/incoming")
async def whatsapp_incoming_webhook(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> Response:
    """Handles inbound Twilio WhatsApp messages for Commander and trade approvals."""
    body = (await request.body()).decode("utf-8")
    form = {key: values[0] for key, values in parse_qs(body).items()}

    if not _is_valid_twilio_request(str(request.url), form, x_twilio_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature.")

    from_number = _normalize_channel_number(form.get("From", ""))
    to_number = _normalize_channel_number(form.get("To", ""))
    message_body = form.get("Body", "")

    commander = handle_incoming_whatsapp_message(from_number=from_number, message_body=message_body)
    if commander:
        reply_text = str(commander.get("message") or "Command received.")
        twiml = f"<Response><Message>{reply_text}</Message></Response>"
        return Response(content=twiml, media_type="application/xml")

    result = handle_trade_reply(
        message_body=message_body,
        to_number=to_number,
        from_number=from_number,
    )
    message = result.get("detail") or f"Reply processed: {result.get('decision', 'unknown')}"
    twiml = f"<Response><Message>{message}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")


@router.post("/email/incoming")
def email_incoming_webhook(
    payload: InboundEmailPayload,
    x_orb_email_secret: str | None = Header(default=None),
) -> dict[str, object]:
    """Handles inbound email commands for Commander orchestration."""
    configured_secret = str(get_settings().resolve("email_webhook_secret", default="")).strip()
    if configured_secret and x_orb_email_secret != configured_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email webhook secret.")

    command = handle_incoming_email_message(
        from_email=payload.from_email,
        subject=payload.subject,
        text_body=payload.text,
    )

    if not command:
        return {
            "received": True,
            "processed": False,
            "detail": "No matching owner or command.",
            "provider": payload.provider,
        }

    return {
        "received": True,
        "processed": True,
        "provider": payload.provider,
        "result": command,
    }


@router.post("/n8n/error")
def n8n_error_webhook(payload: N8nErrorPayload, request: Request) -> dict[str, object]:
    """Accepts N8N failure notifications, logs them, and alerts the owner without retry loops."""
    request_id: str | None = getattr(request.state, "request_id", None)
    
    details = (
        f"N8N workflow failure: {payload.workflow_name}. "
        f"Error: {payload.error_message}. "
        f"Execution: {payload.execution_id or 'n/a'}"
    )

    logged = False
    alert_sent = False
    alert_error: str | None = None

    try:
        log_activity(
            agent_id=None,
            action_type="n8n_error_webhook",
            description=details,
            outcome="received",
            cost_cents=0,
            needs_approval=False,
            request_id=request_id,
        )
        log_activity(
            agent_id=None,
            action_type="sage_alert",
            description=f"Sage alerted to investigate workflow '{payload.workflow_name}'.",
            outcome="queued",
            cost_cents=0,
            needs_approval=False,
            request_id=request_id,
        )
        logged = True
    except Exception as error:
        alert_error = f"activity_log_failure: {error}"

    try:
        settings = get_settings()
        owner_number = settings.my_phone_number
        if owner_number and str(owner_number).strip():
            sms_text = (
                "ORB ALERT: N8N workflow failed. "
                f"Workflow: {payload.workflow_name}. "
                f"Error: {payload.error_message[:120]}"
            )
            send_sms(to=owner_number, message=sms_text)
            alert_sent = True
    except Exception as error:
        if alert_error:
            alert_error = f"{alert_error}; sms_failure: {error}"
        else:
            alert_error = f"sms_failure: {error}"

    # Always return 200 so N8N does not create infinite retries.
    return {
        "received": True,
        "status": "accepted",
        "logged": logged,
        "alert_sent": alert_sent,
        "workflow_name": payload.workflow_name,
        "execution_id": payload.execution_id,
        "error": alert_error,
    }


@router.post("/n8n/complete")
def n8n_complete_webhook(payload: N8nCompletePayload, request: Request) -> dict[str, object]:
    """Accepts N8N workflow completion callbacks and dispatches post-completion handlers."""
    request_id: str | None = getattr(request.state, "request_id", None)

    result = handle_workflow_complete(payload.event, payload.workflow_name, payload.workflow_data)
    success = result.get("success", False)

    try:
        log_activity(
            agent_id=None,
            action_type="n8n_workflow_complete",
            description=(
                f"N8N workflow '{payload.workflow_name}' completed. "
                f"Event: {payload.event}. Execution: {payload.execution_id or 'n/a'}"
            ),
            outcome="completed" if success else "unknown_workflow",
            cost_cents=0,
            needs_approval=False,
            request_id=request_id,
        )
    except Exception:
        pass  # Never 500 on incoming N8N callbacks

    # Always return 200 so N8N does not loop retries
    return {
        "received": True,
        "status": "processed" if success else "no_handler",
        "workflow_name": payload.workflow_name,
        "execution_id": payload.execution_id,
        "handler_result": result,
    }


@router.post("/stripe")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")) -> dict[str, object]:
    """Handles Stripe billing lifecycle events with signature verification."""
    settings = get_settings()
    if not settings.stripe_secret_key.strip() or not settings.stripe_webhook_secret.strip():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe webhook is not configured yet.")

    payload = await request.body()
    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature, secret=settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Stripe signature.") from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe payload.") from error

    result = _handle_stripe_event(event)
    try:
        log_activity(
            agent_id=None,
            action_type="stripe_webhook",
            description=f"Stripe webhook received: {event.get('type', 'unknown')}",
            outcome="processed" if result.get("success") else "ignored",
            cost_cents=0,
            needs_approval=False,
        )
    except Exception:
        pass

    return {"received": True, "event_type": event.get("type"), "handler_result": result}
