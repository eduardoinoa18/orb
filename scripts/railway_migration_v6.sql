-- ============================================================
-- ORB Platform — Supabase Migration v6
-- New Agents: Zara · Finn · Vest
-- Date: 2026-04-19
-- Run in: Supabase Dashboard → SQL Editor
-- ============================================================

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

-- ============================================================
-- PLATFORM VIEWS (for admin dashboard)
-- ============================================================

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

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE onboarding_flows IS 'Zara: step-by-step onboarding progress per owner';
COMMENT ON TABLE nps_responses IS 'Zara: Net Promoter Score survey responses';
COMMENT ON TABLE transactions IS 'Finn: financial transaction ledger (income & expenses)';
COMMENT ON TABLE invoices IS 'Finn: invoice lifecycle management';
COMMENT ON TABLE portfolio_holdings IS 'Vest: investment portfolio positions per owner';
COMMENT ON TABLE investment_memos IS 'Vest: AI-written investment research memos';

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
