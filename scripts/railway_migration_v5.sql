-- ORB Platform Migration v5
-- New tables for:
--   1. Code Agent Protocol (bi-directional VS Code bridge)
--   2. Agent Skill Engine (adaptive skill profiles)
--   3. Extended platform_tasks columns
--
-- Run this in Supabase SQL Editor after migrations v3 and v4.

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Code Agent Status (heartbeat from VS Code / Claude Code agents)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS code_agent_status (
    agent_id         TEXT PRIMARY KEY,
    status           TEXT NOT NULL DEFAULT 'idle',
    current_task_id  UUID,
    capabilities     JSONB NOT NULL DEFAULT '[]',
    version          TEXT,
    last_seen        TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Task Events (bi-directional protocol messages)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS task_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL,
    event_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'platform_tasks') THEN
        ALTER TABLE task_events ADD CONSTRAINT fk_task_events_task
            FOREIGN KEY (task_id) REFERENCES platform_tasks(id) ON DELETE CASCADE;
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_task_events_task_id    ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_event_type ON task_events(event_type);
CREATE INDEX IF NOT EXISTS idx_task_events_created_at ON task_events(created_at DESC);

-- ────────────────────────────────────────────────────────────────────────────
-- 3. Agent Skills (adaptive skill profiles per agent per owner)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_skills (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_slug           TEXT NOT NULL,
    owner_id             UUID NOT NULL,
    core_skills          JSONB NOT NULL DEFAULT '[]',
    expanded_skills      JSONB NOT NULL DEFAULT '[]',
    pending_skills       JSONB NOT NULL DEFAULT '[]',
    skill_scores         JSONB NOT NULL DEFAULT '{}',
    business_adaptations JSONB NOT NULL DEFAULT '[]',
    last_review          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (agent_slug, owner_id)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'owners') THEN
        ALTER TABLE agent_skills ADD CONSTRAINT fk_agent_skills_owner
            FOREIGN KEY (owner_id) REFERENCES owners(id) ON DELETE CASCADE;
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_skills_owner  ON agent_skills(owner_id);
CREATE INDEX IF NOT EXISTS idx_agent_skills_slug   ON agent_skills(agent_slug);
CREATE INDEX IF NOT EXISTS idx_agent_skills_review ON agent_skills(last_review);

CREATE OR REPLACE FUNCTION update_agent_skills_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_agent_skills_updated_at ON agent_skills;
CREATE TRIGGER trg_agent_skills_updated_at
    BEFORE UPDATE ON agent_skills
    FOR EACH ROW EXECUTE FUNCTION update_agent_skills_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- 4. Extend platform_tasks for bi-directional protocol
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS last_agent_activity TIMESTAMPTZ;
ALTER TABLE platform_tasks ADD COLUMN IF NOT EXISTS agent_progress INTEGER DEFAULT 0;

-- ────────────────────────────────────────────────────────────────────────────
-- 5. Row Level Security
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE code_agent_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_skills       ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_only_code_agent_status" ON code_agent_status;
CREATE POLICY "service_only_code_agent_status"
    ON code_agent_status USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_only_task_events" ON task_events;
CREATE POLICY "service_only_task_events"
    ON task_events USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "owner_reads_own_skills" ON agent_skills;
CREATE POLICY "owner_reads_own_skills"
    ON agent_skills FOR SELECT
    USING (owner_id = auth.uid()::uuid);

DROP POLICY IF EXISTS "owner_writes_own_skills" ON agent_skills;
CREATE POLICY "owner_writes_own_skills"
    ON agent_skills FOR ALL
    USING (owner_id = auth.uid()::uuid);

COMMIT;
