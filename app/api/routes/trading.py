"""Trading routes for ORB.

Real trading endpoints arrive in Level 3. This placeholder keeps the structure
ready without exposing unfinished behavior.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/status")
def trading_routes_status() -> dict[str, str]:
    """Simple route to confirm the trading router is loaded."""
    return {"status": "trading router ready"}
