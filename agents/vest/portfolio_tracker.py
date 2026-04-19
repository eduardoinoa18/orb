"""Portfolio tracker — holdings, allocation, P&L, rebalancing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import SupabaseService

logger = logging.getLogger("orb.vest.portfolio")

# Target allocation defaults (owners can override)
DEFAULT_ALLOCATION_TARGETS = {
    "stock": 50.0,
    "etf": 20.0,
    "crypto": 10.0,
    "real_estate": 10.0,
    "bond": 5.0,
    "alternative": 5.0,
}

REBALANCE_THRESHOLD_PCT = 5.0  # Trigger rebalance if drift > 5%


class PortfolioTracker:
    """Manages investment portfolio holdings and computes P&L."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def add_holding(self, owner_id: str, ticker: str, asset_type: str,
                    quantity: float, avg_cost: float, notes: str = "") -> dict[str, Any]:
        """Add a new holding to the portfolio."""
        try:
            existing = (
                self.db.client.table("portfolio_holdings")
                .select("*")
                .eq("owner_id", owner_id)
                .eq("ticker", ticker.upper())
                .execute()
                .data or []
            )

            if existing:
                # Average down / up
                old = existing[0]
                old_qty = float(old["quantity"])
                old_cost = float(old["avg_cost"])
                new_qty = old_qty + quantity
                new_avg = ((old_qty * old_cost) + (quantity * avg_cost)) / new_qty if new_qty > 0 else avg_cost

                self.db.client.table("portfolio_holdings").update({
                    "quantity": round(new_qty, 6),
                    "avg_cost": round(new_avg, 4),
                    "notes": notes or old.get("notes", ""),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("owner_id", owner_id).eq("ticker", ticker.upper()).execute()

                return {"added": True, "action": "averaged", "ticker": ticker.upper(),
                        "new_quantity": round(new_qty, 6), "new_avg_cost": round(new_avg, 4)}
            else:
                record = {
                    "owner_id": owner_id,
                    "ticker": ticker.upper(),
                    "asset_type": asset_type.lower(),
                    "quantity": round(quantity, 6),
                    "avg_cost": round(avg_cost, 4),
                    "notes": notes,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                self.db.client.table("portfolio_holdings").insert(record).execute()
                return {"added": True, "action": "new_position", "ticker": ticker.upper()}
        except Exception as e:
            logger.error("Add holding failed: %s", e)
            return {"added": False, "error": str(e)}

    def update_holding(self, owner_id: str, ticker: str, quantity: float,
                       avg_cost: float | None = None) -> dict[str, Any]:
        """Update a position's quantity / cost basis."""
        try:
            update_data: dict[str, Any] = {
                "quantity": round(quantity, 6),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if avg_cost is not None:
                update_data["avg_cost"] = round(avg_cost, 4)

            self.db.client.table("portfolio_holdings").update(update_data).eq(
                "owner_id", owner_id
            ).eq("ticker", ticker.upper()).execute()

            return {"updated": True, "ticker": ticker.upper()}
        except Exception as e:
            return {"updated": False, "error": str(e)}

    def remove_holding(self, owner_id: str, ticker: str) -> dict[str, Any]:
        """Remove a position from the portfolio."""
        try:
            self.db.client.table("portfolio_holdings").delete().eq(
                "owner_id", owner_id
            ).eq("ticker", ticker.upper()).execute()
            return {"removed": True, "ticker": ticker.upper()}
        except Exception as e:
            return {"removed": False, "error": str(e)}

    def get_summary(self, owner_id: str) -> dict[str, Any]:
        """Quick portfolio summary (no live prices)."""
        try:
            rows = (
                self.db.client.table("portfolio_holdings")
                .select("*")
                .eq("owner_id", owner_id)
                .execute()
                .data or []
            )

            cost_basis = sum(float(r["quantity"]) * float(r["avg_cost"]) for r in rows)
            allocation: dict[str, float] = {}
            for r in rows:
                atype = r.get("asset_type", "other")
                allocation[atype] = allocation.get(atype, 0) + float(r["quantity"]) * float(r["avg_cost"])

            return {
                "holding_count": len(rows),
                "cost_basis": round(cost_basis, 2),
                "total_value": round(cost_basis, 2),  # Will be enriched with live prices
                "ytd_return_pct": 0.0,  # Computed when live prices are available
                "allocation": {k: round((v / cost_basis * 100), 1) if cost_basis > 0 else 0
                               for k, v in allocation.items()},
            }
        except Exception as e:
            logger.error("Portfolio summary failed: %s", e)
            return {"holding_count": 0, "total_value": 0, "allocation": {}}

    def get_full_portfolio(self, owner_id: str) -> dict[str, Any]:
        """Get full portfolio with enriched data."""
        try:
            rows = (
                self.db.client.table("portfolio_holdings")
                .select("*")
                .eq("owner_id", owner_id)
                .execute()
                .data or []
            )

            # Enrich with market data where available
            holdings = []
            total_value = 0.0
            total_cost = 0.0

            for r in rows:
                qty = float(r["quantity"])
                avg_cost = float(r["avg_cost"])
                cost_basis = qty * avg_cost

                # Try to get live price
                current_price = avg_cost  # Fallback to cost
                try:
                    from integrations.market_data import get_price
                    price_data = get_price(r["ticker"])
                    if price_data and price_data.get("price"):
                        current_price = float(price_data["price"])
                except Exception:
                    pass

                current_value = qty * current_price
                unrealized_pnl = current_value - cost_basis
                unrealized_pnl_pct = ((current_value - cost_basis) / cost_basis * 100) if cost_basis > 0 else 0

                total_value += current_value
                total_cost += cost_basis

                holdings.append({
                    **r,
                    "current_price": round(current_price, 4),
                    "current_value": round(current_value, 2),
                    "cost_basis": round(cost_basis, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                })

            # Allocation by asset type
            allocation: dict[str, float] = {}
            for h in holdings:
                atype = h.get("asset_type", "other")
                allocation[atype] = allocation.get(atype, 0) + h["current_value"]

            alloc_pct = {k: round((v / total_value * 100), 1) if total_value > 0 else 0
                         for k, v in allocation.items()}

            ytd_return = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0

            return {
                "holdings": holdings,
                "holding_count": len(holdings),
                "total_value": round(total_value, 2),
                "total_cost_basis": round(total_cost, 2),
                "total_unrealized_pnl": round(total_value - total_cost, 2),
                "ytd_return_pct": round(ytd_return, 2),
                "allocation": alloc_pct,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error("Full portfolio fetch failed: %s", e)
            return {"holdings": [], "total_value": 0, "error": str(e)}

    def check_rebalancing(self, owner_id: str) -> dict[str, Any]:
        """Check if any asset class has drifted beyond target threshold."""
        port = self.get_full_portfolio(owner_id)
        current_alloc = port.get("allocation", {})
        needs_rebalancing = False
        drift_alerts = []

        for asset_type, target_pct in DEFAULT_ALLOCATION_TARGETS.items():
            current_pct = current_alloc.get(asset_type, 0)
            drift = abs(current_pct - target_pct)
            if drift > REBALANCE_THRESHOLD_PCT:
                needs_rebalancing = True
                drift_alerts.append({
                    "asset_type": asset_type,
                    "current_pct": current_pct,
                    "target_pct": target_pct,
                    "drift_pct": round(drift, 1),
                    "action": "overweight" if current_pct > target_pct else "underweight",
                })

        return {
            "needs_rebalancing": needs_rebalancing,
            "drift_alerts": drift_alerts,
            "current_allocation": current_alloc,
            "target_allocation": DEFAULT_ALLOCATION_TARGETS,
        }
