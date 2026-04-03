"""Dashboard data routes for ORB command center."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.connection import DatabaseConnectionError, SupabaseService
from app.database.schema_readiness import schema_readiness_payload
from app.runtime.preflight import build_preflight_report
from config.settings import get_settings
from integrations.brain_connector import TASK_BRAIN_MAPPING
from integrations.claude_client import ping_claude
from integrations.openai_client import ask_gpt_mini
from integrations.twilio_client import get_messages

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class RejectPayload(BaseModel):
    """Reason provided when rejecting an approval item."""

    reason: str


class IntegrationLiveCheckPayload(BaseModel):
    """Optional targeted checks for dashboard integration control center."""

    checks: list[str] | None = None


_FALLBACK_IMPROVEMENTS: list[dict[str, Any]] = [
    {
        "id": "imp-rex-routing",
        "agent_id": "rex",
        "owner_id": "local-owner",
        "improvement_type": "routing",
        "description": "Route simple lead replies to the cheapest fast brain to reduce cost.",
        "before_metric": 0.32,
        "after_metric": 0.21,
        "metric_name": "cost_per_lead",
        "status": "proposed",
        "impact_score": 8,
        "created_at": "2026-04-01T15:00:00+00:00",
    },
    {
        "id": "imp-aria-briefing",
        "agent_id": "aria",
        "owner_id": "local-owner",
        "improvement_type": "behavior",
        "description": "Move Aria briefing summary block higher to reduce morning scan time.",
        "before_metric": 6.2,
        "after_metric": 4.8,
        "metric_name": "minutes_to_priority_clarity",
        "status": "proposed",
        "impact_score": 6,
        "created_at": "2026-04-01T14:40:00+00:00",
    },
    {
        "id": "imp-atlas-security",
        "agent_id": "atlas",
        "owner_id": "local-owner",
        "improvement_type": "prompt",
        "description": "Add stricter secret redaction checks before code generation responses are returned.",
        "before_metric": 94,
        "after_metric": 97,
        "metric_name": "security_score",
        "status": "proposed",
        "impact_score": 9,
        "created_at": "2026-04-01T14:20:00+00:00",
    },
]


def _safe_fetch(db: SupabaseService, table: str) -> list[dict[str, Any]]:
    """Fetches table rows, returning empty list when table is unavailable."""
    try:
        return db.fetch_all(table)
    except DatabaseConnectionError:
        return []


def _parse_row_date(value: Any) -> datetime | None:
    """Parses ISO date values from database rows."""
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mask_secret(value: str) -> str:
    """Returns a safe masked preview for UI visibility."""
    if not value:
        return ""
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def _looks_placeholder(value: str) -> bool:
    """Heuristic to flag placeholder credentials in local environments."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return True
    marker_words = (
        "placeholder",
        "replace",
        "changeme",
        "example",
        "test",
        "your_",
        "your-",
    )
    return any(word in lowered for word in marker_words)


