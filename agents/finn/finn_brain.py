"""Finn — Finance & Bookkeeping Agent.

Finn handles the financial side of every owner's business:
  - Tracks income, expenses, and categorizes transactions
  - Creates and sends professional invoices
  - Sends automated payment reminders
  - Generates P&L summaries and cash flow snapshots
  - Prepares tax-ready expense reports
  - Connects to QuickBooks, Wave, FreshBooks (via integrations)

Business rationale: Most small business owners hate doing their books.
Finn makes it painless, proactive, and accurate — turning financial
chaos into clear weekly snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.finn.bookkeeping_engine import BookkeepingEngine
from agents.finn.invoice_tracker import InvoiceTracker
from agents.self_improvement import AgentSelfImprovement
from agents.skill_engine import AgentSkillEngine
from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.finn")


class FinnBrain(AgentSelfImprovement, AgentSkillEngine):
    """Finance and bookkeeping brain — precise, organized, proactive."""

    agent_slug = "finn"

    def __init__(self) -> None:
        AgentSelfImprovement.__init__(self)
        AgentSkillEngine.__init__(self)
        self.db = SupabaseService()
        self.books = BookkeepingEngine()
        self.invoices = InvoiceTracker()

    # ── Core conversation handler ─────────────────────────────────────────

    def chat(self, owner_id: str, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Handle a finance-related owner query."""
        ctx = context or {}
        summary = self.books.get_monthly_snapshot(owner_id)
        skill_ctx = self.build_skill_context(owner_id)

        system = (
            "You are Finn, ORB's Finance & Bookkeeping Agent. You are precise, organized, and "
            "make finance feel easy. You help business owners understand their money, track expenses, "
            "create invoices, and stay tax-ready — without jargon. You never guess — if data is missing, "
            "you say so and ask for it.\n\n"
            f"Current month snapshot:\n"
            f"  Income: ${summary.get('total_income', 0):,.2f}\n"
            f"  Expenses: ${summary.get('total_expenses', 0):,.2f}\n"
            f"  Net: ${summary.get('net', 0):,.2f}\n"
            f"  Pending invoices: {summary.get('pending_invoice_count', 0)}\n"
            f"  Overdue invoices: {summary.get('overdue_invoice_count', 0)}\n"
            f"{skill_ctx}"
        )

        prompt = f"Owner question: {message}\nContext: {json.dumps(ctx)}"
        response = think(prompt=prompt, task_type="report", system_override=system)

        return {
            "agent": "finn",
            "message": response,
            "snapshot": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Bookkeeping ───────────────────────────────────────────────────────

    def log_transaction(self, owner_id: str, amount: float, category: str,
                        description: str, txn_type: str = "expense",
                        date: str | None = None) -> dict[str, Any]:
        """Log a financial transaction."""
        return self.books.log_transaction(
            owner_id=owner_id, amount=amount, category=category,
            description=description, txn_type=txn_type, date=date,
        )

    def categorize_transaction(self, description: str, amount: float) -> dict[str, Any]:
        """Use AI to categorize an uncategorized transaction."""
        category = think(
            prompt=(
                f"Transaction: {description}, Amount: ${amount}\n"
                "Categorize this into exactly one of: rent, payroll, software, marketing, "
                "supplies, travel, utilities, meals, professional_services, revenue, refund, other.\n"
                "Reply with just the category name."
            ),
            task_type="classify",
        )
        return {"description": description, "amount": amount, "suggested_category": category.strip().lower()}

    def get_monthly_snapshot(self, owner_id: str, month: str | None = None) -> dict[str, Any]:
        """Get income/expense/net for a month."""
        return self.books.get_monthly_snapshot(owner_id=owner_id, month=month)

    def generate_pl_report(self, owner_id: str, period: str = "monthly") -> dict[str, Any]:
        """Generate a P&L report with AI narrative."""
        return self.books.generate_pl_report(owner_id=owner_id, period=period)

    def generate_expense_report(self, owner_id: str) -> dict[str, Any]:
        """Generate a tax-ready expense report."""
        return self.books.generate_expense_report(owner_id)

    # ── Invoicing ─────────────────────────────────────────────────────────

    def create_invoice(self, owner_id: str, client_name: str, client_email: str,
                       line_items: list[dict], due_days: int = 30,
                       notes: str = "") -> dict[str, Any]:
        """Create and store a new invoice."""
        return self.invoices.create_invoice(
            owner_id=owner_id, client_name=client_name,
            client_email=client_email, line_items=line_items,
            due_days=due_days, notes=notes,
        )

    def send_invoice(self, invoice_id: str) -> dict[str, Any]:
        """Send an invoice to the client via email."""
        return self.invoices.send_invoice(invoice_id)

    def mark_invoice_paid(self, invoice_id: str, payment_ref: str = "") -> dict[str, Any]:
        """Mark an invoice as paid."""
        return self.invoices.mark_paid(invoice_id=invoice_id, payment_ref=payment_ref)

    def send_payment_reminders(self, owner_id: str) -> dict[str, Any]:
        """Send reminders for all overdue invoices."""
        return self.invoices.send_reminders(owner_id)

    def get_invoice_list(self, owner_id: str, status: str = "all") -> dict[str, Any]:
        """Get all invoices for an owner, optionally filtered by status."""
        return self.invoices.list_invoices(owner_id=owner_id, status=status)

    # ── AI Financial Advice ───────────────────────────────────────────────

    def get_cash_flow_advice(self, owner_id: str) -> str:
        """Generate AI-driven cash flow advice based on current financials."""
        snapshot = self.books.get_monthly_snapshot(owner_id)
        return think(
            prompt=(
                f"Business financial snapshot:\n"
                f"Monthly income: ${snapshot.get('total_income', 0):,.2f}\n"
                f"Monthly expenses: ${snapshot.get('total_expenses', 0):,.2f}\n"
                f"Net: ${snapshot.get('net', 0):,.2f}\n"
                f"Top expense categories: {snapshot.get('top_categories', [])}\n"
                f"Overdue invoices: {snapshot.get('overdue_invoice_count', 0)}\n\n"
                "Provide 3 specific, actionable cash flow improvement tips for this business owner. "
                "Keep each tip under 30 words."
            ),
            task_type="strategy",
        )

    def run_weekly_finance_digest(self, owner_id: str) -> dict[str, Any]:
        """Generate and push weekly finance digest to Commander inbox."""
        snapshot = self.books.get_monthly_snapshot(owner_id)
        overdue = self.invoices.list_invoices(owner_id=owner_id, status="overdue")
        advice = self.get_cash_flow_advice(owner_id)

        digest = (
            f"💰 Weekly Finance Digest\n\n"
            f"MTD Income: ${snapshot.get('total_income', 0):,.2f}\n"
            f"MTD Expenses: ${snapshot.get('total_expenses', 0):,.2f}\n"
            f"Net: ${snapshot.get('net', 0):,.2f}\n"
            f"Overdue invoices: {len(overdue.get('invoices', []))}\n\n"
            f"💡 Finn's Advice:\n{advice}"
        )

        try:
            self.db.client.table("agent_messages").insert({
                "owner_id": owner_id,
                "agent": "finn",
                "role": "assistant",
                "content": digest,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.warning("Failed to push finance digest: %s", e)

        return {"digest": digest, "snapshot": snapshot}
