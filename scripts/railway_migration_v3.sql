-- ═══════════════════════════════════════════════════════════════════════════
-- ORB v3 Database Migration
-- Run in Supabase SQL Editor → New Query → Run
-- Safe to run multiple times (all use IF NOT EXISTS / ON CONFLICT DO NOTHING)
--
-- Adds:
--   1. channel_mappings   — maps external platform user IDs → ORB owner_id
--   2. dashboard_configs  — per-owner dashboard customization settings
--   3. agent_permissions  — per-agent scoped action permissions
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. CHANNEL MAPPINGS ─────────────────────────────────────────────────────
-- Maps an external platform user ID (e.g. WhatsApp phone, Telegram chat_id,
-- Discord user_id) to an ORB owner_id.
-- Used by all inbound webhook handlers to route messages to the right owner.

CREATE TABLE IF NOT EXISTS channel_mappings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,

    -- Which platform this mapping is for
    platform         TEXT NOT NULL CHECK (platform IN (
                        'whatsapp', 'telegram', 'sms', 'discord',
                        'instagram', 'messenger', 'teams', 'email'
                     )),

    -- The external identifier on that platform
    -- e.g. WhatsApp: '+15551234567'
    -- e.g. Telegram: '123456789'  (chat_id)
    -- e.g. Discord:  '987654321012345678'  (user_id)
    -- e.g. Instagram: '17841234567890'  (IGSID)
    -- e.g. Messenger: '5551234567890'   (PSID)
    external_id      TEXT NOT NULL,

    -- Optional: label for display in the dashboard
    label            TEXT,

    -- Whether this mapping is currently active
    is_active        BOOLEAN DEFAULT true,

    -- Timestamps
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now(),

    -- One external ID per platform per owner
    UNIQUE(platform, external_id)
);

-- Index: look up owner from platform + external_id (hot path on every inbound webhook)
CREATE INDEX IF NOT EXISTS idx_channel_mappings_lookup
    ON channel_mappings(platform, external_id)
    WHERE is_active = true;

-- Index: list all channels for an owner (dashboard display)
CREATE INDEX IF NOT EXISTS idx_channel_mappings_owner
    ON channel_mappings(owner_id);


-- ── 2. DASHBOARD CONFIGS ────────────────────────────────────────────────────
-- Stores per-owner dashboard preferences set via Commander or the Personalize page.
-- The frontend reads this on load and merges with localStorage as a fallback.

CREATE TABLE IF NOT EXISTS dashboard_configs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,

    -- JSON blob of DashboardPreferences
    -- Shape: {
    --   accent: 'blue' | 'emerald' | 'amber',
    --   modules: { commanderCTA, stats, activity, setup, quickLinks },
    --   hiddenNav: string[],
    --   customTabs: [{ id, label, href }],
    --   heroMessage: string | null
    -- }
    config           JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Who last modified this (can be 'owner' or 'commander')
    updated_by       TEXT DEFAULT 'owner',

    -- Timestamps
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now(),

    -- One config row per owner
    UNIQUE(owner_id)
);

-- Index: fetch config for a specific owner
CREATE INDEX IF NOT EXISTS idx_dashboard_configs_owner
    ON dashboard_configs(owner_id);


-- ── 3. AGENT PERMISSIONS ────────────────────────────────────────────────────
-- Scoped per-agent permission overrides.
-- Commander reads these to enforce what each agent is allowed to do.
-- The PermissionGuard in Python checks this table (or falls back to defaults).

CREATE TABLE IF NOT EXISTS agent_permissions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    agent_id         UUID REFERENCES agents(id) ON DELETE CASCADE,

    -- Which permission (must match Permission enum in permission_guard.py)
    permission       TEXT NOT NULL,

    -- Granted or revoked
    is_granted       BOOLEAN NOT NULL DEFAULT true,

    -- Optional expiry for time-limited grants
    expires_at       TIMESTAMPTZ,

    -- Who set this (owner or commander)
    granted_by       TEXT DEFAULT 'owner',

    -- Timestamps
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now(),

    -- One row per agent+permission combination
    UNIQUE(agent_id, permission)
);

-- Index: look up all permissions for an agent
CREATE INDEX IF NOT EXISTS idx_agent_permissions_agent
    ON agent_permissions(agent_id)
    WHERE is_granted = true;

-- Index: look up all agent permissions for an owner
CREATE INDEX IF NOT EXISTS idx_agent_permissions_owner
    ON agent_permissions(owner_id);


-- ── 4. UPDATED_AT TRIGGERS ──────────────────────────────────────────────────
-- Auto-update updated_at on every row modification

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_channel_mappings_updated_at ON channel_mappings;
CREATE TRIGGER trg_channel_mappings_updated_at
    BEFORE UPDATE ON channel_mappings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_dashboard_configs_updated_at ON dashboard_configs;
CREATE TRIGGER trg_dashboard_configs_updated_at
    BEFORE UPDATE ON dashboard_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_agent_permissions_updated_at ON agent_permissions;
CREATE TRIGGER trg_agent_permissions_updated_at
    BEFORE UPDATE ON agent_permissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ── 5. ROW LEVEL SECURITY ───────────────────────────────────────────────────
-- Owners can only read/write their own rows.
-- Enable if you're using Supabase RLS (recommended for production).

ALTER TABLE channel_mappings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_permissions ENABLE ROW LEVEL SECURITY;

-- channel_mappings: owners can only see their own mappings
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='channel_mappings' AND policyname='owner_isolation'
  ) THEN
    CREATE POLICY owner_isolation ON channel_mappings
        USING (owner_id::text = current_setting('app.owner_id', true));
  END IF;
END $$;

-- dashboard_configs: owners can only see their own config
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='dashboard_configs' AND policyname='owner_isolation'
  ) THEN
    CREATE POLICY owner_isolation ON dashboard_configs
        USING (owner_id::text = current_setting('app.owner_id', true));
  END IF;
END $$;

-- agent_permissions: owners can only see their own agent permissions
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='agent_permissions' AND policyname='owner_isolation'
  ) THEN
    CREATE POLICY owner_isolation ON agent_permissions
        USING (owner_id::text = current_setting('app.owner_id', true));
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════════════
-- DONE. Tables created:
--   ✅ channel_mappings
--   ✅ dashboard_configs
--   ✅ agent_permissions
-- ═══════════════════════════════════════════════════════════════════════════
