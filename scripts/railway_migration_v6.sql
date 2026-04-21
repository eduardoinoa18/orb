-- ============================================================
-- ORB Platform — Supabase Migration v6
-- New Agents: Zara · Finn · Vest
-- Date: 2026-04-19
-- Run in: Supabase Dashboard → SQL Editor
-- ============================================================

-- Ensure UUID helpers exist for gen_random_uuid().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- ZARA — Customer Success & Onboarding
-- ============================================================

-- Onboarding flows table
CREATE TABLE IF NOT EXISTS onboarding_flows (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    steps           JSONB NOT NULL DEFAULT '{}',
    current_step    TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    business_profile_snapshot JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id)
);

CREATE INDEX IF NOT EXISTS idx_onboarding_flows_owner ON onboarding_flows(owner_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_flows_completed ON onboarding_flows(completed_at) WHERE completed_at IS NOT NULL;

-- NPS responses table
CREATE TABLE IF NOT EXISTS nps_responses (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    score           SMALLINT CHECK (score BETWEEN 0 AND 10),
    comment         TEXT,
    category        TEXT CHECK (category IN ('promoter', 'passive', 'detractor')),
    status          TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'responded', 'expired')),
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    responded_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nps_responses_owner ON nps_responses(owner_id);
CREATE INDEX IF NOT EXISTS idx_nps_responses_status ON nps_responses(status);
CREATE INDEX IF NOT EXISTS idx_nps_responses_category ON nps_responses(category);

-- ============================================================
-- FINN — Finance & Bookkeeping
-- ============================================================

