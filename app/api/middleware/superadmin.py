"""Authorization helpers for admin and superadmin access tiers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.database.connection import DatabaseConnectionError, SupabaseService


def get_current_owner(request: Request) -> dict[str, Any]:
    payload = getattr(request.state, "token_payload", None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Missing authenticated session.")

    owner_id = str(payload.get("owner_id") or payload.get("sub") or "").strip()
    email = str(payload.get("email") or payload.get("sub") or "").strip().lower()

    if not owner_id and not email:
        raise HTTPException(status_code=401, detail="Invalid auth token payload.")

    try:
        db = SupabaseService()
        owner: dict[str, Any] | None = None
        if owner_id:
            rows = db.fetch_all("owners", {"id": owner_id})
            if rows:
                owner = rows[0]
        if owner is None and email:
            rows = db.fetch_all("owners", {"email": email})
            if rows:
                owner = rows[0]
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if owner is None:
        raise HTTPException(status_code=404, detail="Owner account not found.")

    return owner


def require_superadmin(request: Request) -> dict[str, Any]:
    """Dependency that blocks non-superadmin owners."""
    owner = get_current_owner(request)
    role = str(owner.get("role") or "user").strip().lower()
    # Accept legacy "superadmin" DB role, is_superadmin flag, or JWT "master_owner" role
    jwt_role = str(getattr(request.state, "token_payload", {}).get("role") or "").strip().lower()
    is_admin = (
        bool(owner.get("is_superadmin"))
        or role in ("superadmin", "master_owner")
        or jwt_role in ("superadmin", "master_owner")
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Super admin access required.")
    return owner


def require_admin(request: Request) -> dict[str, Any]:
    """Allows superadmin and admin roles."""
    owner = get_current_owner(request)
    role = str(owner.get("role") or "user").strip().lower()
    if role not in {"superadmin", "admin"}:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return owner
