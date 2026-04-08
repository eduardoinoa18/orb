"""Authentication routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
def auth_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "auth route ready"}

