"""Adaptive Skill Engine — ORB Agent Evolution System.

Every ORB agent (Rex, Aria, Nova, Orion, Sage, Atlas, Commander) inherits
this mixin to gain:

  1. SKILL DISCOVERY — Agents analyze user requests and discover what new
     skills they should develop based on actual usage patterns.

  2. SKILL EXPANSION — Agents can grow beyond their core role. The insurance
     salesman's agent that starts with lead management can evolve to include
     video editing assistance, social media templates, and YouTube content
     — because the user actually asked for it.

  3. BUSINESS CONTEXT ADAPTATION — Every skill is tuned to the owner's
     specific business profile. The same "email drafting" skill behaves
     completely differently for a real estate agent vs. a sports coach.

  4. SELF-SCRUBBING — Agents periodically scan documentation, available
     integrations, and their own usage logs to surface new capabilities.

  5. CAPABILITY PROPOSALS — When an agent discovers a new capability it
     can't currently execute, it files a platform_request so Eduardo's
     Commander can evaluate and potentially build it.

How the insurance + sports video example works:
  - Rex starts with: lead qualification, follow-up sequences, CRM sync
  - User asks: "Help me edit a video of my kid's soccer game for YouTube"
  - Rex can't do video editing → files platform_request
  - Eduardo's Commander sees it → decides to expand Rex with media skills
  - Rex gains: video_editing, social_template, youtube_upload skill flags
  - Next time user asks, Rex can handle it or delegate to Nova
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("orb.skill_engine")

# ── Core skill categories available for all agents ────────────────────────────
UNIVERSAL_SKILLS = {
    # Communication
    "email_drafting":       "Write personalized emails for any business context",
    "sms_compose":          "Draft short, punchy SMS/WhatsApp messages",
    "social_post":          "Create social media content for any platform",
    "report_writing":       "Generate detailed reports, summaries, and briefs",
    # Organization
    "calendar_management":  "Schedule, reschedule, and optimize time",
    "task_tracking":        "Track and prioritize work items",
    "meeting_prep":         "Prepare agendas, talking points, and follow-ups",
    # Analysis
    "data_summarize":       "Summarize complex data into actionable insights",
    "competitor_research":  "Research competitors and market positioning",
    "trend_analysis":       "Identify patterns and emerging trends",
    # Content
    "content_strategy":     "Plan content calendars and campaigns",
    "seo_copy":             "Write SEO-optimized content and descriptions",
    "video_script":         "Write scripts for videos, podcasts, reels",
    # Specialized
    "lead_qualify":         "Score and qualify sales leads",
    "crm_sync":             "Sync data with CRM systems",
    "invoice_tracking":     "Track invoices, payments, and follow up on overdue",
    "bookkeeping_assist":   "Help with expense tracking and basic bookkeeping",
    "image_generation":     "Generate AI images for marketing and content",
    "voice_briefing":       "Deliver audio summaries and briefings",
    # Platform
    "self_review":          "Analyze own performance and improve behavior",
    "platform_request":     "File requests for new platform capabilities",
}

# Per-agent core specializations
AGENT_CORE_SKILLS: dict[str, list[str]] = {
    "rex": [
        "lead_qualify", "crm_sync", "sms_compose", "email_drafting",
        "meeting_prep", "task_tracking",
    ],
    "aria": [
        "email_drafting", "calendar_management", "meeting_prep",
        "report_writing", "task_tracking",
    ],
    "nova": [
        "content_strategy", "social_post", "seo_copy", "image_generation",
        "video_script",
    ],
    "orion": [
        "data_summarize", "trend_analysis", "competitor_research",
        "report_writing",
    ],
    "sage": [
        "bookkeeping_assist", "invoice_tracking", "data_summarize",
        "report_writing", "trend_analysis",
    ],
    "atlas": [
        "report_writing", "competitor_research", "trend_analysis",
        "content_strategy",
    ],
    "commander": [
        # Commander has all base skills
        *list(UNIVERSAL_SKILLS.keys()),
    ],
}

# Skills that unlock new integrations when activated
SKILL_INTEGRATIONS: dict[str, list[str]] = {
    "bookkeeping_assist":  ["quickbooks", "wave", "freshbooks", "xero"],
    "crm_sync":            ["hubspot", "salesforce", "pipedrive", "gohighlevel"],
    "image_generation":    ["openai_dalle", "stability_ai"],
    "voice_briefing":      ["elevenlabs"],
    "social_post":         ["instagram", "twitter", "linkedin", "facebook"],
    "video_script":        ["youtube_data_api", "runway_ml"],
    "invoice_tracking":    ["stripe", "quickbooks"],
    "email_drafting":      ["gmail", "outlook", "sendgrid"],
    "calendar_management": ["google_calendar", "outlook_calendar"],
}


@dataclass
class SkillProfile:
    """An agent's current skill portfolio."""
    agent_slug: str
    owner_id: str
    core_skills: list[str] = field(default_factory=list)
    expanded_skills: list[str] = field(default_factory=list)
    pending_skills: list[str] = field(default_factory=list)  # Requested but not approved
    skill_scores: dict[str, float] = field(default_factory=dict)  # 0-1 proficiency
    last_review: datetime | None = None
    business_adaptations: list[str] = field(default_factory=list)  # Context-specific notes


