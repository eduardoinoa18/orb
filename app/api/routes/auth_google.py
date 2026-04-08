"""Google OAuth routes for owner-scoped integrations."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from integrations import google_client

router = APIRouter(prefix="/auth/google", tags=["auth-google"])


@router.get("/start")
def auth_google_start(owner_id: str) -> RedirectResponse:
    """Redirect owner to Google OAuth consent screen."""
    if not owner_id.strip():
        raise HTTPException(status_code=400, detail="owner_id is required")
    try:
        auth_url = google_client.get_auth_url(owner_id=owner_id.strip())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not generate Google authorization URL: {exc}. "
                "Check GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
            ),
        ) from exc
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/callback")
def auth_google_callback(code: str, state: str) -> RedirectResponse:
    """Handle Google redirect callback and persist owner tokens."""
    if not code.strip():
        raise HTTPException(status_code=400, detail="Missing Google code parameter.")
    if not state.strip():
        raise HTTPException(status_code=400, detail="Missing Google state parameter.")

    try:
        result = google_client.handle_callback(code=code.strip(), state=state.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google callback failed: {exc}") from exc

    query = urlencode(
        {
            "google_connected": "true",
            "owner_id": result.get("owner_id") or "",
            "email": result.get("email") or "",
        }
    )
    return RedirectResponse(url=f"/dashboard/integrations?{query}", status_code=302)
