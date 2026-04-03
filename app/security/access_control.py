"""Role access helpers for request-time authorization checks."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.database.connection import DatabaseConnectionError, SupabaseService
from config.settings import get_settings

_ALLOWED_ROLES = {"master_owner", "admin", "standard_user"}


def resolve_request_role(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    role = str(payload.get("role") or "").strip().lower()
    email = str(payload.get("email") or "").strip().lower()
    if email and email == get_settings().my_email.strip().lower():
        return "master_owner"
    if role in _ALLOWED_ROLES:
        return role
    return "standard_user"


def require_roles(request: Request, allowed: set[str]) -> str:
    payload = getattr(request.state, "token_payload", None)
    if payload is None:
        raise HTTPException(status_code=401, detail="Missing authenticated session.")

    role = resolve_request_role(request)
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{role}' is not allowed for this action.")
    return role


def mark_master_owner(owner_id: str) -> dict[str, Any]:
    try:
        db = SupabaseService()
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    updates = {"role": "master_owner", "billing_exempt": True}
    rows = db.update_many("owners", {"id": owner_id}, updates)
    if rows:
        return rows[0]
    return {"id": owner_id, **updates}