-- Financial transactions
CREATE TABLE IF NOT EXISTS transactions (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id    UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    amount      NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    category    TEXT NOT NULL,
    description TEXT NOT NULL,
    txn_type    TEXT NOT NULL CHECK (txn_type IN ('income', 'expense')),
    txn_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    source      TEXT DEFAULT 'manual',  -- manual | stripe | quickbooks | wave
    reference   TEXT,                   -- external reference / receipt number
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_owner ON transactions(owner_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(txn_type);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
-- Keep monthly queries fast without using non-immutable expressions in index definitions.
CREATE INDEX IF NOT EXISTS idx_transactions_owner_txn_date ON transactions(owner_id, txn_date);

-- Invoices
CREATE TABLE IF NOT EXISTS invoices (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    invoice_number      TEXT NOT NULL UNIQUE,
    client_name         TEXT NOT NULL,
    client_email        TEXT NOT NULL,
    line_items          JSONB NOT NULL DEFAULT '[]',
    subtotal            NUMERIC(14, 2) NOT NULL,
    tax_amount          NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total               NUMERIC(14, 2) NOT NULL,
    due_date            DATE NOT NULL,
    notes               TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'sent', 'overdue', 'paid', 'cancelled')),
    sent_at             TIMESTAMPTZ,
    paid_at             TIMESTAMPTZ,
    payment_reference   TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_owner ON invoices(owner_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date);

-- Auto-update updated_at on invoices
CREATE OR REPLACE FUNCTION update_invoices_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_invoices_updated_at ON invoices;
CREATE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION update_invoices_updated_at();

-- ============================================================
-- VEST — Investment & Portfolio
-- ============================================================

-- Portfolio holdings
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id    UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    asset_type  TEXT NOT NULL DEFAULT 'stock'
                CHECK (asset_type IN ('stock', 'etf', 'crypto', 'real_estate', 'bond', 'alternative', 'other')),
    quantity    NUMERIC(20, 6) NOT NULL CHECK (quantity > 0),
    avg_cost    NUMERIC(20, 4) NOT NULL CHECK (avg_cost > 0),
    notes       TEXT DEFAULT '',
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_owner ON portfolio_holdings(owner_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ticker ON portfolio_holdings(ticker);

-- Investment memos
CREATE TABLE IF NOT EXISTS investment_memos (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id        UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    position_type   TEXT DEFAULT 'long' CHECK (position_type IN ('long', 'short', 'watch', 'overview')),
    content         TEXT NOT NULL,
    price_at_writing NUMERIC(20, 4),
    written_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investment_memos_owner ON investment_memos(owner_id);
CREATE INDEX IF NOT EXISTS idx_investment_memos_ticker ON investment_memos(ticker);

-- ============================================================
-- IDENTITY + EXECUTION HARDENING
-- ============================================================

-- Ensure agent identity fields needed for real-world execution are present.
ALTER TABLE IF EXISTS agents
    ADD COLUMN IF NOT EXISTS email_address TEXT,
    ADD COLUMN IF NOT EXISTS phone_number TEXT,
    ADD COLUMN IF NOT EXISTS agent_type TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';

-- Owner-scoped uniqueness for identity channels.
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_owner_email_unique
    ON agents(owner_id, lower(email_address))
    WHERE email_address IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_owner_phone_unique
    ON agents(owner_id, phone_number)
    WHERE phone_number IS NOT NULL;

-- Audit log for real external executions performed by agents.
CREATE TABLE IF NOT EXISTS integration_execution_events (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id            UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    agent_id            UUID REFERENCES agents(id) ON DELETE SET NULL,
    agent_slug          TEXT NOT NULL,
    tool_name           TEXT NOT NULL,
    integration_slug    TEXT NOT NULL,
    action_type         TEXT NOT NULL DEFAULT 'execute'
                        CHECK (action_type IN ('execute', 'simulate', 'approval_requested', 'approval_denied')),
    success             BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms          INTEGER,
    error_message       TEXT,
    request_payload     JSONB DEFAULT '{}',
    response_payload    JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exec_events_owner_created ON integration_execution_events(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exec_events_success ON integration_execution_events(success);
CREATE INDEX IF NOT EXISTS idx_exec_events_tool ON integration_execution_events(tool_name);

-- ============================================================
-- AGENT SKILLS — Extend for new agents
-- ============================================================

-- Insert default skill profiles for new agents
-- (These will be auto-created on first use via skill_engine.py,
--  but seeding here ensures platform-level admin can see them)

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

-- Enable RLS on all new tables
ALTER TABLE onboarding_flows      ENABLE ROW LEVEL SECURITY;
ALTER TABLE nps_responses         ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices              ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_holdings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE investment_memos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_execution_events ENABLE ROW LEVEL SECURITY;

-- Owners can only see their own data
DROP POLICY IF EXISTS "owner_onboarding" ON onboarding_flows;
CREATE POLICY "owner_onboarding" ON onboarding_flows
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_nps" ON nps_responses;
CREATE POLICY "owner_nps" ON nps_responses
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_transactions" ON transactions;
CREATE POLICY "owner_transactions" ON transactions
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_invoices" ON invoices;
CREATE POLICY "owner_invoices" ON invoices
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_portfolio" ON portfolio_holdings;
CREATE POLICY "owner_portfolio" ON portfolio_holdings
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_investment_memos" ON investment_memos;
CREATE POLICY "owner_investment_memos" ON investment_memos
    FOR ALL USING (owner_id::text = auth.uid()::text);

DROP POLICY IF EXISTS "owner_exec_events" ON integration_execution_events;
CREATE POLICY "owner_exec_events" ON integration_execution_events
    FOR ALL USING (owner_id::text = auth.uid()::text);

-- Service role bypass (for backend)
DROP POLICY IF EXISTS "service_onboarding" ON onboarding_flows;
CREATE POLICY "service_onboarding" ON onboarding_flows
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_nps" ON nps_responses;
CREATE POLICY "service_nps" ON nps_responses
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_transactions" ON transactions;
CREATE POLICY "service_transactions" ON transactions
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_invoices" ON invoices;
CREATE POLICY "service_invoices" ON invoices
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_portfolio" ON portfolio_holdings;
CREATE POLICY "service_portfolio" ON portfolio_holdings
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_investment_memos" ON investment_memos;
CREATE POLICY "service_investment_memos" ON investment_memos
    FOR ALL TO service_role USING (true);

DROP POLICY IF EXISTS "service_exec_events" ON integration_execution_events;
CREATE POLICY "service_exec_events" ON integration_execution_events
    FOR ALL TO service_role USING (true);

-- ============================================================
-- PLATFORM VIEWS (for admin dashboard)
-- ============================================================

-- Compatibility hardening: older databases may have activity_log without owner_id.
ALTER TABLE IF EXISTS activity_log
    ADD COLUMN IF NOT EXISTS owner_id UUID;

-- Platform health summary view
CREATE OR REPLACE VIEW platform_health_summary AS
SELECT
    (SELECT COUNT(*) FROM owners)                                       AS total_owners,
    (SELECT COUNT(*) FROM owners WHERE created_at > NOW() - INTERVAL '7 days') AS new_owners_7d,
    (SELECT COUNT(*) FROM onboarding_flows WHERE completed_at IS NOT NULL)      AS completed_onboarding,
    (SELECT COUNT(*) FROM onboarding_flows WHERE completed_at IS NULL)          AS incomplete_onboarding,
    (SELECT ROUND(AVG(score), 1) FROM nps_responses WHERE status = 'responded') AS avg_nps_score,
    (SELECT COUNT(*) FROM invoices WHERE status = 'overdue')                    AS overdue_invoices,
    (SELECT COALESCE(SUM(total), 0) FROM invoices WHERE status = 'overdue')     AS overdue_invoice_value,
    (SELECT COUNT(*) FROM portfolio_holdings)                                   AS total_portfolio_positions,
    NOW()                                                                       AS computed_at;

-- Owner retention view (for Zara churn analysis)
CREATE OR REPLACE VIEW owner_retention AS
SELECT
    op.id AS owner_id,
    op.created_at AS joined_at,
    MAX(al.created_at) AS last_activity,
    EXTRACT(DAY FROM NOW() - MAX(al.created_at)) AS days_since_active,
    COUNT(DISTINCT al.id) AS total_activities,
    CASE
        WHEN MAX(al.created_at) > NOW() - INTERVAL '7 days' THEN 'active'
        WHEN MAX(al.created_at) > NOW() - INTERVAL '30 days' THEN 'at_risk'
        ELSE 'churned'
    END AS retention_status
FROM owners op
LEFT JOIN activity_log al ON al.owner_id::text = op.id::text
GROUP BY op.id, op.created_at;

-- Owner execution readiness view (identity + real action quality)
CREATE OR REPLACE VIEW owner_execution_readiness AS
SELECT
        op.id AS owner_id,
        CASE WHEN op.email IS NULL OR op.email = '' THEN false ELSE true END AS owner_email_present,
        CASE WHEN op.phone IS NULL OR op.phone = '' THEN false ELSE true END AS owner_phone_present,
        (SELECT COUNT(*) FROM agents a WHERE a.owner_id = op.id AND COALESCE(a.is_active, true) = true AND COALESCE(a.status, 'active') <> 'deprovisioned') AS active_agents,
        (SELECT COUNT(*) FROM agents a
            WHERE a.owner_id = op.id
                AND COALESCE(a.is_active, true) = true
                AND COALESCE(a.status, 'active') <> 'deprovisioned'
                AND (
                        a.name IS NULL OR a.name = '' OR
                        a.agent_type IS NULL OR a.agent_type = '' OR
                        a.email_address IS NULL OR a.email_address = '' OR
                        a.phone_number IS NULL OR a.phone_number = ''
                )) AS active_agents_missing_identity,
        (SELECT COUNT(*) FROM owner_integrations oi WHERE oi.owner_id = op.id AND oi.status = 'connected') AS connected_integrations,
        (SELECT COUNT(*) FROM integration_execution_events ie WHERE ie.owner_id = op.id) AS execution_attempts,
        (SELECT COUNT(*) FROM integration_execution_events ie WHERE ie.owner_id = op.id AND ie.success = true) AS successful_executions,
        (SELECT ROUND(100.0 * AVG(CASE WHEN ie.success THEN 1 ELSE 0 END), 1)
                FROM integration_execution_events ie
                WHERE ie.owner_id = op.id
                    AND ie.created_at > NOW() - INTERVAL '30 days') AS success_rate_30d,
        NOW() AS computed_at
FROM owners op;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE onboarding_flows IS 'Zara: step-by-step onboarding progress per owner';
COMMENT ON TABLE nps_responses IS 'Zara: Net Promoter Score survey responses';
COMMENT ON TABLE transactions IS 'Finn: financial transaction ledger (income & expenses)';
COMMENT ON TABLE invoices IS 'Finn: invoice lifecycle management';
COMMENT ON TABLE portfolio_holdings IS 'Vest: investment portfolio positions per owner';
COMMENT ON TABLE investment_memos IS 'Vest: AI-written investment research memos';
COMMENT ON TABLE integration_execution_events IS 'Cross-agent audit of real external actions executed via integrations';

-- ============================================================
-- DONE
-- ============================================================
-- After running this migration:
-- 1. Verify tables in Supabase Table Editor
-- 2. Check RLS policies in Auth > Policies
-- 3. Test by calling GET /zara/onboarding/{owner_id}
--    and GET /finn/snapshot/{owner_id}
--    and GET /vest/portfolio/{owner_id}
-- ============================================================
