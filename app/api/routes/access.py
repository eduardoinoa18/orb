"""Access and role context routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.security.access_control import mark_master_owner, require_roles, resolve_request_role

router = APIRouter(prefix="/access", tags=["access"])


class MasterOwnerPayload(BaseModel):
    owner_id: str = Field(min_length=2)


@router.get("/context")
def access_context(request: Request) -> dict[str, Any]:
    role = resolve_request_role(request)
    payload = getattr(request.state, "token_payload", {}) or {}
    return {
        "role": role,
        "owner_id": payload.get("owner_id"),
        "email": payload.get("email"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/bootstrap-master")
def access_bootstrap_master(payload: MasterOwnerPayload, request: Request) -> dict[str, Any]:
    require_roles(request, {"master_owner"})
    owner = mark_master_owner(payload.owner_id)
    return {
        "status": "ok",
        "owner_id": payload.owner_id,
        "owner": owner,
        "message": "Master owner privileges enabled and billing exemption applied.",
    }
