"""Assistant (Aria) routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status")
def assistant_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "assistant route ready"}

