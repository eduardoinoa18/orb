-- ═══════════════════════════════════════════════════════════════════════════
-- ORB v4 Database Migration — Self-Improving Platform Architecture
-- Run in Supabase SQL Editor → New Query → Run
-- Safe to run multiple times (all use IF NOT EXISTS)
--
-- Adds:
--   1. business_profiles    — per-owner business identity (Commander reads this)
--   2. platform_requests    — user agents request features/help from admin agent
--   3. agent_messages       — agent-to-agent message bus
--   4. platform_tasks       — code task queue: agent → VS Code → Eduardo approves
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. BUSINESS PROFILES ────────────────────────────────────────────────────
-- Every owner teaches their Commander who they are, what they sell,
-- who their customers are, and what matters most to their business.
-- Commander reads this on every conversation to personalize everything.

CREATE TABLE IF NOT EXISTS business_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,

    -- Core identity
    business_name       TEXT,
    industry            TEXT,
    business_type       TEXT,       -- 'solo', 'small_team', 'agency', 'enterprise'
    founding_year       INT,
    website             TEXT,
    location            TEXT,

    -- What they sell / do
    products_services   TEXT,       -- free-form description
    target_customer     TEXT,       -- who they sell to
    avg_deal_size       TEXT,       -- e.g. "$500/month", "$5k one-time"
    sales_cycle         TEXT,       -- e.g. "same day", "2-4 weeks", "3 months"

    -- Team
    team_size           INT DEFAULT 1,
    key_team_members    JSONB DEFAULT '[]'::JSONB,  -- [{name, role}]

    -- Goals & priorities (Commander uses these to prioritize)
    primary_goal        TEXT,       -- e.g. "close 10 deals/month", "grow to $50k MRR"
    secondary_goals     JSONB DEFAULT '[]'::JSONB,
    current_challenges  TEXT,

    -- Tone & style preferences for Commander
    communication_tone  TEXT DEFAULT 'professional', -- professional, casual, direct, friendly
    response_length     TEXT DEFAULT 'concise',      -- concise, detailed, bullet-points
    language            TEXT DEFAULT 'en',

    -- Custom Commander name for this owner
    commander_name      TEXT DEFAULT 'Commander',

    -- Key metrics Commander should always track
    tracked_metrics     JSONB DEFAULT '[]'::JSONB,   -- ['revenue', 'leads', 'meetings', ...]
    kpi_targets         JSONB DEFAULT '{}'::JSONB,   -- {revenue: 50000, leads: 100}

    -- Workflow automation rules taught by owner
    automation_rules    JSONB DEFAULT '[]'::JSONB,   -- [{trigger, action, conditions}]

    -- Platform tier (controls what agent can do on platform)
    platform_tier       TEXT DEFAULT 'user',         -- 'user', 'power', 'admin'
    is_platform_admin   BOOLEAN DEFAULT false,       -- true only for Eduardo

    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(owner_id)
);

CREATE INDEX IF NOT EXISTS idx_business_profiles_owner ON business_profiles(owner_id);

-- ── 2. PLATFORM REQUESTS ────────────────────────────────────────────────────
-- When a user's Commander can't do something they need, it files a
-- platform request. Eduardo's admin agent sees these and can build the feature.
-- This is the "never-ending self-improving" feedback loop.

CREATE TABLE IF NOT EXISTS platform_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id    UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,

    -- Request details
    request_type    TEXT NOT NULL CHECK (request_type IN (
                        'integration',      -- need a new integration (e.g. Salesforce)
                        'feature',          -- need a new feature
                        'workflow',         -- need a custom workflow built
                        'fix',              -- something broken
                        'enhancement',      -- improve existing feature
                        'question',         -- asking for help / support
                        'data',             -- need access to specific data
                        'other'
                    )),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    priority        TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    context         JSONB DEFAULT '{}'::JSONB,  -- additional structured data

    -- Processing
    status          TEXT DEFAULT 'pending' CHECK (status IN (
                        'pending',          -- filed, not yet seen
                        'acknowledged',     -- Eduardo's agent saw it
                        'in_progress',      -- being built
                        'completed',        -- done, user can use it
                        'rejected',         -- won't build (with reason)
                        'needs_info'        -- Eduardo's agent needs more details
                    )),
    admin_notes     TEXT,           -- Eduardo's agent's response/notes
    assigned_task_id UUID,          -- links to platform_tasks if being built

    -- Which platform admin received/is handling this
    handled_by_owner_id UUID REFERENCES owners(id),

    -- Response sent back to the requesting Commander
    response_message TEXT,
    responded_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_platform_requests_requester ON platform_requests(requester_id);
CREATE INDEX IF NOT EXISTS idx_platform_requests_status ON platform_requests(status);
CREATE INDEX IF NOT EXISTS idx_platform_requests_admin ON platform_requests(handled_by_owner_id);


-- ── 3. AGENT MESSAGES (Inter-Agent Message Bus) ─────────────────────────────
-- Enables any agent to send a structured message to any other agent.
-- Key use case: user Commander → Eduardo's Commander (for requests, alerts, escalations).
-- Also used: Eduardo's Commander → user Commander (for announcements, completions).

