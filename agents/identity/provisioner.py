"""Agent identity provisioning helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from app.database.activity_log import log_activity
from app.database.connection import DatabaseConnectionError, SupabaseService
from agents.identity.email_manager import create_agent_email
from agents.identity.phone_manager import assign_number, get_available_numbers
from config.settings import get_settings
from integrations.twilio_client import send_sms


def _get_owner_record(db: SupabaseService, owner_id: str) -> dict[str, Any] | None:
    owners = db.fetch_all("owners", {"id": owner_id})
    return owners[0] if owners else None


def _validate_agent_limit(owner: dict[str, Any], existing_agents: list[dict[str, Any]]) -> None:
    plan_limits = {
        "personal": 4,
        "starter": 1,
        "professional": 5,
        "team": 10,
    }
    plan = str(owner.get("plan") or "personal").lower()
    limit = plan_limits.get(plan, 4)
    if len(existing_agents) >= limit:
        raise ValueError(f"Owner has reached the agent limit for the '{plan}' plan ({limit}).")


def _choose_phone_number(area_code: str | None = None) -> dict[str, Any]:
    numbers = get_available_numbers(area_code)
    if not numbers:
        raise ValueError("No phone number is available. Add TWILIO_PHONE_NUMBER or enable Twilio number search.")
    return numbers[0]


def _normalize_e164(value: str | None) -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


def _validate_identity_inputs(agent_name: str, role: str) -> None:
    cleaned_name = str(agent_name or "").strip()
    cleaned_role = str(role or "").strip()
    if len(cleaned_name) < 2:
        raise ValueError("Agent name must be at least 2 characters.")
    if len(cleaned_role) < 2:
        raise ValueError("Agent role must be at least 2 characters.")
    if not re.search(r"[a-zA-Z]", cleaned_name):
        raise ValueError("Agent name must include letters.")


def _ensure_unique_owner_email(db: SupabaseService, owner_id: str, base_email: str) -> str:
    existing_agents = db.fetch_all("agents", {"owner_id": owner_id})
    existing_emails = {str(a.get("email_address") or "").strip().lower() for a in existing_agents}
    if base_email.lower() not in existing_emails:
        return base_email

    local, sep, domain = base_email.partition("@")
    for index in range(2, 100):
        candidate = f"{local}.{index}{sep}{domain}"
        if candidate.lower() not in existing_emails:
            return candidate
    raise ValueError("Could not generate a unique email alias for this agent.")


def provision_agent(
    owner_id: str,
    agent_name: str,
    role: str,
    brain_provider: str,
    brain_api_key: str | None = None,
    persona: str | None = None,
    owner_phone_number: str | None = None,
) -> dict[str, Any]:
    """Creates an agent identity package and stores it in the database."""
    _validate_identity_inputs(agent_name=agent_name, role=role)

    settings = get_settings()
    db = SupabaseService()

    owner = _get_owner_record(db, owner_id)
    if not owner:
        raise ValueError("Owner not found. Create or import the owner record before provisioning an agent.")

    existing_agents = db.fetch_all("agents", {"owner_id": owner_id})
    _validate_agent_limit(owner, existing_agents)

    business_address = owner.get("business_address") or owner.get("address")
    area_code = None
    phone_seed = (owner_phone_number or owner.get("phone") or "").strip()
    digits = "".join(ch for ch in phone_seed if ch.isdigit())
    if len(digits) >= 10:
        area_code = digits[-10:-7]

    selected_number = _choose_phone_number(area_code)
    normalized_agent_phone = _normalize_e164(selected_number["phone_number"])
    if not normalized_agent_phone:
        raise ValueError("A valid agent phone number could not be provisioned.")

    email_identity = create_agent_email(agent_name, settings.platform_domain)
    unique_email = _ensure_unique_owner_email(db=db, owner_id=owner_id, base_email=email_identity["email_address"])

    payload = {
        "owner_id": owner_id,
        "name": agent_name.strip(),
        "agent_type": role.strip(),
        "phone_number": normalized_agent_phone,
        "email_address": unique_email,
        "api_key": brain_api_key,
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    agent = db.insert_one("agents", payload)
    assign_number(str(agent.get("id")), normalized_agent_phone)

    # Keep identity profile table in sync when available.
    try:
        db.client.table("agent_identity_profiles").upsert(
            {
                "owner_id": owner_id,
                "agent_slug": str(agent.get("agent_type") or role).strip().lower(),
                "agent_name": agent_name.strip(),
                "communication_voice": "direct and practical",
                "autonomy_baseline": 5,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="owner_id,agent_slug",
        ).execute()
    except Exception:
        pass

    log_activity(
        agent_id=str(agent.get("id")),
        action_type="agent_provisioned",
        description=f"Provisioned {agent_name} as {role} with {selected_number['phone_number']}",
        outcome="success",
        cost_cents=0,
    )

    recipient = owner_phone_number or owner.get("phone")
    recipient = _normalize_e164(recipient)
    sms_result = None
    if recipient:
        try:
            sms_result = send_sms(
                to=recipient,
                message=(
                    f"Your agent {agent_name} is now online. "
                    f"Phone: {normalized_agent_phone} | "
                    f"Email: {unique_email} | "
                    f"Role: {role} | Brain: {brain_provider}"
                ),
            )
        except Exception as error:
            sms_result = {"success": False, "error": str(error)}

    return {
        "agent_id": str(agent.get("id")),
        "name": agent_name,
        "phone": normalized_agent_phone,
        "email": unique_email,
        "role": role,
        "status": "active" if agent.get("is_active", True) else "inactive",
        "business_address": business_address,
        "provisioned_at": str(agent.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "number_source": selected_number.get("source"),
        "identity_quality": "complete",
        "welcome_sms": sms_result,
    }


def deprovision_agent(agent_id: str) -> dict[str, Any]:
    """Marks an agent as deprovisioned and archives outgoing activity."""
    db = SupabaseService()
    agents = db.fetch_all("agents", {"id": agent_id})
    if not agents:
        raise ValueError("Agent not found.")

    updated_rows = db.update_many(
        "agents",
        {"id": agent_id},
        {"status": "deprovisioned", "updated_at": datetime.now(timezone.utc).isoformat()},
    )
    updated_agent = updated_rows[0] if updated_rows else agents[0]

    log_activity(
        agent_id=agent_id,
        action_type="agent_deprovisioned",
        description=f"Deprovisioned agent {updated_agent.get('name', agent_id)}",
        outcome="success",
        cost_cents=0,
    )

    return {
        "agent_id": agent_id,
        "status": updated_agent.get("status", "deprovisioned"),
        "phone": updated_agent.get("phone_number"),
        "email": updated_agent.get("email_address"),
    }
