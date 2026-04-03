"""Addendum endpoints for generalized Rex learning workflows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.rex.rex_brain import RexBrain

router = APIRouter(prefix="/agents/rex", tags=["rex"])
rex_brain = RexBrain()


class RexLearnOwnerRequest(BaseModel):
    owner_id: str
    product_description: str = Field(min_length=10)
    ideal_customer_profile: str = Field(min_length=10)
    common_objections: list[str] = Field(default_factory=list)
    successful_close_examples: list[str] = Field(default_factory=list)


class RexLearnOutcomesRequest(BaseModel):
    owner_id: str


@router.get("/status")
def rex_status() -> dict[str, str]:
    """Health check for Rex addendum routes."""
    return {"status": "rex addendum routes ready"}


@router.post("/learn-owner")
def rex_learn_owner(payload: RexLearnOwnerRequest) -> dict[str, Any]:
    """Teaches Rex what the owner sells and how buyers respond."""
    try:
        return rex_brain.learn_from_owner(
            owner_id=payload.owner_id,
            product_description=payload.product_description,
            ideal_customer_profile=payload.ideal_customer_profile,
            common_objections=payload.common_objections,
            successful_close_examples=payload.successful_close_examples,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/learn-outcomes")
def rex_learn_outcomes(payload: RexLearnOutcomesRequest) -> dict[str, Any]:
    """Runs Rex weekly self-review proof-of-concept for this owner."""
    try:
        return rex_brain.learn_from_outcomes(owner_id=payload.owner_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