CREATE TABLE IF NOT EXISTS agent_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Routing
    from_owner_id   UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    to_owner_id     UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    from_agent_type TEXT DEFAULT 'commander',
    to_agent_type   TEXT DEFAULT 'commander',

    -- Message
    message_type    TEXT NOT NULL CHECK (message_type IN (
                        'request',          -- asking for something
                        'response',         -- replying to a request
                        'announcement',     -- platform-wide news/update
                        'alert',            -- something urgent
                        'completion',       -- "I finished the thing you asked for"
                        'question',         -- need more info
                        'feedback'          -- rating / reaction
                    )),
    subject         TEXT,
    body            TEXT NOT NULL,
    payload         JSONB DEFAULT '{}'::JSONB,   -- structured data

    -- Threading
    thread_id       UUID,           -- for conversations (reply chains)
    reply_to_id     UUID REFERENCES agent_messages(id),

    -- State
    is_read         BOOLEAN DEFAULT false,
    read_at         TIMESTAMPTZ,

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_owner_id, is_read);
CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON agent_messages(from_owner_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_thread ON agent_messages(thread_id);


-- ── 4. PLATFORM TASKS (Code Agent Queue — VS Code Bridge) ───────────────────
-- The bridge between Eduardo's Commander and actual code changes.
--
-- Flow:
--   User requests feature → Eduardo's agent creates platform_task with full spec
--   → Code agent (Claude Code / VS Code) picks up the task
--   → Generates code, uploads diff
--   → Eduardo reviews in dashboard
--   → Approves → task status = 'approved' → triggers deploy
--
-- This makes ORB a truly self-improving platform.

CREATE TABLE IF NOT EXISTS platform_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,  -- always Eduardo

    -- Task definition
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    task_type       TEXT NOT NULL CHECK (task_type IN (
                        'new_integration',  -- build a new integration client
                        'new_feature',      -- build a new UI/API feature
                        'new_route',        -- add an API endpoint
                        'bug_fix',          -- fix a broken thing
                        'refactor',         -- improve existing code
                        'migration',        -- database schema change
                        'ui_change',        -- frontend only
                        'workflow',         -- automation workflow
                        'other'
                    )),

    -- Specification (what the code agent needs to know)
    spec            JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- spec shape: {
    --   files_to_create: [{path, description}],
    --   files_to_modify: [{path, changes}],
    --   acceptance_criteria: string[],
    --   tech_context: string,
    --   example_code: string
    -- }

    -- Links
    source_request_id UUID REFERENCES platform_requests(id),  -- which request triggered this

    -- Priority & effort
    priority        TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    estimated_hours FLOAT,
    target_branch   TEXT DEFAULT 'main',

    -- Status lifecycle
    status          TEXT DEFAULT 'pending' CHECK (status IN (
                        'pending',          -- waiting for code agent to pick up
                        'picked_up',        -- code agent is working on it
                        'needs_review',     -- code agent submitted diff, Eduardo reviews
                        'approved',         -- Eduardo approved → triggers deploy
                        'rejected',         -- Eduardo rejected (with reason)
                        'deployed',         -- successfully deployed
                        'failed'            -- deployment or build failed
                    )),

    -- Code agent output
    generated_code  TEXT,           -- the actual code/diff generated
    affected_files  JSONB DEFAULT '[]'::JSONB,   -- list of files changed
    diff_url        TEXT,           -- GitHub PR URL or similar

    -- Review
    review_notes    TEXT,           -- Eduardo's review notes
    reviewed_at     TIMESTAMPTZ,
    deployed_at     TIMESTAMPTZ,

    -- Assignment (which code agent picked this up)
    assigned_to     TEXT,           -- 'claude_code', 'cursor', 'manual'
    picked_up_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_platform_tasks_status ON platform_tasks(status);
CREATE INDEX IF NOT EXISTS idx_platform_tasks_owner ON platform_tasks(owner_id);
CREATE INDEX IF NOT EXISTS idx_platform_tasks_priority ON platform_tasks(priority, status);


-- ── 5. TRIGGERS ──────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_business_profiles_updated_at ON business_profiles;
CREATE TRIGGER trg_business_profiles_updated_at
    BEFORE UPDATE ON business_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_platform_requests_updated_at ON platform_requests;
CREATE TRIGGER trg_platform_requests_updated_at
    BEFORE UPDATE ON platform_requests FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_platform_tasks_updated_at ON platform_tasks;
CREATE TRIGGER trg_platform_tasks_updated_at
    BEFORE UPDATE ON platform_tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ── 6. RLS ───────────────────────────────────────────────────────────────────

ALTER TABLE business_profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_requests  ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_tasks      ENABLE ROW LEVEL SECURITY;


-- ═══════════════════════════════════════════════════════════════════════════
-- DONE. Tables created:
--   ✅ business_profiles
--   ✅ platform_requests
--   ✅ agent_messages
--   ✅ platform_tasks
-- ═══════════════════════════════════════════════════════════════════════════
