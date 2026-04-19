"""Bookkeeping engine — transaction logging, P&L, expense reports."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.finn.books")

EXPENSE_CATEGORIES = [
    "rent", "payroll", "software", "marketing", "supplies",
    "travel", "utilities", "meals", "professional_services", "other",
]


class BookkeepingEngine:
    """Handles financial transaction storage and reporting."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def log_transaction(self, owner_id: str, amount: float, category: str,
                        description: str, txn_type: str = "expense",
                        date: str | None = None) -> dict[str, Any]:
        """Log a single financial transaction."""
        txn_date = date or datetime.now(timezone.utc).date().isoformat()
        try:
            record = {
                "owner_id": owner_id,
                "amount": abs(amount),
                "category": category.lower(),
                "description": description,
                "txn_type": txn_type,  # "income" or "expense"
                "txn_date": txn_date,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.db.client.table("transactions").insert(record).execute()
            return {"logged": True, "transaction": record}
        except Exception as e:
            logger.error("Failed to log transaction: %s", e)
            return {"logged": False, "error": str(e)}

    def get_monthly_snapshot(self, owner_id: str, month: str | None = None) -> dict[str, Any]:
        """Return income/expense/net for the current (or given) month."""
        try:
            if not month:
                now = datetime.now(timezone.utc)
                month_prefix = f"{now.year}-{now.month:02d}"
            else:
                month_prefix = month[:7]  # "YYYY-MM"

            rows = (
                self.db.client.table("transactions")
                .select("*")
                .eq("owner_id", owner_id)
                .like("txn_date", f"{month_prefix}%")
                .execute()
                .data or []
            )

            total_income = sum(r["amount"] for r in rows if r.get("txn_type") == "income")
            total_expenses = sum(r["amount"] for r in rows if r.get("txn_type") == "expense")

            # Category breakdown for expenses
            category_totals: dict[str, float] = {}
            for r in rows:
                if r.get("txn_type") == "expense":
                    cat = r.get("category", "other")
                    category_totals[cat] = category_totals.get(cat, 0) + r["amount"]

            top_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]

            # Pending / overdue invoices
            pending_inv = (
                self.db.client.table("invoices")
                .select("id", count="exact")
                .eq("owner_id", owner_id)
                .eq("status", "sent")
                .execute()
                .count or 0
            )
            overdue_inv = (
                self.db.client.table("invoices")
                .select("id", count="exact")
                .eq("owner_id", owner_id)
                .eq("status", "overdue")
                .execute()
                .count or 0
            )

            return {
                "month": month_prefix,
                "total_income": round(total_income, 2),
                "total_expenses": round(total_expenses, 2),
                "net": round(total_income - total_expenses, 2),
                "transaction_count": len(rows),
                "top_categories": [{"category": k, "amount": round(v, 2)} for k, v in top_categories],
                "pending_invoice_count": pending_inv,
                "overdue_invoice_count": overdue_inv,
            }
        except Exception as e:
            logger.error("Snapshot failed: %s", e)
            return {"error": str(e), "total_income": 0, "total_expenses": 0, "net": 0}

    def generate_pl_report(self, owner_id: str, period: str = "monthly") -> dict[str, Any]:
        """Generate a P&L report with AI narrative summary."""
        snapshot = self.get_monthly_snapshot(owner_id)

        narrative = think(
            prompt=(
                f"Generate a brief P&L narrative for a small business:\n"
                f"Period: {period}\n"
                f"Revenue: ${snapshot.get('total_income', 0):,.2f}\n"
                f"Expenses: ${snapshot.get('total_expenses', 0):,.2f}\n"
                f"Net Income: ${snapshot.get('net', 0):,.2f}\n"
                f"Top expense categories: {snapshot.get('top_categories', [])}\n\n"
                "Write 3 sentences: (1) summary of performance, "
                "(2) largest cost driver, (3) one actionable recommendation."
            ),
            task_type="report",
        )

        return {
            "period": period,
            "financials": snapshot,
            "narrative": narrative,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_expense_report(self, owner_id: str) -> dict[str, Any]:
        """Generate a tax-ready expense report by category."""
        try:
            # Get all expenses for the current year
            year = datetime.now(timezone.utc).year
            rows = (
                self.db.client.table("transactions")
                .select("*")
                .eq("owner_id", owner_id)
                .eq("txn_type", "expense")
                .like("txn_date", f"{year}%")
                .order("txn_date")
                .execute()
                .data or []
            )

            by_category: dict[str, list[dict]] = {}
            for r in rows:
                cat = r.get("category", "other")
                by_category.setdefault(cat, []).append(r)

            category_totals = {
                cat: round(sum(r["amount"] for r in txns), 2)
                for cat, txns in by_category.items()
            }

            total = sum(category_totals.values())

            return {
                "year": year,
                "total_expenses": round(total, 2),
                "by_category": category_totals,
                "transaction_count": len(rows),
                "transactions": rows[:100],  # Cap for response size
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error("Expense report failed: %s", e)
            return {"error": str(e)}
