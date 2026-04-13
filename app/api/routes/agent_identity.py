"""Agent Identity & Autonomy Governance API.

Enables per-agent persistent identity, learned preferences evolution, and owner-scoped autonomy rules.
This is a core differentiator: agents develop identity within owner workspaces, learn from interactions,
and enforce transparent approval workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService

router = APIRouter(prefix="/agent-identity", tags=["Agent Identity"])


class AgentIdentityProfilePayload(BaseModel):
    """Payload to create or update agent identity within owner workspace."""
    owner_id: str = Field(min_length=2)
    agent_slug: str = Field(min_length=2)
    agent_name: str = Field(min_length=2)
    personality_archetype: str = Field(default="professional")
    communication_voice: str | None = None
    autonomy_baseline: int = Field(default=5, ge=1, le=10)


class AgentMemoryContextPayload(BaseModel):
    """Persist agent learning/preferences as isolated memory contexts per owner."""
    owner_id: str = Field(min_length=2)
    agent_slug: str = Field(min_length=2)
    memory_type: str = Field(pattern="^(learning|preference|context|interaction)$")
    memory_payload: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = Field(default=0.75, ge=0.0, le=1.0)
    ttl_hours: int | None = None


class AgentAutonomyRulePayload(BaseModel):
    """Define per-agent autonomy rules and approval workflows."""
    owner_id: str = Field(min_length=2)
    agent_slug: str = Field(min_length=2)
    rule_type: str = Field(pattern="^(action_type|budget_gate|data_risk|approval_required)$")
    action_category: str = Field(min_length=2)
    autonomy_level: int = Field(default=5, ge=1, le=10)
    requires_approval: bool = False
    notification_channel: str = Field(default="in_app", pattern="^(in_app|email|sms|slack)$")


class AgentCollaborationPayload(BaseModel):
    """Log agent-to-agent collaboration for orchestration insights."""
    owner_id: str = Field(min_length=2)
    initiating_agent_slug: str = Field(min_length=2)
    collaborating_agents: list[str] = Field(default_factory=list)
    task_description: str | None = None
    outcome: str | None = None
    coordination_pattern: str | None = None
    success: bool = False


def _get_db() -> SupabaseService:
    """Get database service."""
    return SupabaseService()


@router.post("/profile")
def create_agent_identity(payload: AgentIdentityProfilePayload) -> dict[str, Any]:
    """Create or update persistent agent identity within owner workspace."""
    try:
        db = _get_db()
        data = {
            "owner_id": payload.owner_id,
            "agent_slug": payload.agent_slug,
            "agent_name": payload.agent_name,
            "personality_archetype": payload.personality_archetype,
            "communication_voice": payload.communication_voice,
            "autonomy_baseline": payload.autonomy_baseline,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try to insert; on conflict update
        try:
            db.insert_one("agent_identity_profiles", data)
        except DatabaseConnectionError:
            db.update_many(
                "agent_identity_profiles",
                {"owner_id": payload.owner_id, "agent_slug": payload.agent_slug},
                data,
            )

        return {
            "status": "created",
            "owner_id": payload.owner_id,
            "agent_slug": payload.agent_slug,
            "identity": data,
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/profile/{owner_id}/{agent_slug}")
def get_agent_identity(owner_id: str, agent_slug: str) -> dict[str, Any]:
    """Retrieve agent identity profile and evolved traits."""
    try:
        db = _get_db()
        rows = db.fetch_all(
            "agent_identity_profiles",
            {"owner_id": owner_id, "agent_slug": agent_slug},
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not rows:
        raise HTTPException(status_code=404, detail="Agent identity not found.")

    profile = rows[0]
    return {
        "owner_id": owner_id,
        "agent_slug": agent_slug,
        "name": profile.get("agent_name"),
        "archetype": profile.get("personality_archetype"),
        "voice": profile.get("communication_voice"),
        "baseline_autonomy": profile.get("autonomy_baseline"),
        "evolved_traits": profile.get("evolved_traits") or {},
        "interaction_count": profile.get("interaction_count", 0),
        "last_interaction": profile.get("last_interaction_at"),
    }


@router.post("/memory")
def record_agent_memory(payload: AgentMemoryContextPayload) -> dict[str, Any]:
    """Record agent learning/preference memory isolated per owner."""
    try:
        db = _get_db()
        expires_at = None
        if payload.ttl_hours:
            from datetime import timedelta
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=payload.ttl_hours)).isoformat()

        data = {
            "owner_id": payload.owner_id,
            "agent_slug": payload.agent_slug,
            "memory_type": payload.memory_type,
            "memory_payload": payload.memory_payload,
            "relevance_score": payload.relevance_score,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.insert_one("agent_memory_contexts", data)
        return {
            "status": "recorded",
            "memory_id": data.get("id"),
            "type": payload.memory_type,
            "expires_at": expires_at,
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/memory/{owner_id}/{agent_slug}")
def list_agent_memory(
    owner_id: str,
    agent_slug: str,
    memory_type: str | None = None,
) -> dict[str, Any]:
    """Retrieve agent memory contexts with highest relevance first."""
    try:
        db = _get_db()
        filters: dict[str, Any] = {"owner_id": owner_id, "agent_slug": agent_slug}
        if memory_type:
            filters["memory_type"] = memory_type

        rows = db.fetch_all("agent_memory_contexts", filters)
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    # Sort by relevance descending, filter expired
    now = datetime.now(timezone.utc)
    valid = [
        r for r in rows
        if not r.get("expires_at") or datetime.fromisoformat(r["expires_at"]) > now
    ]
    valid.sort(key=lambda x: float(x.get("relevance_score") or 0), reverse=True)

    return {
        "owner_id": owner_id,
        "agent_slug": agent_slug,
        "memory_count": len(valid),
        "memories": valid[:20],  # Return top 20 by relevance
    }


@router.post("/autonomy-rule")
def create_autonomy_rule(payload: AgentAutonomyRulePayload) -> dict[str, Any]:
    """Create agent autonomy governance rule for owner workspace."""
    try:
        db = _get_db()
        data = {
            "owner_id": payload.owner_id,
            "agent_slug": payload.agent_slug,
            "rule_type": payload.rule_type,
            "action_category": payload.action_category,
            "autonomy_level": payload.autonomy_level,
            "requires_approval": payload.requires_approval,
            "notification_channel": payload.notification_channel,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.insert_one("agent_autonomy_rules", data)
        return {"status": "created", "rule": data}
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/autonomy-rules/{owner_id}/{agent_slug}")
def list_autonomy_rules(owner_id: str, agent_slug: str) -> dict[str, Any]:
    """List all autonomy rules for a specific agent in owner workspace."""
    try:
        db = _get_db()
        rows = db.fetch_all(
            "agent_autonomy_rules",
            {"owner_id": owner_id, "agent_slug": agent_slug, "enabled": True},
        )
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "owner_id": owner_id,
        "agent_slug": agent_slug,
        "rule_count": len(rows),
        "rules": rows,
    }


@router.post("/collaboration")
def log_collaboration(payload: AgentCollaborationPayload) -> dict[str, Any]:
    """Log multi-agent collaboration for orchestration insights."""
    try:
        db = _get_db()
        data = {
            "owner_id": payload.owner_id,
            "initiating_agent_slug": payload.initiating_agent_slug,
            "collaborating_agents": payload.collaborating_agents,
            "task_description": payload.task_description,
            "outcome": payload.outcome,
            "coordination_pattern": payload.coordination_pattern,
            "success": payload.success,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.insert_one("agent_collaboration_events", data)
        return {"status": "logged", "success_rate": "tracked"}
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/collaboration-stats/{owner_id}")
def collaboration_statistics(owner_id: str) -> dict[str, Any]:
    """Get agent collaboration orchestration statistics for owner."""
    try:
        db = _get_db()
        rows = db.fetch_all("agent_collaboration_events", {"owner_id": owner_id})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not rows:
        return {
            "owner_id": owner_id,
            "total_collaborations": 0,
            "success_rate": 0.0,
            "top_agent_pairs": [],
        }

    successful = sum(1 for r in rows if r.get("success"))
    success_rate = (successful / len(rows) * 100) if rows else 0.0

    # Extract most common agent pairs
    pair_counts: dict[str, int] = {}
    for row in rows:
        initiator = str(row.get("initiating_agent_slug") or "")
        collaborators = row.get("collaborating_agents") or []
        for collab in collaborators:
            pair_key = tuple(sorted([initiator, str(collab)]))
            pair_counts[str(pair_key)] = pair_counts.get(str(pair_key), 0) + 1

    top_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "owner_id": owner_id,
        "total_collaborations": len(rows),
        "successful": successful,
        "success_rate": round(success_rate, 2),
        "top_agent_pairs": top_pairs,
    }
