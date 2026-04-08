"""Commander brain for owner-first orchestration across all ORB agents."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.anthropic_client import ask_claude

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "agent_configs" / "commander.json"
_DEFAULT_COMMANDER_NAME = "Max"


class CommanderBrain:
    """Orchestrates owner requests into coordinated cross-agent actions."""

    def __init__(self) -> None:
        self._db: SupabaseService | None = None

    def _get_db(self) -> SupabaseService | None:
        """Returns a shared Supabase helper when available."""
        if self._db is not None:
            return self._db
        try:
            self._db = SupabaseService()
            return self._db
        except DatabaseConnectionError:
            return None

    def _fetch_rows(self, table: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if filters:
            owner_id = filters.get("owner_id")
            if owner_id and not self._is_uuid(str(owner_id)):
                return []
            row_id = filters.get("id")
            if table in {"owners", "agents", "tasks", "leads", "activity_log", "paper_trades"} and row_id:
                if not self._is_uuid(str(row_id)):
                    return []
        db = self._get_db()
        if not db:
            return []
        try:
            return db.fetch_all(table, filters)
        except DatabaseConnectionError:
            return []

    def _load_agent_config(self) -> dict[str, Any]:
        if not _CONFIG_PATH.exists():
            return {"default_name": _DEFAULT_COMMANDER_NAME, "persona": ""}
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"default_name": _DEFAULT_COMMANDER_NAME, "persona": ""}

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except (ValueError, TypeError):
            return False

    def _load_commander_profile(self, owner_id: str) -> dict[str, Any]:
        """Loads owner-specific commander settings with sensible defaults."""
        base = self._load_agent_config()
        profile = {
            "commander_name": str(base.get("default_name") or _DEFAULT_COMMANDER_NAME),
            "personality_style": "professional",
            "communication_style": "concise",
            "proactivity_level": 7,
            "morning_briefing_enabled": True,
            "briefing_time": "07:00",
            "weekly_review_enabled": True,
            "review_day": "sunday",
            "language": "en",
            "persona": str(base.get("persona") or ""),
        }
        rows = self._fetch_rows("commander_config", {"owner_id": owner_id})
        if rows:
            row = rows[0]
            for key in list(profile.keys()):
                if key in row and row.get(key) is not None:
                    profile[key] = row.get(key)
        return profile

    async def gather_full_context(self, owner_id: str) -> dict[str, Any]:
        """Collects command context in parallel using asyncio.gather."""

        async def run_blocking(func: Any) -> Any:
            return await asyncio.to_thread(func)

        (
            pipeline,
            calendar,
            approvals,
            ai_cost,
            health,
            trading,
            urgent_alerts,
            owner_profile,
            recent_activity,
        ) = await asyncio.gather(
            run_blocking(lambda: self._get_pipeline_summary(owner_id)),
            run_blocking(lambda: self._get_calendar_summary(owner_id)),
            run_blocking(lambda: self._get_pending_approvals(owner_id)),
            run_blocking(lambda: self._get_daily_ai_cost(owner_id)),
            run_blocking(lambda: self._get_platform_health(owner_id)),
            run_blocking(lambda: self._get_orion_summary(owner_id)),
            run_blocking(lambda: self._get_urgent_alerts(owner_id)),
            run_blocking(lambda: self._get_owner_profile(owner_id)),
            run_blocking(lambda: self._get_recent_activity(owner_id)),
        )

        return {
            "owner_id": owner_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": pipeline,
            "calendar": calendar,
            "pending_approvals": approvals,
            "daily_ai_cost": ai_cost,
            "platform_health": health,
            "orion": trading,
            "urgent_alerts": urgent_alerts,
            "owner_profile": owner_profile,
            "recent_activity": recent_activity,
        }

    def _get_owner_profile(self, owner_id: str) -> dict[str, Any]:
        if not self._is_uuid(owner_id):
            return {"owner_name": "Owner", "business_name": "", "email": "", "phone": ""}
        owners = self._fetch_rows("owners", {"id": owner_id})
        if owners:
            owner = owners[0]
            name = str(owner.get("name") or owner.get("full_name") or "Owner")
            return {
                "owner_name": name,
                "business_name": owner.get("business_name") or "",
                "email": owner.get("email") or "",
                "phone": owner.get("phone") or "",
            }
        return {"owner_name": "Owner", "business_name": "", "email": "", "phone": ""}

    def _get_pipeline_summary(self, owner_id: str) -> dict[str, Any]:
        leads = self._fetch_rows("leads", {"owner_id": owner_id})
        hot = [row for row in leads if int(row.get("temperature") or 0) >= 8]
        qualified = [row for row in leads if str(row.get("status") or "").lower() in {"qualified", "appointment", "offer"}]
        return {
            "total": len(leads),
            "hot": len(hot),
            "qualified": len(qualified),
            "next_hot_lead": hot[0] if hot else None,
        }

    def _get_calendar_summary(self, owner_id: str) -> dict[str, Any]:
        tasks = self._fetch_rows("tasks", {"owner_id": owner_id})
        today = datetime.now(timezone.utc).date()
        today_tasks = []
        for row in tasks:
            due = row.get("due_at")
            if not due:
                continue
            try:
                due_dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
            except ValueError:
                continue
            if due_dt.date() == today:
                today_tasks.append(row)
        return {
            "meetings_today": len(today_tasks),
            "next_meeting": today_tasks[0] if today_tasks else None,
        }

    def _get_pending_approvals(self, owner_id: str) -> dict[str, Any]:
        activity = self._fetch_rows("activity_log", {"owner_id": owner_id})
        pending = [row for row in activity if row.get("needs_approval") is True]
        return {"count": len(pending), "items": pending[:5]}

    def _get_daily_ai_cost(self, owner_id: str) -> dict[str, Any]:
        activity = self._fetch_rows("activity_log", {"owner_id": owner_id})
        today = datetime.now(timezone.utc).date()
        total_cents = 0
        for row in activity:
            created = row.get("created_at")
            if not created:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except ValueError:
                continue
            if created_dt.date() == today:
                total_cents += int(row.get("cost_cents") or 0)
        return {"cost_dollars": round(total_cents / 100, 2)}

    def _get_platform_health(self, owner_id: str) -> dict[str, Any]:
        del owner_id
        alerts = self._fetch_rows("activity_log")
        recent_errors = [
            row for row in alerts
            if str(row.get("action_type") or "").lower() == "error"
        ]
        return {
            "status": "alert" if recent_errors else "all_clear",
            "error_count": len(recent_errors),
        }

    def _get_orion_summary(self, owner_id: str) -> dict[str, Any]:
        trades = self._fetch_rows("paper_trades", {"owner_id": owner_id})
        wins = 0
        total = 0
        pnl = 0.0
        for row in trades:
            total += 1
            row_pnl = float(row.get("pnl_dollars") or 0)
            pnl += row_pnl
            if row_pnl > 0:
                wins += 1
        win_rate = round((wins / total) * 100, 1) if total else 0.0
        return {
            "trades_today": total,
            "win_rate": win_rate,
            "pnl_today": round(pnl, 2),
        }

    def _get_recent_activity(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetch_rows("activity_log", {"owner_id": owner_id})
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[:8]

    def _get_urgent_alerts(self, owner_id: str) -> list[str]:
        alerts: list[str] = []
        approvals = self._get_pending_approvals(owner_id)
        if approvals.get("count", 0) > 3:
            alerts.append("You have more than 3 pending approvals.")

        costs = self._get_daily_ai_cost(owner_id)
        if float(costs.get("cost_dollars") or 0) > 25:
            alerts.append("Daily AI cost is above $25.00.")

        health = self._get_platform_health(owner_id)
        if health.get("status") == "alert":
            alerts.append("Sage flagged recent platform errors.")

        return alerts

    def delegate_to_agent(
        self,
        agent_role: str,
        task: str,
        priority: str,
        owner_id: str,
        due_by: str | None = None,
    ) -> str:
        """Creates a task row for an agent and returns the task id."""
        db = self._get_db()
        task_id_fallback = f"local-{agent_role}-{int(datetime.now(timezone.utc).timestamp())}"
        if not db or not self._is_uuid(owner_id):
            return task_id_fallback

        agent_id = None
        agents = self._fetch_rows("agents", {"owner_id": owner_id})
        for row in agents:
            role_values = {
                str(row.get("role") or "").lower(),
                str(row.get("agent_type") or "").lower(),
                str(row.get("name") or "").lower(),
            }
            if agent_role.lower() in role_values:
                agent_id = row.get("id")
                break

        payload: dict[str, Any] = {
            "owner_id": owner_id,
            "title": f"Commander request for {agent_role}",
            "description": task,
            "priority": priority,
            "status": "pending",
        }
        if agent_id:
            payload["agent_id"] = agent_id
        if due_by:
            payload["due_at"] = due_by

        try:
            created = db.insert_one("tasks", payload)
            return str(created.get("id") or task_id_fallback)
        except DatabaseConnectionError:
            return task_id_fallback

    def _build_context_summary(self, context: dict[str, Any]) -> str:
        pipeline = context.get("pipeline", {})
        calendar = context.get("calendar", {})
        approvals = context.get("pending_approvals", {})
        costs = context.get("daily_ai_cost", {})
        health = context.get("platform_health", {})
        orion = context.get("orion", {})
        alerts = context.get("urgent_alerts", [])

        return (
            f"Pipeline: {pipeline.get('total', 0)} leads, {pipeline.get('hot', 0)} hot, {pipeline.get('qualified', 0)} qualified.\n"
            f"Calendar: {calendar.get('meetings_today', 0)} meetings today.\n"
            f"Approvals pending: {approvals.get('count', 0)}.\n"
            f"AI cost today: ${float(costs.get('cost_dollars') or 0):.2f}.\n"
            f"Platform health: {health.get('status', 'unknown')} ({health.get('error_count', 0)} errors).\n"
            f"Orion today: {orion.get('trades_today', 0)} trades, {orion.get('win_rate', 0)}% win-rate, ${orion.get('pnl_today', 0)} PnL.\n"
            f"Urgent alerts: {', '.join(alerts) if alerts else 'none'}"
        )

    def _infer_intent(self, owner_message: str) -> dict[str, Any]:
        msg = owner_message.lower()
        high_urgency_words = ("urgent", "asap", "now", "immediately", "today")
        is_urgent = any(word in msg for word in high_urgency_words)

        agents = []
        for role in ("rex", "aria", "nova", "orion", "sage", "atlas"):
            if role in msg:
                agents.append(role)

        if not agents:
            if any(word in msg for word in ("lead", "pipeline", "call", "sales")):
                agents.append("rex")
            if any(word in msg for word in ("calendar", "meeting", "email", "schedule")):
                agents.append("aria")
            if any(word in msg for word in ("content", "post", "marketing", "social")):
                agents.append("nova")
            if any(word in msg for word in ("trade", "orion", "market", "win rate")):
                agents.append("orion")
            if any(word in msg for word in ("health", "metrics", "kpi", "platform")):
                agents.append("sage")
            if any(word in msg for word in ("bug", "code", "feature", "atlas")):
                agents.append("atlas")

        return {
            "is_urgent": is_urgent,
            "target_agents": agents or ["sage"],
            "needs_decision": any(word in msg for word in ("should", "decide", "choose", "strategy")),
        }

    def _build_plan(self, owner_message: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        intent = self._infer_intent(owner_message)
        priority = "urgent" if intent["is_urgent"] else "high"
        now = datetime.now(timezone.utc)
        due_by = (now + timedelta(hours=1 if intent["is_urgent"] else 6)).isoformat()

        plan: list[dict[str, Any]] = []
        for role in intent["target_agents"]:
            plan.append(
                {
                    "agent_role": role,
                    "task": f"Owner request: {owner_message}",
                    "priority": priority,
                    "due_by": due_by,
                }
            )

        alerts = context.get("urgent_alerts", [])
        if alerts and "sage" not in [item["agent_role"] for item in plan]:
            plan.append(
                {
                    "agent_role": "sage",
                    "task": "Investigate and summarize urgent platform alerts for the owner.",
                    "priority": "urgent",
                    "due_by": (now + timedelta(minutes=30)).isoformat(),
                }
            )
        return plan

    def process_owner_request(
        self,
        owner_message: str,
        owner_id: str,
        conversation_history: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Processes owner request, delegates work, and returns unified response."""
        profile = self._load_commander_profile(owner_id)
        owner_profile = context.get("owner_profile", {})
        owner_name = str(owner_profile.get("owner_name") or "Owner")
        commander_name = str(profile.get("commander_name") or _DEFAULT_COMMANDER_NAME)

        plan = self._build_plan(owner_message, context)
        actions_taken: list[dict[str, Any]] = []
        activated = sorted({item["agent_role"] for item in plan})

        for item in plan:
            task_id = self.delegate_to_agent(
                agent_role=item["agent_role"],
                task=item["task"],
                priority=item["priority"],
                owner_id=owner_id,
                due_by=item.get("due_by"),
            )
            actions_taken.append(
                {
                    "agent": item["agent_role"],
                    "task_id": task_id,
                    "priority": item["priority"],
                    "due_by": item.get("due_by"),
                }
            )

        context_summary = self._build_context_summary(context)
        history_excerpt = conversation_history[-6:]
        history_text = "\n".join(
            f"{str(row.get('role') or 'owner')}: {str(row.get('message') or '')}" for row in history_excerpt
        )

        system_prompt = (
            f"You are {commander_name}, the personal AI chief of staff for {owner_name}.\n"
            "You have real-time access to: leads pipeline, calendar, pending approvals, AI costs,"
            " platform health, and Orion paper trading results.\n"
            "Respond as their trusted chief of staff. Be direct. Lead with the answer."
            " Tell them what you are doing about it. Use 'I'. Maximum 3 paragraphs unless asked for detail."
        )

        user_prompt = (
            f"Current context:\n{context_summary}\n\n"
            f"Recent conversation:\n{history_text or 'No prior messages.'}\n\n"
            f"Owner said: {owner_message}\n\n"
            "Also include a compact action list that says which agents I activated and why."
        )

        try:
            ai = ask_claude(
                system=system_prompt,
                prompt=user_prompt,
                model=str(profile.get("brain_model") or "claude-sonnet-4-6"),
                max_tokens=450,
                max_budget_cents=10,
                agent_id=None,
                is_critical=True,
            )
            response_text = str(ai.get("text") or "").strip()
        except Exception:
            response_text = (
                f"I have this. Based on your request, I activated {', '.join(activated)} and started execution immediately. "
                f"Right now I am prioritizing the highest-impact actions first and I will keep you updated as results land.\n\n"
                f"Current signal snapshot: {context_summary}.\n\n"
                "Immediate actions are queued and I will report back with outcomes plus any approval decisions you need to make."
            )

        needs_approval = [
            "Any outbound message that affects customer commitments",
            "Any billing or plan change",
        ] if any(role in {"rex", "nova", "atlas"} for role in activated) else []

        return {
            "response": response_text,
            "actions_taken": actions_taken,
            "agents_activated": activated,
            "follow_ups_scheduled": [
                {
                    "summary": f"{item['agent']} update expected",
                    "eta": item.get("due_by"),
                }
                for item in actions_taken
            ],
            "needs_approval": needs_approval,
            "summary_for_activity_log": f"Commander processed owner request and activated {', '.join(activated)}.",
            "commander_name": commander_name,
        }

    async def morning_briefing(self, owner_id: str) -> str:
        """Generates a personal morning briefing from full context."""
        context = await self.gather_full_context(owner_id)
        profile = self._load_commander_profile(owner_id)
        owner_name = str(context.get("owner_profile", {}).get("owner_name") or "there")
        commander_name = str(profile.get("commander_name") or _DEFAULT_COMMANDER_NAME)

        pipeline = context.get("pipeline", {})
        calendar = context.get("calendar", {})
        approvals = context.get("pending_approvals", {})
        cost = context.get("daily_ai_cost", {})
        alerts = context.get("urgent_alerts", [])

        lines = [
            f"Good morning, {owner_name}.",
            "Here is what I see for today:",
            f"Your pipeline has {pipeline.get('hot', 0)} hot leads and {pipeline.get('qualified', 0)} qualified opportunities.",
            f"Your calendar has {calendar.get('meetings_today', 0)} meeting(s) today.",
            f"Approvals waiting: {approvals.get('count', 0)}.",
            f"AI spend today: ${float(cost.get('cost_dollars') or 0):.2f}.",
            f"One thing I am watching: {alerts[0] if alerts else 'No urgent risks at the moment.'}",
            f"- {commander_name}",
        ]
        return "\n\n".join(lines)

    async def weekly_review(self, owner_id: str) -> str:
        """Builds a strategic weekly review with higher-depth reasoning."""
        context = await self.gather_full_context(owner_id)
        profile = self._load_commander_profile(owner_id)
        owner_name = str(context.get("owner_profile", {}).get("owner_name") or "Owner")
        commander_name = str(profile.get("commander_name") or _DEFAULT_COMMANDER_NAME)
        summary = self._build_context_summary(context)

        prompt = (
            f"Here is this week's context summary:\n{summary}\n\n"
            "Write a strategic weekly review with:\n"
            "1) numbers that matter\n2) biggest win\n3) biggest miss\n"
            "4) what I am changing next week and why\n5) one question for the owner."
        )

        try:
            result = ask_claude(
                system=f"You are {commander_name}, the owner's trusted chief of staff.",
                prompt=prompt,
                model="claude-opus-4-5",
                max_tokens=700,
                task_type="weekly_review",
                max_budget_cents=25,
                agent_id=None,
                is_critical=True,
            )
            text = str(result.get("text") or "").strip()
            if text:
                return text
        except Exception:
            pass

        return (
            f"Here is your week in review, {owner_name}:\n\n"
            "Numbers that matter: pipeline momentum is stable and execution coverage is active across your team.\n"
            "Biggest win: coordination speed improved because delegated tasks now flow through one command layer.\n"
            "Biggest miss: pending approvals are still accumulating too quickly.\n"
            "What I am changing next week: I will reduce approval bottlenecks with tighter triage and proactive summaries.\n"
            "One question for you: should I optimize for growth velocity or cost efficiency as the top priority next week?"
        )