def _integration_snapshot() -> dict[str, Any]:
    """Builds integration config visibility for UI dashboards."""
    settings = get_settings()
    anthropic_key = settings.resolve("anthropic_api_key")
    openai_key = settings.resolve("openai_api_key")
    twilio_sid = settings.resolve("twilio_account_sid")
    twilio_token = settings.resolve("twilio_auth_token")
    twilio_number = settings.resolve("twilio_phone_number")

    records = [
        {
            "key": "supabase",
            "configured": bool(settings.supabase_url and settings.supabase_service_key),
            "placeholder_risk": _looks_placeholder(settings.supabase_url) or _looks_placeholder(settings.supabase_service_key),
            "details": {
                "url": _mask_secret(settings.supabase_url),
                "service_key": _mask_secret(settings.supabase_service_key),
            },
        },
        {
            "key": "anthropic",
            "configured": bool(anthropic_key),
            "placeholder_risk": _looks_placeholder(anthropic_key),
            "details": {"api_key": _mask_secret(anthropic_key)},
        },
        {
            "key": "openai",
            "configured": bool(openai_key),
            "placeholder_risk": _looks_placeholder(openai_key),
            "details": {"api_key": _mask_secret(openai_key)},
        },
        {
            "key": "twilio",
            "configured": bool(twilio_sid and twilio_token and twilio_number),
            "placeholder_risk": _looks_placeholder(twilio_sid) or _looks_placeholder(twilio_token),
            "details": {
                "account_sid": _mask_secret(twilio_sid),
                "from_number": twilio_number,
            },
        },
        {
            "key": "railway",
            "configured": bool(settings.railway_api_token and settings.railway_project_id),
            "placeholder_risk": _looks_placeholder(settings.railway_api_token) or _looks_placeholder(settings.railway_project_id),
            "details": {
                "api_token": _mask_secret(settings.railway_api_token),
                "project_id": _mask_secret(settings.railway_project_id),
            },
        },
    ]

    for record in records:
        if not record["configured"]:
            record["status"] = "missing"
        elif record["placeholder_risk"]:
            record["status"] = "warning"
        else:
            record["status"] = "ready"

    return {
        "integrations": records,
        "ui_controls": {
            "computer_use_enabled": settings.computer_use_enabled,
            "computer_use_screenshot_dir": settings.computer_use_screenshot_dir,
            "token_cache_ttl_minutes": settings.token_cache_ttl_minutes,
        },
    }


def _run_live_check(check_name: str) -> dict[str, Any]:
    """Runs a single integration health check and returns normalized output."""
    try:
        if check_name == "supabase":
            rows = SupabaseService().fetch_all("activity_log")
            return {"check": check_name, "ok": True, "detail": f"Connected (activity_log rows={len(rows)})"}

        if check_name == "anthropic":
            result = ping_claude()
            return {"check": check_name, "ok": True, "detail": f"Reply: {result.get('response', '').strip()}"}

        if check_name == "openai":
            result = ask_gpt_mini(prompt="Reply with exactly: hello", max_tokens=8, task_type="short_analysis")
            return {"check": check_name, "ok": True, "detail": f"Reply: {(result.get('text') or '').strip()}"}

        if check_name == "twilio":
            settings = get_settings()
            rows = get_messages(settings.resolve("twilio_phone_number"), limit=1)
            return {"check": check_name, "ok": True, "detail": f"Retrieved {len(rows)} messages"}

        return {"check": check_name, "ok": False, "detail": "Unsupported check name."}
    except Exception as error:
        return {"check": check_name, "ok": False, "detail": str(error)}


