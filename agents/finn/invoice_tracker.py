"""Invoice tracker — create, send, remind, and reconcile invoices."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think
from integrations.resend_client import send_email

logger = logging.getLogger("orb.finn.invoices")


class InvoiceTracker:
    """Full invoice lifecycle management."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def create_invoice(self, owner_id: str, client_name: str, client_email: str,
                       line_items: list[dict], due_days: int = 30,
                       notes: str = "") -> dict[str, Any]:
        """Create a new invoice and store it in Supabase."""
        invoice_id = str(uuid.uuid4())
        invoice_number = f"INV-{datetime.now(timezone.utc).strftime('%Y%m')}-{invoice_id[:6].upper()}"

        # Compute totals
        subtotal = sum(float(item.get("quantity", 1)) * float(item.get("unit_price", 0)) for item in line_items)
        tax_rate = 0.0  # Owners can configure this
        tax_amount = round(subtotal * tax_rate, 2)
        total = round(subtotal + tax_amount, 2)

        due_date = (datetime.now(timezone.utc) + timedelta(days=due_days)).date().isoformat()

        record = {
            "id": invoice_id,
            "owner_id": owner_id,
            "invoice_number": invoice_number,
            "client_name": client_name,
            "client_email": client_email,
            "line_items": line_items,
            "subtotal": round(subtotal, 2),
            "tax_amount": tax_amount,
            "total": total,
            "due_date": due_date,
            "notes": notes,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self.db.client.table("invoices").insert(record).execute()
            return {"created": True, "invoice": record}
        except Exception as e:
            logger.error("Failed to create invoice: %s", e)
            return {"created": False, "error": str(e)}

    def send_invoice(self, invoice_id: str) -> dict[str, Any]:
        """Send an invoice to the client via email."""
        try:
            rows = self.db.client.table("invoices").select("*").eq("id", invoice_id).execute().data
            if not rows:
                return {"sent": False, "error": "Invoice not found"}

            inv = rows[0]
            if inv["status"] == "paid":
                return {"sent": False, "error": "Invoice already paid"}

            # Build email body
            line_items_text = "\n".join(
                f"  - {item.get('description', 'Service')}: "
                f"{item.get('quantity', 1)} x ${item.get('unit_price', 0):.2f}"
                for item in inv.get("line_items", [])
            )

            body = (
                f"Dear {inv['client_name']},\n\n"
                f"Please find your invoice below:\n\n"
                f"Invoice #: {inv['invoice_number']}\n"
                f"Due Date: {inv['due_date']}\n\n"
                f"Items:\n{line_items_text}\n\n"
                f"Total Due: ${inv['total']:,.2f}\n\n"
                f"{inv.get('notes', '')}\n\n"
                f"Thank you for your business!"
            )

            # Send via Resend
            email_sent = False
            try:
                send_email(
                    to=inv["client_email"],
                    subject=f"Invoice {inv['invoice_number']} — ${inv['total']:,.2f} Due {inv['due_date']}",
                    body=body,
                )
                email_sent = True
            except Exception as email_err:
                logger.warning("Email send failed: %s", email_err)

            # Update status
            self.db.client.table("invoices").update({
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", invoice_id).execute()

            return {"sent": True, "email_sent": email_sent, "invoice_number": inv["invoice_number"]}
        except Exception as e:
            logger.error("Failed to send invoice: %s", e)
            return {"sent": False, "error": str(e)}

    def mark_paid(self, invoice_id: str, payment_ref: str = "") -> dict[str, Any]:
        """Mark an invoice as paid and log as income transaction."""
        try:
            rows = self.db.client.table("invoices").select("*").eq("id", invoice_id).execute().data
            if not rows:
                return {"marked": False, "error": "Invoice not found"}

            inv = rows[0]
            self.db.client.table("invoices").update({
                "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "payment_reference": payment_ref,
            }).eq("id", invoice_id).execute()

            # Log as income transaction
            self.db.client.table("transactions").insert({
                "owner_id": inv["owner_id"],
                "amount": inv["total"],
                "category": "revenue",
                "description": f"Invoice {inv['invoice_number']} — {inv['client_name']}",
                "txn_type": "income",
                "txn_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            return {"marked": True, "invoice_id": invoice_id, "amount": inv["total"]}
        except Exception as e:
            logger.error("Failed to mark invoice paid: %s", e)
            return {"marked": False, "error": str(e)}

    def send_reminders(self, owner_id: str) -> dict[str, Any]:
        """Send payment reminders for all overdue invoices."""
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            overdue = (
                self.db.client.table("invoices")
                .select("*")
                .eq("owner_id", owner_id)
                .eq("status", "sent")
                .lt("due_date", today)
                .execute()
                .data or []
            )

            sent_count = 0
            for inv in overdue:
                days_overdue = (
                    datetime.now(timezone.utc).date() -
                    datetime.fromisoformat(inv["due_date"]).date()
                ).days

                reminder_text = think(
                    prompt=(
                        f"Write a polite but firm payment reminder email.\n"
                        f"Invoice: {inv['invoice_number']}\n"
                        f"Amount: ${inv['total']:,.2f}\n"
                        f"Days overdue: {days_overdue}\n"
                        f"Client: {inv['client_name']}\n"
                        "Keep it under 80 words. Professional but warm."
                    ),
                    task_type="email",
                )

                try:
                    send_email(
                        to=inv["client_email"],
                        subject=f"Payment Reminder: {inv['invoice_number']} ({days_overdue} days overdue)",
                        body=reminder_text,
                    )
                    sent_count += 1

                    # Update status to overdue
                    self.db.client.table("invoices").update({"status": "overdue"}).eq("id", inv["id"]).execute()
                except Exception as e:
                    logger.warning("Reminder email failed for %s: %s", inv["invoice_number"], e)

            return {"overdue_count": len(overdue), "reminders_sent": sent_count}
        except Exception as e:
            logger.error("Send reminders failed: %s", e)
            return {"error": str(e)}

    def list_invoices(self, owner_id: str, status: str = "all") -> dict[str, Any]:
        """List invoices for an owner."""
        try:
            query = self.db.client.table("invoices").select("*").eq("owner_id", owner_id)
            if status != "all":
                query = query.eq("status", status)
            rows = query.order("created_at", desc=True).limit(50).execute().data or []
            return {
                "invoices": rows,
                "count": len(rows),
                "total_value": round(sum(r.get("total", 0) for r in rows), 2),
            }
        except Exception as e:
            logger.error("List invoices failed: %s", e)
            return {"invoices": [], "error": str(e)}
