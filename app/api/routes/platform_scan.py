"""Platform Scan API — Trigger and read platform health scans.

Exposes the PlatformScanner engine as REST endpoints so:
  - Eduardo's Commander can trigger a manual scan
  - The admin dashboard can show the latest scan results
  - Railway cron jobs can trigger scheduled scans via HTTP
  - The scan results are visible in the platform-tasks dashboard

Endpoints:
  POST   /platform-scan/run          — trigger a full scan (admin only or cron key)
  GET    /platform-scan/latest       — get the most recent scan results
  GET    /platform-scan/health       — quick integration health check
  POST   /platform-scan/notify       — push urgent digest to WhatsApp/Telegram
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.platform_scan_api")

router = APIRouter(prefix="/platform-scan", tags=["Platform Scan"])

_CRON_KEY_ENV = "ORB_CRON_SECRET"


def _require_auth(request: Request, cron_key: Optional[str] = None) -> bool:
    """Accepts either admin JWT or a Railway cron secret key."""
    # Check cron key first (for Railway scheduled jobs)
    expected_cron = os.environ.get(_CRON_KEY_ENV, "")
    if expected_cron and cron_key == expected_cron:
        return True

    # Fall back to JWT admin check
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SupabaseService()
        rows = db.client.table("business_profiles") \
            .select("is_platform_admin") \
            .eq("owner_id", owner_id) \
            .limit(1) \
            .execute()
        if rows.data and rows.data[0].get("is_platform_admin"):
            return True
        # Superadmin fallback
        owner_rows = db.client.table("owners") \
            .select("role,is_superadmin") \
            .eq("id", owner_id) \
            .limit(1) \
            .execute()
        if owner_rows.data:
            row = owner_rows.data[0]
            if bool(row.get("is_superadmin")) or str(row.get("role", "")).lower() in {"superadmin", "admin"}:
                return True
    except Exception:
        pass

    raise HTTPException(status_code=403, detail="Platform admin access required")


@router.post("/run")
async def run_scan(
    request: Request,
    cron_key: Optional[str] = Query(None),
    notify: bool = Query(False),
):
    """Triggers a full platform scan and returns the results.

    Can be called by:
      - Admin Commander tool: POST /platform-scan/run (JWT)
      - Railway cron job: POST /platform-scan/run?cron_key=YOUR_CRON_SECRET
      - Manual testing

    Set notify=true to also push to WhatsApp/Telegram if urgency is high.
    """
    _require_auth(request, cron_key)
    try:
        from agents.platform_scan import PlatformScanner
        scanner = PlatformScanner()
        scan = scanner.run_full_scan()
        scanner.push_digest_to_commander(scan)
        if notify and scan.get("urgency_score", 0) >= 5:
            scanner.push_urgent_notification(scan)
        return {
            "status": "completed",
            "scanned_at": scan.get("scanned_at"),
            "urgency_score": scan.get("urgency_score", 0),
            "needs_attention": scan.get("needs_attention", False),
            "summary": {
                "pending_requests": scan.get("requests", {}).get("total", 0),
                "urgent_requests": scan.get("requests", {}).get("urgent", 0),
                "tasks_needs_review": scan.get("code_tasks", {}).get("needs_review", 0),
                "stale_tasks": scan.get("code_tasks", {}).get("stale", 0),
                "unread_messages": scan.get("unread_messages", {}).get("total", 0),
                "integrations_healthy": scan.get("integrations", {}).get("all_healthy", False),
                "failed_integrations": scan.get("integrations", {}).get("failed", []),
            },
            "full_scan": scan,
        }
    except Exception as e:
        logger.error("Platform scan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_scan(request: Request):
    """Returns the most recent scan digest from Commander's agent_messages inbox."""
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        db = SupabaseService()
        rows = db.client.table("agent_messages") \
            .select("*") \
            .eq("to_owner_id", owner_id) \
            .eq("message_type", "platform_digest") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if not rows.data:
            return {"digest": None, "message": "No scans run yet. Run POST /platform-scan/run to start."}
        return {"digest": rows.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def integration_health(request: Request):
    """Returns current integration health without running a full scan."""
    payload = getattr(request.state, "token_payload", {}) or {}
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from agents.platform_scan import PlatformScanner
        scanner = PlatformScanner()
        health = scanner.scan_integration_health()
        stats = scanner.scan_platform_stats()
        return {
            "integrations": health,
            "platform_stats": stats,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notify")
async def push_notification(
    request: Request,
    cron_key: Optional[str] = Query(None),
):
    """Pushes an urgent digest to WhatsApp/Telegram if configured.

    Runs a quick scan and sends the digest regardless of urgency score.
    """
    _require_auth(request, cron_key)
    try:
        from agents.platform_scan import PlatformScanner
        scanner = PlatformScanner()
        scan = scanner.run_full_scan()
        digest = scanner.build_digest_message(scan)
        sent = scanner.push_urgent_notification(scan)
        return {
            "status": "sent" if sent else "queued",
            "digest_preview": digest[:500],
            "urgency_score": scan.get("urgency_score", 0),
        }
    except Exception as e:
        logger.error("Platform notification failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