def _build_setup_checklist() -> dict[str, Any]:
    """Builds a UI-first readiness checklist for local platform setup."""
    snapshot = _integration_snapshot()
    schema = schema_readiness_payload()
    preflight = build_preflight_report()
    integration_rows = {str(item.get("key") or ""): item for item in snapshot.get("integrations", [])}

    def integration_status(name: str) -> str:
        row = integration_rows.get(name, {})
        status = str(row.get("status") or "missing")
        if status == "ready":
            return "ready"
        if status == "warning":
            return "attention"
        return "attention"

    steps = [
        {
            "id": "dashboard-open",
            "title": "Open dashboard shell",
            "status": "ready",
            "detail": "Dashboard shell and command-center routes are available for local use.",
            "recommended_action": "Open /dashboard and verify the hero, stats, and operations index render.",
        },
        {
            "id": "platform-preflight",
            "title": "Run full platform preflight",
            "status": "ready" if preflight.get("ready") else "attention",
            "detail": "Preflight checks combine environment quality and schema readiness into a launch score.",
            "recommended_action": "Use Setup Wizard > Run Full Preflight and resolve blockers before launch.",
        },
        {
            "id": "database-schema",
            "title": "Confirm database schema readiness",
            "status": "ready" if schema.get("ready") else "attention",
            "detail": "Current runtime requires activity_log.metadata and owner_integrations for full onboarding + monitoring behavior.",
            "recommended_action": "Run scripts/setup_database.py --strict and apply scripts/database_migration_patch.sql if checks fail.",
        },
        {
            "id": "database-config",
            "title": "Confirm database configuration",
            "status": integration_status("supabase"),
            "detail": "Supabase config is required for most live platform operations.",
            "recommended_action": "Use Integration Control Center to confirm Supabase is ready and run a live check.",
        },
        {
            "id": "ai-primary",
            "title": "Confirm primary AI provider",
            "status": integration_status("anthropic"),
            "detail": "Anthropic is the current primary text provider for core agents.",
            "recommended_action": "Run live check for Anthropic and confirm low-cost test replies succeed.",
        },
        {
            "id": "ai-secondary",
            "title": "Confirm secondary AI provider",
            "status": integration_status("openai"),
            "detail": "OpenAI remains optional until final integrations, but UI should surface its state clearly.",
            "recommended_action": "Replace placeholder OPENAI_API_KEY before enabling final OpenAI-based workflows.",
        },
        {
            "id": "messaging",
            "title": "Confirm messaging setup",
            "status": integration_status("twilio"),
            "detail": "Twilio is needed for SMS tests, alerts, and agent messaging flows.",
            "recommended_action": "Run Twilio live check and verify the configured sender number is correct.",
        },
        {
            "id": "ui-controls",
            "title": "Review UI control toggles",
            "status": "ready",
            "detail": "Computer-use and token-cache controls are visible from the dashboard integration panel.",
            "recommended_action": "Review COMPUTER_USE_ENABLED and token cache TTL before enabling advanced flows.",
        },
    ]

    ready_count = sum(1 for step in steps if step.get("status") == "ready")
    attention_count = sum(1 for step in steps if step.get("status") == "attention")

    return {
        "steps": steps,
        "summary": {
            "ready": ready_count,
            "attention": attention_count,
            "total": len(steps),
        },
    }


def _brain_inventory() -> dict[str, Any]:
    """Returns UI-focused AI brain inventory and routing preferences."""
    settings = get_settings()
    anthropic_key = settings.resolve("anthropic_api_key")
    openai_key = settings.resolve("openai_api_key")

    records = [
        {
            "key": "anthropic",
            "label": "Claude (Anthropic)",
            "connected": bool(anthropic_key) and not _looks_placeholder(anthropic_key),
            "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-6"],
            "cost_range": "$0.00025 to $0.015 / 1k",
            "best_for": "Core reasoning and production work",
        },
        {
            "key": "openai",
            "label": "GPT-4 (OpenAI)",
            "connected": bool(openai_key) and not _looks_placeholder(openai_key),
            "models": ["gpt-4o-mini", "gpt-4o", "o1"],
            "cost_range": "$0.00015 to $0.015 / 1k",
            "best_for": "Vision tasks and multimodal analysis",
        },
        {
            "key": "google",
            "label": "Gemini (Google)",
            "connected": bool(settings.google_ai_api_key) and not _looks_placeholder(settings.google_ai_api_key),
            "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
            "cost_range": "Free tier available",
            "best_for": "Cheap fast drafting",
        },
        {
            "key": "groq",
            "label": "Groq (Fast AI)",
            "connected": bool(settings.groq_api_key) and not _looks_placeholder(settings.groq_api_key),
            "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
            "cost_range": "Free/low-cost",
            "best_for": "Fast simple replies",
        },
        {
            "key": "mistral",
            "label": "Mistral",
            "connected": bool(settings.mistral_api_key) and not _looks_placeholder(settings.mistral_api_key),
            "models": ["mistral-7b-instruct", "mistral-medium", "mistral-large"],
            "cost_range": "Low to medium",
            "best_for": "EU-friendly deployments",
        },
        {
            "key": "ollama",
            "label": "Ollama (Local)",
            "connected": bool(settings.ollama_base_url),
            "models": ["llama3.1", "mistral", "phi3"],
            "cost_range": "$0 local",
            "best_for": "Privacy mode",
        },
        {
            "key": "custom",
            "label": "Custom API",
            "connected": False,
            "models": ["OpenAI-compatible endpoint"],
            "cost_range": "Varies",
            "best_for": "Future models",
        },
    ]

    monthly_usage = [
        {"provider": "anthropic", "spend_dollars": 0.24},
        {"provider": "openai", "spend_dollars": 0.08},
        {"provider": "groq", "spend_dollars": 0.00},
        {"provider": "ollama", "spend_dollars": 0.00},
    ]

    return {
        "brains": records,
        "routing_modes": {
            "automatic": True,
            "budget_mode": False,
            "quality_mode": False,
            "privacy_mode": bool(settings.privacy_mode),
        },
        "task_routes": TASK_BRAIN_MAPPING,
        "monthly_usage": monthly_usage,
    }


