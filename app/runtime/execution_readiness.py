"""Execution-readiness checks for owner workspaces.

Goal: ensure agents can do real work (not only chat) by validating:
1) Identity foundations (owner + active agents have core fields)
2) Integrations and channels needed for outbound actions
3) Number of executable tools currently available
"""

from __future__ import annotations

from typing import Any

from agents.commander.tool_registry import get_all_tools
from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings


ENV_TO_SETTING = {
    "TWILIO_FROM_NUMBER": "twilio_from_number",
    "TWILIO_PHONE_NUMBER": "twilio_from_number",
    "TWILIO_ACCOUNT_SID": "twilio_account_sid",
    "TWILIO_AUTH_TOKEN": "twilio_auth_token",
    "RESEND_API_KEY": "resend_api_key",
    "SLACK_BOT_TOKEN": "slack_bot_token",
    "GOOGLE_REFRESH_TOKEN": "google_refresh_token",
    "FOLLOWUPBOSS_API_KEY": "followupboss_api_key",
    "HUBSPOT_API_KEY": "hubspot_api_key",
    "NOTION_API_KEY": "notion_api_key",
    "GITHUB_TOKEN": "github_token",
    "OPENPHONE_API_KEY": "openphone_api_key",
    "OPENPHONE_NUMBER_ID": "openphone_number_id",
    "MAILCHIMP_API_KEY": "mailchimp_api_key",
    "PIPEDRIVE_API_KEY": "pipedrive_api_key",
    "CALENDLY_API_KEY": "calendly_api_key",
    "AIRTABLE_API_KEY": "airtable_api_key",
    "ZAPIER_WEBHOOK_URL": "zapier_webhook_url",
    "TEAMS_WEBHOOK_URL": "teams_webhook_url",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
}


def _setting_key_from_env(env_name: str) -> str:
    return ENV_TO_SETTING.get(env_name, env_name.strip().lower())


def _is_configured(settings: Any, env_var_name: str) -> bool:
    key = _setting_key_from_env(env_var_name)
    checker = getattr(settings, "is_configured", None)
    if callable(checker):
        return bool(checker(key))
    value = getattr(settings, key, "")
    return bool(str(value or "").strip())


def owner_execution_readiness(owner_id: str) -> dict[str, Any]:
    """Return execution readiness scorecard for one owner workspace."""
    settings = get_settings()
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    try:
        db = SupabaseService()
    except DatabaseConnectionError as exc:
        return {
            "ready": False,
            "score": 0,
            "blockers": [{"code": "db_unavailable", "message": str(exc)}],
            "warnings": [],
            "identity": {},
            "integrations": {},
            "tool_execution": {},
        }

    try:
        owners = db.fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError as exc:
        return {
            "ready": False,
            "score": 0,
            "blockers": [{"code": "owner_lookup_failed", "message": str(exc)}],
            "warnings": [],
            "identity": {},
            "integrations": {},
            "tool_execution": {},
        }
    if not owners:
        blockers.append({"code": "owner_missing", "message": "Owner does not exist in owners table."})
        owner = {}
    else:
        owner = owners[0]

    owner_email = str(owner.get("email") or "").strip()
    owner_phone = str(owner.get("phone") or "").strip()
    if not owner_email:
        blockers.append({"code": "owner_email_missing", "message": "Owner email is required for identity continuity."})
    if not owner_phone:
        warnings.append({"code": "owner_phone_missing", "message": "Owner phone is recommended for approval and escalation flows."})

    try:
        agents = db.fetch_all("agents", {"owner_id": owner_id})
    except DatabaseConnectionError:
        agents = []
    active_agents = [a for a in agents if bool(a.get("is_active", True)) and str(a.get("status") or "").lower() != "deprovisioned"]

    if not active_agents:
        blockers.append({"code": "no_active_agents", "message": "No active agents are provisioned for this owner."})

    missing_agent_fields = 0
    for agent in active_agents:
        if not str(agent.get("name") or "").strip():
            missing_agent_fields += 1
        if not str(agent.get("agent_type") or "").strip():
            missing_agent_fields += 1
        if not str(agent.get("email_address") or "").strip():
            missing_agent_fields += 1
        if not str(agent.get("phone_number") or "").strip():
            missing_agent_fields += 1

    if missing_agent_fields > 0:
        blockers.append(
            {
                "code": "agent_identity_incomplete",
                "message": "One or more active agents are missing name/role/email/phone identity fields.",
            }
        )

    try:
        owner_integrations = db.fetch_all("owner_integrations", {"owner_id": owner_id})
    except DatabaseConnectionError:
        owner_integrations = []
    connected = [row for row in owner_integrations if str(row.get("status") or "").lower() == "connected"]
    connected_slugs = {str(r.get("provider_slug") or "").lower() for r in connected}

    execution_channels = {
        "twilio": _is_configured(settings, "TWILIO_ACCOUNT_SID") and _is_configured(settings, "TWILIO_AUTH_TOKEN"),
        "resend": _is_configured(settings, "RESEND_API_KEY"),
        "slack": _is_configured(settings, "SLACK_BOT_TOKEN"),
        "google_calendar": _is_configured(settings, "GOOGLE_REFRESH_TOKEN"),
    }

    if not any(execution_channels.values()) and not connected_slugs:
        blockers.append(
            {
                "code": "no_execution_channels",
                "message": "No delivery/integration channels are configured, so agents cannot execute outbound work.",
            }
        )

    tools = get_all_tools()
    executable_tools = 0
    for metadata in tools.values():
        if metadata.always_available:
            executable_tools += 1
            continue
        if metadata.required_env_vars and all(_is_configured(settings, env_key) for env_key in metadata.required_env_vars):
            executable_tools += 1

    if executable_tools < 10:
        warnings.append(
            {
                "code": "low_executable_tool_count",
                "message": "Few tools are executable with current integrations. Connect more providers for real autonomy.",
            }
        )

    score = max(0, 100 - len(blockers) * 28 - len(warnings) * 8)
    return {
        "ready": len(blockers) == 0,
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "identity": {
            "owner_email_present": bool(owner_email),
            "owner_phone_present": bool(owner_phone),
            "active_agents": len(active_agents),
            "missing_agent_identity_fields": missing_agent_fields,
        },
        "integrations": {
            "owner_connected_integrations": len(connected),
            "connected_slugs": sorted(connected_slugs),
            "execution_channels": execution_channels,
        },
        "tool_execution": {
            "total_tools": len(tools),
            "executable_tools": executable_tools,
        },
    }
