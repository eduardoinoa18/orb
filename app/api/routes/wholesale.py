"""Wholesale routes for ORB.

Real lead intake endpoints arrive in Level 4. This placeholder simply proves
that the route module is correctly mounted.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/wholesale", tags=["wholesale"])


@router.get("/status")
def wholesale_routes_status() -> dict[str, str]:
    """Simple route to confirm the wholesale router is loaded."""
    return {"status": "wholesale router ready"}