def _load_improvements() -> list[dict[str, Any]]:
    """Loads improvement proposals with local fallback when DB table is unavailable."""
    try:
        db = SupabaseService()
        rows = db.fetch_all("improvements")
        if rows:
            rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
            return rows
    except (DatabaseConnectionError, Exception):
        pass
    return [dict(item) for item in _FALLBACK_IMPROVEMENTS]


def _update_fallback_improvement(improvement_id: str, status: str, note: str | None = None) -> dict[str, Any] | None:
    """Updates in-memory fallback improvement proposals."""
    for row in _FALLBACK_IMPROVEMENTS:
        if str(row.get("id")) != improvement_id:
            continue
        row["status"] = status
        if status == "approved":
            row["approved_at"] = datetime.now(timezone.utc).isoformat()
        if note:
            row["decision_note"] = note
        return dict(row)
    return None


def _build_notifications() -> dict[str, Any]:
    """Builds a notification feed for the top-bar drawer."""
    integration_rows = _integration_snapshot().get("integrations", [])
    warning_integrations = [row for row in integration_rows if row.get("status") == "warning"]
    improvements = [row for row in _load_improvements() if str(row.get("status") or "") == "proposed"]
    approvals = dashboard_approvals().get("approvals", [])[:5]

    notifications: list[dict[str, Any]] = []
    if warning_integrations:
        notifications.append(
            {
                "type": "warning",
                "title": "Integration attention needed",
                "message": f"{len(warning_integrations)} integration(s) have placeholder or risky credentials.",
            }
        )
    if approvals:
        notifications.append(
            {
                "type": "approval",
                "title": "Pending approvals waiting",
                "message": f"{len(approvals)} activity item(s) still need your decision.",
            }
        )
    if improvements:
        notifications.append(
            {
                "type": "improvement",
                "title": "Agent improvements proposed",
                "message": f"{len(improvements)} change suggestion(s) are waiting for review.",
            }
        )

    if not notifications:
        notifications.append(
            {
                "type": "info",
                "title": "Everything looks calm",
                "message": "No urgent alerts right now. ORB is operating within expected thresholds.",
            }
        )

    return {"notifications": notifications, "unread_count": len(notifications)}


