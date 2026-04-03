"""Agent routes for ORB."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.identity.provisioner import deprovision_agent, provision_agent
from app.database.activity_log import get_recent_activity
from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.twilio_client import send_sms

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentProvisionRequest(BaseModel):
    owner_id: str
    agent_name: str
    role: str
    brain_provider: str = "claude"
    brain_api_key: str | None = None
    persona: str | None = None
    owner_phone_number: str | None = None


class AgentSmsRequest(BaseModel):
    to: str
    message: str


@router.get("/status")
def agent_routes_status() -> dict[str, str]:
    """Simple route to confirm the agents router is loaded."""
    return {"status": "agents router ready"}


@router.post("/provision")
def provision_agent_route(payload: AgentProvisionRequest) -> dict[str, Any]:
    """Provision a new agent identity package for an owner."""
    try:
        return provision_agent(
            owner_id=payload.owner_id,
            agent_name=payload.agent_name,
            role=payload.role,
            brain_provider=payload.brain_provider,
            brain_api_key=payload.brain_api_key,
            persona=payload.persona,
            owner_phone_number=payload.owner_phone_number,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("")
def list_agents(owner_id: str | None = None) -> dict[str, Any]:
    """Returns all agents, optionally filtered by owner."""
    db = SupabaseService()
    filters = {"owner_id": owner_id} if owner_id else None
    agents = db.fetch_all("agents", filters)
    return {"agents": agents, "count": len(agents)}


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    """Returns one agent plus recent activity."""
    db = SupabaseService()
    rows = db.fetch_all("agents", {"id": agent_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Agent not found.")
    agent = rows[0]
    agent["recent_activity"] = get_recent_activity(agent_id=agent_id, limit=10)
    return agent


@router.get("/{agent_id}/activity")
def get_agent_activity(agent_id: str, limit: int = 25) -> dict[str, Any]:
    """Returns recent activity log rows for an agent."""
    activity = get_recent_activity(agent_id=agent_id, limit=limit)
    return {"activity": activity, "count": len(activity)}


@router.put("/{agent_id}/pause")
def pause_agent(agent_id: str) -> dict[str, Any]:
    """Pauses an agent from taking new outgoing actions."""
    db = SupabaseService()
    rows = db.update_many("agents", {"id": agent_id}, {"status": "paused"})
    if not rows:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"agent_id": agent_id, "status": "paused"}


@router.put("/{agent_id}/resume")
def resume_agent(agent_id: str) -> dict[str, Any]:
    """Resumes an agent after a pause."""
    db = SupabaseService()
    rows = db.update_many("agents", {"id": agent_id}, {"status": "active"})
    if not rows:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"agent_id": agent_id, "status": "active"}


@router.delete("/{agent_id}")
def delete_agent(agent_id: str) -> dict[str, Any]:
    """Deprovisions an agent identity."""
    try:
        return deprovision_agent(agent_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{agent_id}/sms")
def send_agent_sms(agent_id: str, payload: AgentSmsRequest) -> dict[str, Any]:
    """Send an SMS using the agent's assigned phone number."""
    db = SupabaseService()
    rows = db.fetch_all("agents", {"id": agent_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Agent not found.")
    agent = rows[0]
    if agent.get("status") != "active":
        raise HTTPException(status_code=400, detail="Agent is not active.")

    try:
        result = send_sms(
            to=payload.to,
            message=payload.message,
            from_number=agent.get("phone_number") or None,
        )
        return {"agent_id": agent_id, "result": result}
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
