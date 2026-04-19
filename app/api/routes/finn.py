"""Finn — Finance & Bookkeeping API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agents.finn.finn_brain import FinnBrain

router = APIRouter(prefix="/finn", tags=["finn"])
logger = logging.getLogger("orb.routes.finn")

_brain: FinnBrain | None = None


def _get_brain() -> FinnBrain:
    global _brain
    if _brain is None:
        _brain = FinnBrain()
    return _brain


# ── Pydantic models ────────────────────────────────────────────────────────

class ChatPayload(BaseModel):
    owner_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class TransactionPayload(BaseModel):
    owner_id: str
    amount: float = Field(gt=0)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=500)
    txn_type: str = Field(default="expense", pattern="^(income|expense)$")
    date: str | None = None  # YYYY-MM-DD format


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(gt=0)


class CreateInvoicePayload(BaseModel):
    owner_id: str
    client_name: str = Field(min_length=1)
    client_email: str = Field(min_length=5)
    line_items: list[InvoiceLineItem] = Field(min_length=1)
    due_days: int = Field(default=30, ge=1, le=365)
    notes: str = Field(default="", max_length=2000)


class MarkPaidPayload(BaseModel):
    invoice_id: str
    payment_reference: str = ""


# ── Chat ────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def finn_chat(payload: ChatPayload) -> dict[str, Any]:
    """Chat with Finn about finances, invoices, or bookkeeping."""
    brain = _get_brain()
    return brain.chat(owner_id=payload.owner_id, message=payload.message, context=payload.context)


# ── Bookkeeping ─────────────────────────────────────────────────────────────

@router.post("/transactions/log")
async def log_transaction(payload: TransactionPayload) -> dict[str, Any]:
    """Log a financial transaction."""
    brain = _get_brain()
    return brain.log_transaction(
        owner_id=payload.owner_id,
        amount=payload.amount,
        category=payload.category,
        description=payload.description,
        txn_type=payload.txn_type,
        date=payload.date,
    )


@router.post("/transactions/categorize")
async def categorize_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    """AI-categorize a transaction from description and amount."""
    brain = _get_brain()
    return brain.categorize_transaction(
        description=str(payload.get("description", "")),
        amount=float(payload.get("amount", 0)),
    )


@router.get("/snapshot/{owner_id}")
async def get_snapshot(owner_id: str, month: str | None = None) -> dict[str, Any]:
    """Get monthly income/expense snapshot."""
    brain = _get_brain()
    return brain.get_monthly_snapshot(owner_id=owner_id, month=month)


@router.get("/report/pl/{owner_id}")
async def get_pl_report(owner_id: str, period: str = "monthly") -> dict[str, Any]:
    """Get P&L report with AI narrative."""
    brain = _get_brain()
    return brain.generate_pl_report(owner_id=owner_id, period=period)


@router.get("/report/expenses/{owner_id}")
async def get_expense_report(owner_id: str) -> dict[str, Any]:
    """Get tax-ready expense report by category."""
    brain = _get_brain()
    return brain.generate_expense_report(owner_id)


# ── Invoicing ────────────────────────────────────────────────────────────────

@router.post("/invoices/create")
async def create_invoice(payload: CreateInvoicePayload) -> dict[str, Any]:
    """Create a new invoice."""
    brain = _get_brain()
    return brain.create_invoice(
        owner_id=payload.owner_id,
        client_name=payload.client_name,
        client_email=payload.client_email,
        line_items=[item.model_dump() for item in payload.line_items],
        due_days=payload.due_days,
        notes=payload.notes,
    )


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: str) -> dict[str, Any]:
    """Send an invoice to the client."""
    brain = _get_brain()
    return brain.send_invoice(invoice_id)


@router.post("/invoices/mark-paid")
async def mark_invoice_paid(payload: MarkPaidPayload) -> dict[str, Any]:
    """Mark an invoice as paid."""
    brain = _get_brain()
    return brain.mark_invoice_paid(
        invoice_id=payload.invoice_id,
        payment_ref=payload.payment_reference,
    )


@router.post("/invoices/reminders/{owner_id}")
async def send_reminders(owner_id: str) -> dict[str, Any]:
    """Send payment reminders for all overdue invoices."""
    brain = _get_brain()
    return brain.send_payment_reminders(owner_id)


@router.get("/invoices/{owner_id}")
async def list_invoices(owner_id: str, status: str = "all") -> dict[str, Any]:
    """List invoices for an owner."""
    brain = _get_brain()
    return brain.get_invoice_list(owner_id=owner_id, status=status)


# ── Digest ────────────────────────────────────────────────────────────────────

@router.post("/digest/{owner_id}")
async def weekly_finance_digest(owner_id: str) -> dict[str, Any]:
    """Generate and push weekly finance digest to Commander inbox."""
    brain = _get_brain()
    return brain.run_weekly_finance_digest(owner_id)


@router.get("/advice/{owner_id}")
async def get_cash_flow_advice(owner_id: str) -> dict[str, str]:
    """Get AI-powered cash flow advice."""
    brain = _get_brain()
    advice = brain.get_cash_flow_advice(owner_id)
    return {"advice": advice}