@router.get("/overview")
def dashboard_overview() -> dict[str, Any]:
    """Returns top-level command center data for the dashboard UI."""
    db = SupabaseService()

    agents = _safe_fetch(db, "agents")
    activity = _safe_fetch(db, "activity_log")
    leads = _safe_fetch(db, "leads")
    paper_trades = _safe_fetch(db, "paper_trades")

    now_date = datetime.now(timezone.utc).date()

    # Build activity feed and approvals queue from recent actions.
    recent_activity = sorted(
        activity,
        key=lambda r: str(r.get("created_at") or ""),
        reverse=True,
    )
    activity_feed = recent_activity[:20]
    approval_queue = [row for row in recent_activity if row.get("needs_approval") is True][:20]

    calls_made_today = 0
    appointments_booked = 0
    emails_drafted = 0
    cost_today_cents = 0

    for row in recent_activity:
        row_dt = _parse_row_date(row.get("created_at"))
        if not row_dt or row_dt.date() != now_date:
            continue
        action_type = str(row.get("action_type") or "").lower()
        if action_type == "call":
            calls_made_today += 1
        if action_type in {"appointment", "appointment_booked"}:
            appointments_booked += 1
        if action_type in {"email_draft", "email"}:
            emails_drafted += 1
        cost_today_cents += int(row.get("cost_cents") or 0)

    leads_today = 0
    for row in leads:
        row_dt = _parse_row_date(row.get("created_at"))
        if row_dt and row_dt.date() == now_date:
            leads_today += 1

    paper_trades_today = 0
    paper_pnl_today = 0.0
    for row in paper_trades:
        row_dt = _parse_row_date(row.get("created_at"))
        if not row_dt or row_dt.date() != now_date:
            continue
        paper_trades_today += 1
        paper_pnl_today += float(row.get("pnl_dollars") or 0)

    agent_rows = []
    for agent in agents:
        agent_id = str(agent.get("id") or "")
        agent_actions_today = 0
        last_action = "No recent action"
        last_action_time = ""

        for row in recent_activity:
            if str(row.get("agent_id") or "") != agent_id:
                continue
            if not last_action_time:
                last_action = str(row.get("description") or "No recent action")
                last_action_time = str(row.get("created_at") or "")
            row_dt = _parse_row_date(row.get("created_at"))
            if row_dt and row_dt.date() == now_date:
                agent_actions_today += 1

        agent_rows.append(
            {
                "id": agent_id,
                "name": str(agent.get("name") or "Unnamed"),
                "role": str(agent.get("role") or "unknown"),
                "status": str(agent.get("status") or "unknown"),
                "actions_today": agent_actions_today,
                "last_action": last_action,
                "last_action_time": last_action_time,
            }
        )

    return {
        "agents": agent_rows,
        "activity_feed": activity_feed,
        "approval_queue": approval_queue,
        "stats": {
            "leads_today": leads_today,
            "calls_made_today": calls_made_today,
            "appointments_booked": appointments_booked,
            "emails_drafted": emails_drafted,
            "content_queued": 0,
            "paper_trades_today": paper_trades_today,
            "paper_pnl_today": round(paper_pnl_today, 2),
            "cost_today_dollars": round(cost_today_cents / 100, 2),
        },
    }


@router.get("/pipeline")
def dashboard_pipeline() -> dict[str, Any]:
    """Returns lead pipeline grouped by status for kanban-style UI."""
    db = SupabaseService()
    leads = _safe_fetch(db, "leads")

    buckets: dict[str, list[dict[str, Any]]] = {
        "new": [],
        "contacted": [],
        "qualified": [],
        "appointment": [],
        "offer": [],
        "closed": [],
        "other": [],
    }

    for lead in leads:
        status = str(lead.get("status") or "new").lower()
        if status not in buckets:
            status = "other"
        buckets[status].append(lead)

    return {"pipeline": buckets, "total": len(leads)}


@router.get("/approvals")
def dashboard_approvals() -> dict[str, Any]:
    """Returns pending approvals ordered newest first."""
    db = SupabaseService()
    activity = _safe_fetch(db, "activity_log")
    approvals = [row for row in activity if row.get("needs_approval") is True]
    approvals.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return {"approvals": approvals, "count": len(approvals)}