class AgentSkillEngine:
    """Mixin that gives any ORB agent adaptive, self-improving skills."""

    agent_slug: str = "agent"  # Override in each agent class

    def __init__(self) -> None:
        self._db = None

    def _get_db(self):
        if self._db is None:
            try:
                from app.database.connection import SupabaseService
                self._db = SupabaseService()
            except Exception:
                pass
        return self._db

    # ── Load / Save ───────────────────────────────────────────────────────────

    def load_skill_profile(self, owner_id: str) -> SkillProfile:
        """Loads the agent's current skill profile for this owner."""
        db = self._get_db()
        core = list(AGENT_CORE_SKILLS.get(self.agent_slug, []))

        if not db:
            return SkillProfile(
                agent_slug=self.agent_slug,
                owner_id=owner_id,
                core_skills=core,
            )
        try:
            rows = db.client.table("agent_skills") \
                .select("*") \
                .eq("agent_slug", self.agent_slug) \
                .eq("owner_id", owner_id) \
                .limit(1) \
                .execute()
            if not rows.data:
                return SkillProfile(agent_slug=self.agent_slug, owner_id=owner_id, core_skills=core)
            row = rows.data[0]
            return SkillProfile(
                agent_slug=self.agent_slug,
                owner_id=owner_id,
                core_skills=row.get("core_skills") or core,
                expanded_skills=row.get("expanded_skills") or [],
                pending_skills=row.get("pending_skills") or [],
                skill_scores=row.get("skill_scores") or {},
                business_adaptations=row.get("business_adaptations") or [],
                last_review=datetime.fromisoformat(row["last_review"]) if row.get("last_review") else None,
            )
        except Exception as e:
            logger.warning("Failed to load skill profile for %s/%s: %s", self.agent_slug, owner_id, e)
            return SkillProfile(agent_slug=self.agent_slug, owner_id=owner_id, core_skills=core)

    def save_skill_profile(self, profile: SkillProfile) -> bool:
        """Persists the skill profile to the database."""
        db = self._get_db()
        if not db:
            return False
        try:
            db.client.table("agent_skills").upsert({
                "agent_slug": profile.agent_slug,
                "owner_id": profile.owner_id,
                "core_skills": profile.core_skills,
                "expanded_skills": profile.expanded_skills,
                "pending_skills": profile.pending_skills,
                "skill_scores": profile.skill_scores,
                "business_adaptations": profile.business_adaptations,
                "last_review": profile.last_review.isoformat() if profile.last_review else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="agent_slug,owner_id").execute()
            return True
        except Exception as e:
            logger.warning("Failed to save skill profile: %s", e)
            return False

    # ── Skill discovery ────────────────────────────────────────────────────────

    def discover_needed_skills(
        self,
        owner_id: str,
        recent_requests: list[str],
        business_profile: dict[str, Any] | None = None,
    ) -> list[str]:
        """Analyzes recent user requests to identify skills this agent should have.

        Returns a list of skill names from UNIVERSAL_SKILLS that would serve
        this user better, based on what they've been asking for.
        """
        if not recent_requests:
            return []

        from integrations.ai_router import think_structured

        profile = self.load_skill_profile(owner_id)
        current_skills = set(profile.core_skills + profile.expanded_skills)

        business_ctx = ""
        if business_profile:
            business_ctx = (
                f"Business: {business_profile.get('business_name', 'Unknown')}, "
                f"Industry: {business_profile.get('industry', 'Unknown')}, "
                f"Products/Services: {business_profile.get('products_services', 'Unknown')}"
            )

        skills_list = "\n".join(f"- {k}: {v}" for k, v in UNIVERSAL_SKILLS.items()
                                 if k not in current_skills)
        requests_str = "\n".join(f"- {r}" for r in recent_requests[:20])

        prompt = f"""You are analyzing what skills an AI agent should develop.

Agent: {self.agent_slug}
{business_ctx}

Recent user requests (what they've been asking the agent to help with):
{requests_str}

Current agent skills: {', '.join(sorted(current_skills))}

Available skills the agent could expand into:
{skills_list}

Based on the user's actual requests and business context, which 1-5 skills from the
available list would most benefit this user? Only suggest skills that are clearly
needed based on the actual requests. Do NOT suggest skills that aren't evidenced
by the requests.

Respond with valid JSON:
{{"suggested_skills": ["skill_name_1", "skill_name_2"], "reasoning": "brief explanation"}}
"""
        result = think_structured(
            prompt=prompt,
            task_type="skill_expand",
            owner_id=owner_id,
        )
        suggested = result.get("suggested_skills", [])
        # Filter to only valid skill names
        valid = [s for s in suggested if s in UNIVERSAL_SKILLS and s not in current_skills]
        logger.info(
            "Skill discovery for %s/%s: %d suggestions from %d requests",
            self.agent_slug, owner_id, len(valid), len(recent_requests),
        )
        return valid

    def adapt_to_business(
        self,
        owner_id: str,
        business_profile: dict[str, Any],
    ) -> list[str]:
        """Generates business-specific adaptation notes for this agent.

        These notes are injected into the agent's system prompt so it knows
        how to apply its skills in the context of this specific business.
        """
        from integrations.ai_router import think

        bp = business_profile
        industry = bp.get("industry", "")
        products = bp.get("products_services", "")
        customers = bp.get("target_customer", "")
        goal = bp.get("primary_goal", "")

        prompt = f"""You are configuring an AI agent to serve a specific business.

Agent: {self.agent_slug} (core skills: {', '.join(AGENT_CORE_SKILLS.get(self.agent_slug, []))})

Business context:
- Industry: {industry}
- Products/Services: {products}
- Target customers: {customers}
- Primary goal: {goal}

Write 3-5 SHORT, specific adaptation notes that tell this agent how to apply
its skills differently for THIS business. Be concrete and practical.
Each note should be one sentence, max 100 characters.
Format as JSON: {{"adaptations": ["note1", "note2", ...]}}
"""
        result = think(prompt=prompt, task_type="skill_expand", owner_id=owner_id)
        try:
            parsed = json.loads(result.strip())
            adaptations = parsed.get("adaptations", [])
        except Exception:
            adaptations = []
        return adaptations[:5]

    # ── Self-improvement cycle ─────────────────────────────────────────────────

    def run_skill_review(self, owner_id: str, lookback_days: int = 7) -> dict[str, Any]:
        """Runs a full skill review cycle for this agent and this owner.

        Steps:
          1. Load recent requests/activity from the DB
          2. Identify skills that should be expanded
          3. Generate business-specific adaptations
          4. Update the skill profile
          5. File platform_requests for skills that need new platform capabilities
          6. Return a summary for logging

        Should run weekly per agent per owner.
        """
        profile = self.load_skill_profile(owner_id)

        # Skip if reviewed recently
        if profile.last_review:
            days_since = (datetime.now(timezone.utc) - profile.last_review.replace(tzinfo=timezone.utc)).days
            if days_since < lookback_days:
                logger.debug("Skipping skill review for %s/%s — last review %d days ago", self.agent_slug, owner_id, days_since)
                return {"status": "skipped", "reason": f"reviewed {days_since}d ago"}

        # Load recent activity
        recent_requests = self._load_recent_requests(owner_id, lookback_days)

        # Load business profile
        business_profile = self._load_business_profile(owner_id)

        # Discover needed skills
        needed_skills = self.discover_needed_skills(
            owner_id=owner_id,
            recent_requests=recent_requests,
            business_profile=business_profile,
        )

        # Adapt to business context
        adaptations = []
        if business_profile:
            adaptations = self.adapt_to_business(owner_id=owner_id, business_profile=business_profile)

        # Update profile
        new_skills = []
        pending_skills = list(profile.pending_skills)
        for skill in needed_skills:
            if skill not in profile.core_skills and skill not in profile.expanded_skills:
                # Skills that require only prompt adaptation can be expanded directly
                if not SKILL_INTEGRATIONS.get(skill):
                    profile.expanded_skills.append(skill)
                    new_skills.append(skill)
                else:
                    # Skills requiring new integrations go to pending
                    if skill not in pending_skills:
                        pending_skills.append(skill)

        profile.pending_skills = pending_skills
        profile.business_adaptations = adaptations
        profile.last_review = datetime.now(timezone.utc)
        self.save_skill_profile(profile)

        # File platform requests for skills that need new capabilities
        filed_requests = []
        for skill in pending_skills[:3]:  # Don't spam with too many requests
            req_id = self._file_capability_request(owner_id, skill)
            if req_id:
                filed_requests.append({"skill": skill, "request_id": req_id})

        result = {
            "status": "completed",
            "agent": self.agent_slug,
            "owner_id": owner_id,
            "new_skills_expanded": new_skills,
            "skills_requested": [r["skill"] for r in filed_requests],
            "adaptations_updated": len(adaptations),
            "total_skills": len(profile.core_skills) + len(profile.expanded_skills),
        }
        logger.info(
            "Skill review: %s/%s — +%d skills, %d requested",
            self.agent_slug, owner_id, len(new_skills), len(filed_requests),
        )
        return result

    def _load_recent_requests(self, owner_id: str, lookback_days: int) -> list[str]:
        """Loads recent user message summaries for skill analysis."""
        db = self._get_db()
        if not db:
            return []
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
            rows = db.client.table("activity_log") \
                .select("description,action_type") \
                .eq("owner_id", owner_id) \
                .gte("created_at", cutoff) \
                .order("created_at", desc=True) \
                .limit(50) \
                .execute()
            return [r.get("description", "") for r in (rows.data or []) if r.get("description")]
        except Exception:
            return []

    def _load_business_profile(self, owner_id: str) -> dict[str, Any]:
        """Loads owner's business profile for context."""
        db = self._get_db()
        if not db:
            return {}
        try:
            rows = db.client.table("business_profiles") \
                .select("*") \
                .eq("owner_id", owner_id) \
                .limit(1) \
                .execute()
            return rows.data[0] if rows.data else {}
        except Exception:
            return {}

    def _file_capability_request(self, owner_id: str, skill_name: str) -> str | None:
        """Files a platform_request asking Eduardo to enable a new skill/integration."""
        db = self._get_db()
        if not db:
            return None
        try:
            # Don't duplicate existing requests for the same skill
            existing = db.client.table("platform_requests") \
                .select("id") \
                .eq("requester_id", owner_id) \
                .ilike("title", f"%{skill_name}%") \
                .in_("status", ["pending", "acknowledged", "in_progress"]) \
                .limit(1) \
                .execute()
            if existing.data:
                return existing.data[0]["id"]

            integrations = SKILL_INTEGRATIONS.get(skill_name, [])
            description = (
                f"The {self.agent_slug} agent has identified that the user needs '{skill_name}' "
                f"capability based on their recent requests. "
                + (f"This requires integration with: {', '.join(integrations)}. " if integrations else "")
                + f"Skill description: {UNIVERSAL_SKILLS.get(skill_name, 'New capability')}"
            )

            # Find admin
            admin_rows = db.client.table("business_profiles") \
                .select("owner_id") \
                .eq("is_platform_admin", True) \
                .limit(1) \
                .execute()
            admin_id = admin_rows.data[0]["owner_id"] if admin_rows.data else None

            result = db.client.table("platform_requests").insert({
                "requester_id": owner_id,
                "request_type": "skill_expansion",
                "title": f"Expand {self.agent_slug} with {skill_name} capability",
                "description": description,
                "priority": "normal",
                "context": {
                    "agent_slug": self.agent_slug,
                    "skill_name": skill_name,
                    "required_integrations": integrations,
                },
                "status": "pending",
                "handled_by_owner_id": admin_id,
            }).execute()

            req_id = result.data[0]["id"] if result.data else None

            # Notify admin
            if admin_id and req_id:
                db.client.table("agent_messages").insert({
                    "from_owner_id": owner_id,
                    "to_owner_id": admin_id,
                    "from_agent_type": self.agent_slug,
                    "to_agent_type": "commander",
                    "message_type": "skill_request",
                    "subject": f"[{self.agent_slug.upper()}] Skill expansion request: {skill_name}",
                    "body": description,
                    "payload": {"request_id": req_id, "skill_name": skill_name},
                    "thread_id": req_id,
                }).execute()

            return req_id
        except Exception as e:
            logger.warning("Failed to file capability request for %s: %s", skill_name, e)
            return None

    # ── Context injection ──────────────────────────────────────────────────────

    def build_skill_context(self, owner_id: str) -> str:
        """Builds a skill context block to inject into the agent's system prompt.

        This is what makes every agent's behavior uniquely tailored to each owner.
        """
        profile = self.load_skill_profile(owner_id)
        all_skills = profile.core_skills + profile.expanded_skills

        lines = [f"=== {self.agent_slug.upper()} AGENT SKILLS ==="]
        lines.append(f"Core skills: {', '.join(profile.core_skills)}")
        if profile.expanded_skills:
            lines.append(f"Expanded skills: {', '.join(profile.expanded_skills)}")

        if profile.business_adaptations:
            lines.append("\nBusiness-specific behavior:")
            for adaptation in profile.business_adaptations:
                lines.append(f"  • {adaptation}")

        if all_skills:
            lines.append(f"\nTotal capabilities: {len(all_skills)}")

        lines.append("=== END SKILLS ===")
        return "\n".join(lines)


# ── Supabase migration helper ──────────────────────────────────────────────────
AGENT_SKILLS_MIGRATION = """
-- Agent Skills table for adaptive skill engine
CREATE TABLE IF NOT EXISTS agent_skills (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_slug  TEXT NOT NULL,
    owner_id    UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    core_skills JSONB NOT NULL DEFAULT '[]',
    expanded_skills JSONB NOT NULL DEFAULT '[]',
    pending_skills JSONB NOT NULL DEFAULT '[]',
    skill_scores JSONB NOT NULL DEFAULT '{}',
    business_adaptations JSONB NOT NULL DEFAULT '[]',
    last_review TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (agent_slug, owner_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_skills_owner ON agent_skills(owner_id);
CREATE INDEX IF NOT EXISTS idx_agent_skills_slug ON agent_skills(agent_slug);

-- Task events for code agent bi-directional protocol
CREATE TABLE IF NOT EXISTS task_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL REFERENCES platform_tasks(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL, -- progress | question | answer | blocker | partial_proposal
    message     TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type);

-- Code agent status for heartbeat
CREATE TABLE IF NOT EXISTS code_agent_status (
    agent_id    TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'idle',
    current_task_id UUID,
    capabilities JSONB DEFAULT '[]',
    version     TEXT,
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

-- Add new columns to platform_tasks for bi-directional protocol
ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS last_agent_activity TIMESTAMPTZ;
ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS agent_progress INTEGER DEFAULT 0;
"""
