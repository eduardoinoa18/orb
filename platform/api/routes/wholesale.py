"""Wholesale (Rex) routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/wholesale", tags=["wholesale"])


@router.get("/status")
def wholesale_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "wholesale route ready"}

