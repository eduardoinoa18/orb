"""Trading (Orion) routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/status")
def trading_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "trading route ready"}

