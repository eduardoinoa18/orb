"""Content (Nova) routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/status")
def content_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "content route ready"}

