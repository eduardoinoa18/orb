"""Identity provisioning routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/status")
def identity_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "identity route ready"}

