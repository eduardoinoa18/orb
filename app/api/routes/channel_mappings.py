"""Channel Mappings — Bidirectional Chat Platform Routing.

Maps external platform user IDs (WhatsApp numbers, Telegram chat IDs,
Discord user IDs, Instagram IGSIDs, etc.) to ORB owner_ids.

Every inbound webhook handler queries this table to determine which owner
a message belongs to and routes it to their Commander instance.

Endpoints:
  GET  /channel-mappings          — list all mappings for the authenticated owner
  POST /channel-mappings          — create or update a mapping
  DELETE /channel-mappings/{id}   — remove a mapping
  GET  /channel-mappings/resolve  — resolve an external_id → owner_id (internal use)
  GET  /channel-mappings/platforms — list configured platforms + deep-link URLs
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database.connection import SupabaseService
from config.settings import get_settings

logger = logging.getLogger("orb.channel_mappings")

router = APIRouter(prefix="/channel-mappings", tags=["Channel Mappings"])

SUPPORTED_PLATFORMS = {
    "whatsapp": {
        "name": "WhatsApp",
        "env_key": "TWILIO_WHATSAPP_NUMBER",
        "link_template": "https://wa.me/{id}?text=STATUS",
        "id_format": "E.164 phone number e.g. +15551234567",
    },
    "telegram": {
        "name": "Telegram",
        "env_key": "TELEGRAM_BOT_USERNAME",
        "link_template": "https://t.me/{id}",
        "id_format": "Bot username e.g. @YourBot",
    },
    "sms": {
        "name": "SMS",
        "env_key": "TWILIO_PHONE_NUMBER",
        "link_template": "sms:{id}?body=STATUS",
        "id_format": "E.164 phone number e.g. +15551234567",
    },
    "instagram": {
        "name": "Instagram",
        "env_key": "INSTAGRAM_USERNAME",
        "link_template": "https://ig.me/m/{id}",
        "id_format": "Business username e.g. @yourbusiness",
    },
    "messenger": {
        "name": "Messenger",
        "env_key": "FACEBOOK_PAGE_ID",
        "link_template": "https://m.me/{id}",
        "id_format": "Facebook Page ID",
    },
    "discord": {
        "name": "Discord",
        "env_key": "DISCORD_INVITE_URL",
        "link_template": "{id}",   # full URL stored
        "id_format": "Discord invite URL",
    },
    "teams": {
        "name": "Microsoft Teams",
        "env_key": "TEAMS_BOT_DEEPLINK",
        "link_template": "{id}",   # full URL stored
        "id_format": "Teams bot deep link URL",
    },
    "email": {
        "name": "Email",
        "env_key": "RESEND_FROM_EMAIL",
        "link_template": "mailto:{id}",
        "id_format": "Email address",
    },
}


# ─── Models ──────────────────────────────────────────────────────────────────

class MappingCreate(BaseModel):
    platform: str
    external_id: str
    label: Optional[str] = None


class MappingUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _require_owner(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return owner_id


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_mappings(request: Request):
    """List all channel mappings for the authenticated owner."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        rows = db.client.table("channel_mappings") \
            .select("*") \
            .eq("owner_id", owner_id) \
            .order("created_at", desc=False) \
            .execute()
        return {"mappings": rows.data or []}
    except Exception as e:
        logger.error(f"Failed to list channel mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def upsert_mapping(request: Request, body: MappingCreate):
    """Create or update a channel mapping.

    If a mapping for this platform+external_id already exists, it is updated.
    Otherwise a new mapping is created.
    """
    owner_id = _require_owner(request)

    if body.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform '{body.platform}'. Supported: {list(SUPPORTED_PLATFORMS)}"
        )

    try:
        db = SupabaseService()
        existing = (
            db.client.table("channel_mappings")
            .select("id")
            .eq("owner_id", owner_id)
            .eq("platform", body.platform)
            .limit(1)
            .execute()
        )
        payload = {
            "owner_id": owner_id,
            "platform": body.platform,
            "external_id": body.external_id.strip(),
            "label": body.label,
            "is_active": True,
        }

        if existing.data:
            result = (
                db.client.table("channel_mappings")
                .update(payload)
                .eq("id", existing.data[0]["id"])
                .eq("owner_id", owner_id)
                .execute()
            )
        else:
            result = db.client.table("channel_mappings").upsert(
                payload,
                on_conflict="platform,external_id"
            ).execute()
        return {"mapping": result.data[0] if result.data else None, "status": "ok"}
    except Exception as e:
        logger.error(f"Failed to upsert channel mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{mapping_id}")
async def update_mapping(request: Request, mapping_id: str, body: MappingUpdate):
    """Update label or active status of an existing mapping."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        updates: dict = {}
        if body.label is not None:
            updates["label"] = body.label
        if body.is_active is not None:
            updates["is_active"] = body.is_active
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = db.client.table("channel_mappings") \
            .update(updates) \
            .eq("id", mapping_id) \
            .eq("owner_id", owner_id) \
            .execute()
        return {"mapping": result.data[0] if result.data else None, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update channel mapping {mapping_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{mapping_id}")
async def delete_mapping(request: Request, mapping_id: str):
    """Remove a channel mapping."""
    owner_id = _require_owner(request)
    try:
        db = SupabaseService()
        db.client.table("channel_mappings") \
            .delete() \
            .eq("id", mapping_id) \
            .eq("owner_id", owner_id) \
            .execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Failed to delete channel mapping {mapping_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolve")
async def resolve_external_id(platform: str, external_id: str):
    """Internal: resolve an external platform user ID to an ORB owner_id.

    Called by inbound webhook handlers (not user-facing).
    Returns the owner_id or 404 if no mapping found.
    """
    try:
        db = SupabaseService()
        rows = db.client.table("channel_mappings") \
            .select("owner_id") \
            .eq("platform", platform) \
            .eq("external_id", external_id) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()
        if not rows.data:
            raise HTTPException(
                status_code=404,
                detail=f"No mapping found for {platform}:{external_id}"
            )
        return {"owner_id": rows.data[0]["owner_id"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve channel mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/platforms")
async def list_platforms(request: Request):
    """Return all supported platforms with their env-based identifiers
    and pre-built deep links for the Connect page.

    This lets the frontend pre-fill inputs from already-configured env vars.
    """
    owner_id = _require_owner(request)
    settings = get_settings()
    db = SupabaseService()
    mapping_rows = (
        db.client.table("channel_mappings")
        .select("platform,external_id,is_active")
        .eq("owner_id", owner_id)
        .eq("is_active", True)
        .execute()
    )
    mapping_by_platform = {
        row["platform"]: row["external_id"]
        for row in (mapping_rows.data or [])
        if row.get("platform") and row.get("external_id")
    }
    result = []
    for platform_id, meta in SUPPORTED_PLATFORMS.items():
        env_key = meta["env_key"].lower()
        env_val = settings.resolve(env_key, default="")
        identifier = mapping_by_platform.get(platform_id, env_val)
        deep_link = ""
        if identifier:
            clean = identifier.replace("+", "").replace(" ", "")
            deep_link = meta["link_template"].replace("{id}", clean)
        result.append({
            "id": platform_id,
            "name": meta["name"],
            "env_key": meta["env_key"],
            "configured": bool(identifier),
            "identifier": identifier,
            "deep_link": deep_link,
            "id_format": meta["id_format"],
        })
    return {"platforms": result}