@router.post("/approve/{activity_id}")
def dashboard_approve(activity_id: str) -> dict[str, Any]:
    """Approves a pending activity item."""
    db = SupabaseService()
    rows = db.update_many(
        "activity_log",
        {"id": activity_id},
        {
            "approved": True,
            "needs_approval": False,
            "outcome": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Approval item not found.")
    return {"status": "approved", "activity_id": activity_id}


@router.post("/reject/{activity_id}")
def dashboard_reject(activity_id: str, payload: RejectPayload) -> dict[str, Any]:
    """Rejects a pending activity item with a reason."""
    db = SupabaseService()
    rows = db.update_many(
        "activity_log",
        {"id": activity_id},
        {
            "approved": False,
            "needs_approval": False,
            "outcome": f"rejected: {payload.reason}",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Approval item not found.")
    return {"status": "rejected", "activity_id": activity_id, "reason": payload.reason}


@router.get("/integrations")
def dashboard_integrations() -> dict[str, Any]:
    """Returns integration readiness snapshot for UI-first operations."""
    snapshot = _integration_snapshot()
    integrations = snapshot.get("integrations", [])
    ready_count = sum(1 for row in integrations if row.get("status") == "ready")
    return {
        "integrations": integrations,
        "ready_count": ready_count,
        "total": len(integrations),
        "ui_controls": snapshot.get("ui_controls", {}),
    }


@router.get("/ai-brains")
def dashboard_ai_brains() -> dict[str, Any]:
    """Returns UI metadata for the universal AI brain layer."""
    return _brain_inventory()


@router.get("/improvements")
def dashboard_improvements() -> dict[str, Any]:
    """Returns agent improvement proposals and current decision state."""
    rows = _load_improvements()
    proposed = [row for row in rows if str(row.get("status") or "") == "proposed"]
    return {
        "improvements": rows,
        "proposed_count": len(proposed),
        "approved_count": sum(1 for row in rows if str(row.get("status") or "") == "approved"),
    }


@router.post("/improvements/{improvement_id}/approve")
def dashboard_improvement_approve(improvement_id: str) -> dict[str, Any]:
    """Approves an improvement proposal."""
    try:
        db = SupabaseService()
        rows = db.update_many(
            "improvements",
            {"id": improvement_id},
            {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat()},
        )
        if rows:
            return {"status": "approved", "improvement_id": improvement_id}
    except DatabaseConnectionError:
        pass

    fallback = _update_fallback_improvement(improvement_id, "approved")
    if not fallback:
        raise HTTPException(status_code=404, detail="Improvement item not found.")
    return {"status": "approved", "improvement_id": improvement_id}


@router.post("/improvements/{improvement_id}/reject")
def dashboard_improvement_reject(improvement_id: str, payload: RejectPayload) -> dict[str, Any]:
    """Rejects an improvement proposal with a plain-English note."""
    try:
        db = SupabaseService()
        rows = db.update_many(
            "improvements",
            {"id": improvement_id},
            {"status": "rejected", "decision_note": payload.reason},
        )
        if rows:
            return {"status": "rejected", "improvement_id": improvement_id, "reason": payload.reason}
    except DatabaseConnectionError:
        pass

    fallback = _update_fallback_improvement(improvement_id, "rejected", payload.reason)
    if not fallback:
        raise HTTPException(status_code=404, detail="Improvement item not found.")
    return {"status": "rejected", "improvement_id": improvement_id, "reason": payload.reason}


@router.get("/notifications")
def dashboard_notifications() -> dict[str, Any]:
    """Returns the current dashboard notification drawer payload."""
    return _build_notifications()


@router.post("/integrations/live-check")
def dashboard_integrations_live_check(payload: IntegrationLiveCheckPayload) -> dict[str, Any]:
    """Runs optional live checks to confirm integration connectivity."""
    requested = payload.checks or ["supabase", "anthropic", "openai", "twilio"]
    normalized = []
    for item in requested:
        name = str(item or "").strip().lower()
        if name and name not in normalized:
            normalized.append(name)

    results = [_run_live_check(name) for name in normalized]
    passed = sum(1 for row in results if row.get("ok") is True)
    return {
        "checks": results,
        "passed": passed,
        "total": len(results),
        "failed": len(results) - passed,
    }


@router.get("/command-center")
def dashboard_command_center() -> dict[str, Any]:
    """Returns one consolidated payload for the dashboard UI shell."""
    overview = dashboard_overview()
    pipeline = dashboard_pipeline()
    approvals = dashboard_approvals()
    integrations = dashboard_integrations()
    brains = dashboard_ai_brains()
    improvements = dashboard_improvements()
    notifications = dashboard_notifications()
    setup = _build_setup_checklist()
    return {
        "overview": overview,
        "pipeline": pipeline,
        "approvals": approvals,
        "integrations": integrations,
        "brains": brains,
        "improvements": improvements,
        "notifications": notifications,
        "setup": setup,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/setup-checklist")
def dashboard_setup_checklist() -> dict[str, Any]:
    """Returns a guided checklist for UI-first local setup and operations readiness."""
    return _build_setup_checklist()
