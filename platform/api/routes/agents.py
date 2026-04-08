"""Agent management routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status")
def agents_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "agents route ready"}

