"""Onboarding flow engine for ORB owners.

Manages a step-by-step guided setup sequence. Each step has:
  - A key (unique identifier)
  - A title + description shown in the UI
  - Completion criteria
  - Optional AI-generated guidance

The flow persists to Supabase so owners can resume across sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.database.connection import SupabaseService
from integrations.ai_router import think

logger = logging.getLogger("orb.zara.onboarding")

ONBOARDING_STEPS = [
    {
        "key": "business_profile",
        "title": "Set Up Your Business Profile",
        "description": "Tell ORB about your business so agents can speak your language.",
        "required": True,
        "order": 1,
    },
    {
        "key": "first_agent",
        "title": "Activate Your First Agent",
        "description": "Choose which agent fits your most urgent need and turn them on.",
        "required": True,
        "order": 2,
    },
    {
        "key": "connect_channel",
        "title": "Connect a Communication Channel",
        "description": "Link WhatsApp, SMS, or email so your agent can reach clients.",
        "required": True,
        "order": 3,
    },
    {
        "key": "first_conversation",
        "title": "Have Your First Commander Conversation",
        "description": "Ask Commander anything — discover what your platform can do.",
        "required": True,
        "order": 4,
    },
    {
        "key": "integration",
        "title": "Connect an Integration (Optional)",
        "description": "Link HubSpot, Google Calendar, Stripe, or another tool.",
        "required": False,
        "order": 5,
    },
    {
        "key": "invite_team",
        "title": "Invite a Team Member (Optional)",
        "description": "Add your assistant, ops lead, or partner to the platform.",
        "required": False,
        "order": 6,
    },
]


class OnboardingFlow:
    """Manages step-by-step owner onboarding."""

    def __init__(self) -> None:
        self.db = SupabaseService()

    def initialize(self, owner_id: str, business_profile: dict[str, Any]) -> dict[str, Any]:
        """Create or reset the onboarding record for an owner."""
        steps_state = {
            step["key"]: {"status": "pending", "completed_at": None, "data": {}}
            for step in ONBOARDING_STEPS
        }

        record = {
            "owner_id": owner_id,
            "steps": steps_state,
            "current_step": "business_profile",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "business_profile_snapshot": business_profile,
        }

        try:
            existing = self.db.fetch_all("onboarding_flows", {"owner_id": owner_id})
            if existing:
                self.db.client.table("onboarding_flows").update(record).eq("owner_id", owner_id).execute()
            else:
                self.db.client.table("onboarding_flows").insert(record).execute()
        except Exception as e:
            logger.warning("Could not persist onboarding flow: %s", e)

        return {"owner_id": owner_id, "steps": ONBOARDING_STEPS, "current_step": "business_profile"}

    def get_status(self, owner_id: str) -> dict[str, Any]:
        """Return current onboarding progress."""
        try:
            rows = self.db.fetch_all("onboarding_flows", {"owner_id": owner_id})
            if not rows:
                return {"owner_id": owner_id, "started": False, "progress_pct": 0, "steps": ONBOARDING_STEPS}

            row = rows[0]
            steps_state = row.get("steps", {})
            completed = sum(1 for s in steps_state.values() if s.get("status") == "completed")
            total = len(ONBOARDING_STEPS)
            required_done = all(
                steps_state.get(s["key"], {}).get("status") == "completed"
                for s in ONBOARDING_STEPS if s["required"]
            )

            return {
                "owner_id": owner_id,
                "started": True,
                "completed": row.get("completed_at") is not None,
                "progress_pct": round((completed / total) * 100),
                "required_complete": required_done,
                "current_step": row.get("current_step"),
                "steps": [
                    {**step, "state": steps_state.get(step["key"], {"status": "pending"})}
                    for step in ONBOARDING_STEPS
                ],
            }
        except Exception as e:
            logger.error("Failed to get onboarding status: %s", e)
            return {"owner_id": owner_id, "error": str(e)}

    def complete_step(self, owner_id: str, step_key: str, data: dict[str, Any]) -> dict[str, Any]:
        """Mark a step complete and advance to the next."""
        try:
            rows = self.db.fetch_all("onboarding_flows", {"owner_id": owner_id})
            if not rows:
                return {"error": "No onboarding flow found. Call initialize() first."}

            row = rows[0]
            steps_state = row.get("steps", {})

            if step_key not in steps_state:
                return {"error": f"Unknown step: {step_key}"}

            steps_state[step_key] = {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }

            # Find next pending step
            ordered = sorted(ONBOARDING_STEPS, key=lambda s: s["order"])
            next_step = None
            for step in ordered:
                if steps_state.get(step["key"], {}).get("status") != "completed":
                    next_step = step["key"]
                    break

            update_payload: dict[str, Any] = {
                "steps": steps_state,
                "current_step": next_step,
            }

            # Check if all required steps are done
            required_done = all(
                steps_state.get(s["key"], {}).get("status") == "completed"
                for s in ONBOARDING_STEPS if s["required"]
            )
            if required_done and not row.get("completed_at"):
                update_payload["completed_at"] = datetime.now(timezone.utc).isoformat()

            self.db.client.table("onboarding_flows").update(update_payload).eq("owner_id", owner_id).execute()

            # Generate AI guidance for the next step
            guidance = ""
            if next_step:
                next_info = next((s for s in ONBOARDING_STEPS if s["key"] == next_step), {})
                guidance = think(
                    prompt=f"Give a 2-sentence encouraging tip for completing this onboarding step: {next_info.get('title', next_step)}",
                    task_type="classify",
                )

            return {
                "completed_step": step_key,
                "next_step": next_step,
                "onboarding_complete": required_done,
                "ai_guidance": guidance,
            }
        except Exception as e:
            logger.error("Failed to complete onboarding step: %s", e)
            return {"error": str(e)}
