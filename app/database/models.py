"""Simple Pydantic models for ORB database records.

These models are lightweight and mainly help us keep request and response
shapes consistent while the project is still in its early stages.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OwnerRecord(BaseModel):
    """Represents a platform owner."""

    id: UUID | None = None
    email: str
    full_name: str
    business_name: str | None = None
    address: str | None = None
    plan: str
    spend_limit_cents: int = 0
    created_at: datetime | None = None


class AgentRecord(BaseModel):
    """Represents an AI agent record."""

    id: UUID | None = None
    owner_id: UUID | None = None
    name: str
    role: str
    phone_number: str | None = None
    email_address: str | None = None
    brain_provider: str
    brain_api_key: str | None = Field(default=None, repr=False)
    status: str = "active"
    trust_score: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ActivityLogRecord(BaseModel):
    """Represents an activity log entry."""

    id: UUID | None = None
    agent_id: UUID | None = None
    action_type: str
    description: str
    outcome: str | None = None
    cost_cents: int = 0
    needs_approval: bool = False
    approved: bool | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None


class LeadRecord(BaseModel):
    """Represents a wholesale lead."""

    id: UUID | None = None
    agent_id: UUID | None = None
    contact_name: str
    phone: str | None = None
    email: str | None = None
    property_address: str | None = None
    motivation_score: int | None = None
    status: str = "new"
    last_contact: datetime | None = None
    notes: str | None = None
    created_at: datetime | None = None


class TradeRecord(BaseModel):
    """Represents a trading record."""

    id: UUID | None = None
    agent_id: UUID | None = None
    instrument: str
    direction: str
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    pnl_dollars: Decimal | None = None
    setup_name: str | None = None
    confidence_score: int | None = None
    status: str = "pending_approval"
    approved_by_human: bool = False
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None


class StrategyRecord(BaseModel):
    """Represents a stored strategy."""

    id: UUID | None = None
    agent_id: UUID | None = None
    name: str
    description: str | None = None
    rules_json: dict[str, Any] = Field(default_factory=dict)
    source_trader: str | None = None
    win_rate: Decimal | None = None
    is_active: bool = True
    created_at: datetime | None = None
