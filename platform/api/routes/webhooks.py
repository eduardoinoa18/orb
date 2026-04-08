"""Webhook routes placeholder for Level 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/status")
def webhooks_status() -> dict[str, str]:
	"""Simple status endpoint for early integration checks."""
	return {"status": "webhooks route ready"}

