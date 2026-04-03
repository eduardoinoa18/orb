-- ORB Platform Database Schema
-- Create this in your Supabase SQL Editor and run it once
-- This creates all 9 tables needed for ORB to function

-- ============================================
-- TABLE 1: OWNERS (Users)
-- ============================================
CREATE TABLE IF NOT EXISTS owners (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  phone TEXT,
  name TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('superadmin','admin','user','trial')),
  is_superadmin BOOLEAN DEFAULT false,
  monthly_cost_override_cents INTEGER DEFAULT NULL,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  subscription_status TEXT DEFAULT 'active', -- active, paused, cancelled
  subscription_plan TEXT DEFAULT 'free', -- free, pro, enterprise
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  stripe_card_last4 TEXT,
  subscription_amount_cents INT DEFAULT 0,
  subscription_current_period_end TIMESTAMPTZ,
  trial_ends_at TIMESTAMPTZ,
  grace_period_ends_at TIMESTAMPTZ,
  monthly_ai_budget_cents INT DEFAULT 5000,
  daily_max_cost_cents INT DEFAULT 1500,
  current_month_spent_cents INT DEFAULT 0
);

-- ============================================
-- TABLE 2: AGENTS (AI Agents per Owner)
-- ============================================
CREATE TABLE IF NOT EXISTS agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  agent_type TEXT NOT NULL, -- rex, aria, nova, orion, sage
  phone_number TEXT, -- For Rex: which Twilio number to use
  email_address TEXT, -- For Aria: which Gmail account
  name TEXT, -- Display name for UI
  api_key TEXT, -- For N8N workflows specific to this agent
  daily_budget_cents INT DEFAULT 100,
  is_active BOOLEAN DEFAULT true,
  last_action_at TIMESTAMP,
  error_count_today INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- TABLE 3: ACTIVITY_LOG (Audit Trail)
-- ============================================
CREATE TABLE IF NOT EXISTS activity_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
  request_id TEXT, -- X-Request-ID for tracing
  action_type TEXT NOT NULL, -- sms, call, claude, trade, email, lead, task, error
  description TEXT NOT NULL,
  outcome TEXT, -- sent, failed, approved, rejected, queued, completed
  cost_cents INT DEFAULT 0,
  needs_approval BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT now(),
  
  -- Metadata for debugging
  error_message TEXT,
  raw_response TEXT, -- For debugging API responses
  external_id TEXT -- e.g., Twilio SID, Bland AI call_id
);

-- ============================================
-- TABLE 4: LEADS (For Rex)
-- ============================================
CREATE TABLE IF NOT EXISTS leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  phone TEXT NOT NULL,
  email TEXT,
  name TEXT,
  company TEXT,
  source TEXT, -- website_form, phone_call, email, facebook, etc
  status TEXT DEFAULT 'new', -- new, contacted, interested, qualified, appointment_set, closed_won, closed_lost, nurturing
  temperature INT, -- 1-10 hot/cold score from Rex
  notes TEXT,
  last_contacted_at TIMESTAMP,
  next_followup_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  
  -- Suppress duplicate within 30 days
  phone_hash TEXT -- md5(phone) for duplicate detection
);

-- ============================================
-- TABLE 5: SEQUENCES (N8N Workflows)
-- ============================================
CREATE TABLE IF NOT EXISTS sequences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  workflow_type TEXT, -- 30_day_nurture, 90_day_nurture, hot_lead_urgent
  n8n_workflow_id TEXT, -- ID in your N8N instance
  started_at TIMESTAMP DEFAULT now(),
  next_action_at TIMESTAMP,
  last_action_at TIMESTAMP,
  status TEXT DEFAULT 'active', -- active, paused, completed
  action_count INT DEFAULT 0
);

-- ============================================
-- TABLE 6: PAPER_TRADES (Orion Test Trades)
-- ============================================
CREATE TABLE IF NOT EXISTS paper_trades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
  
  symbol TEXT NOT NULL, -- ES, NQ, CL, etc
  direction TEXT NOT NULL, -- long, short
  entry_price DECIMAL(12, 4),
  stop_loss_price DECIMAL(12, 4),
  target_price DECIMAL(12, 4),
  
  quantity INT DEFAULT 1,
  status TEXT DEFAULT 'open', -- open, closed, analyzed
  
  entry_at TIMESTAMP,
  exit_at TIMESTAMP,
  entry_reason TEXT,
  exit_reason TEXT, -- stop_hit, target_hit, manual_close, session_close
  
  unrealized_pnl_cents INT DEFAULT 0, -- P&L in cents
  realized_pnl_cents INT DEFAULT 0,
  pnl_percent DECIMAL(6, 2) DEFAULT 0,
  
  confidence_score INT, -- 1-10 how confident was Orion
  
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- TABLE 7: STRATEGIES (Orion Trading Rules)
-- ============================================
CREATE TABLE IF NOT EXISTS strategies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  
  name TEXT NOT NULL,
  description TEXT,
  entry_rule TEXT, -- "price > ema_20 AND rsi < 30"
  exit_rule TEXT,
  
  version INT DEFAULT 1, -- v1, v2, v3 as strategy improves
  status TEXT DEFAULT 'testing', -- testing, live, retired
  
  performance_win_pct DECIMAL(5, 2), -- Percentage of trades that were profitable
  performance_avg_win_cents INT, -- Average profit per winning trade
  performance_avg_loss_cents INT, -- Average loss per losing trade
  performance_trades_total INT DEFAULT 0,
  
  created_at TIMESTAMP DEFAULT now(),
  last_tested_at TIMESTAMP,
  last_performance_update_at TIMESTAMP,
  
  -- For learning/improvement
  last_improvement_suggestion TEXT,
  owner_approved BOOLEAN DEFAULT true
);

-- ============================================
-- TABLE 8: TASKS (Aria Reminders)
-- ============================================
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  
  title TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'todo', -- todo, in_progress, done, cancelled
  
  priority TEXT DEFAULT 'normal', -- low, normal, high, urgent
  due_at TIMESTAMP,
  
  source TEXT, -- aria_calendar_alert, aria_deadline_reminder, owner_created
  
  created_at TIMESTAMP DEFAULT now(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);

-- ============================================
-- TABLE 9: CONTENT (Nova Drafts)
-- ============================================
CREATE TABLE IF NOT EXISTS content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  
  content_type TEXT NOT NULL, -- social_post, listing, email, article
  platform TEXT, -- linkedin, facebook, instagram, website_listing, etc
  
  title TEXT,
  body TEXT NOT NULL,
  image_url TEXT,
  
  status TEXT DEFAULT 'draft', -- draft, pending_approval, approved, scheduled, published, rejected
  
  rejection_reason TEXT, -- Why owner rejected it
  
  -- Approval workflow
  requested_approval_at TIMESTAMP,
  approved_by_owner_at TIMESTAMP,
  owner_approval_feedback TEXT,
  
  -- Publishing
  scheduled_for TIMESTAMP,
  published_at TIMESTAMP,
  published_url TEXT,
  
  -- Performance
  engagement_count INT DEFAULT 0,
  click_count INT DEFAULT 0,
  
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- TABLE 10: DAILY_COSTS (Cost Tracking)
-- ============================================
CREATE TABLE IF NOT EXISTS daily_costs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  cost_date DATE NOT NULL,
  
  rex_cost_cents INT DEFAULT 0,
  aria_cost_cents INT DEFAULT 0,
  nova_cost_cents INT DEFAULT 0,
  orion_cost_cents INT DEFAULT 0,
  sage_cost_cents INT DEFAULT 0,
  
  total_cost_cents INT DEFAULT 0, -- Sum of above
  
  created_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- TABLE 11: COMMANDER_CONFIG (Owner preferences)
-- ============================================
CREATE TABLE IF NOT EXISTS commander_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID REFERENCES owners(id) UNIQUE,
  commander_name TEXT DEFAULT 'Max',
  personality_style TEXT DEFAULT 'professional',
  communication_style TEXT DEFAULT 'concise',
  proactivity_level INTEGER DEFAULT 7,
  morning_briefing_enabled BOOLEAN DEFAULT true,
  briefing_time TEXT DEFAULT '07:00',
  weekly_review_enabled BOOLEAN DEFAULT true,
  review_day TEXT DEFAULT 'sunday',
  language TEXT DEFAULT 'en',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- TABLE 12: FEATURE_FLAGS (runtime toggles)
-- ============================================
CREATE TABLE IF NOT EXISTS feature_flags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flag_name TEXT UNIQUE NOT NULL,
  is_enabled BOOLEAN DEFAULT false,
  enabled_for_plans TEXT[] DEFAULT '{}',
  description TEXT,
  updated_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO feature_flags (flag_name, is_enabled, enabled_for_plans, description)
VALUES
  ('computer_use', false, '{full_team}', 'Allow agents to control browser'),
  ('whatsapp_commander', true, '{professional,full_team}', 'Commander accessible via WhatsApp'),
  ('custom_agent_builder', true, '{professional,full_team}', 'Users can create custom agents'),
  ('voice_input', true, '{starter,professional,full_team}', 'Voice input to Commander'),
  ('leaderboard', false, '{}', 'Public opt-in leaderboard')
ON CONFLICT (flag_name) DO NOTHING;

-- ============================================
-- TABLE 13: CHAT_SESSIONS (Commander conversation history)
-- ============================================
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID REFERENCES owners(id) ON DELETE CASCADE,
  agent_role TEXT NOT NULL,
  role TEXT NOT NULL,
  message TEXT NOT NULL,
  structured_payload JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES (For Speed)
-- ============================================

-- Speed up finding leads by phone
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_owner ON leads(owner_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_phone_hash ON leads(phone_hash);

-- Speed up finding activity logs
CREATE INDEX IF NOT EXISTS idx_activity_agent ON activity_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_activity_owner ON activity_log(owner_id);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_request_id ON activity_log(request_id);

-- Speed up finding agents
CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_id);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(is_active);

-- Speed up paper trades queries
CREATE INDEX IF NOT EXISTS idx_paper_trades_agent ON paper_trades(agent_id);
CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_paper_trades_owner ON paper_trades(owner_id);

-- Speed up sequences
CREATE INDEX IF NOT EXISTS idx_sequences_lead ON sequences(lead_id);
CREATE INDEX IF NOT EXISTS idx_sequences_next ON sequences(next_action_at);
CREATE INDEX IF NOT EXISTS idx_sequences_owner ON sequences(owner_id);

-- Speed up content queries
CREATE INDEX IF NOT EXISTS idx_content_owner ON content(owner_id);
CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);

-- Commander indexes
CREATE INDEX IF NOT EXISTS idx_commander_config_owner ON commander_config(owner_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner ON chat_sessions(owner_id);

-- Speed up task queries
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- ============================================
-- ROW LEVEL SECURITY (Data Isolation)
-- ============================================
-- These policies ensure each owner only sees their own data

-- Enable RLS on all tables
ALTER TABLE owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE content ENABLE ROW LEVEL SECURITY;
ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_costs ENABLE ROW LEVEL SECURITY;

-- Owners see only their own record
CREATE POLICY "owners see own record"
ON owners FOR ALL
USING (id = auth.uid());

-- Agents: owners see only their own agents
CREATE POLICY "owners see own agents"
ON agents FOR ALL
USING (owner_id = auth.uid());

-- Leads: owners see only their own leads
CREATE POLICY "owners see own leads"
ON leads FOR ALL
USING (owner_id = auth.uid());

-- Activity: owners see only their own activity
CREATE POLICY "owners see own activity"
ON activity_log FOR ALL
USING (owner_id = auth.uid());

-- Paper trades: owners see only their own trades
CREATE POLICY "owners see own paper trades"
ON paper_trades FOR ALL
USING (owner_id = auth.uid());

-- Strategies: owners see only their own strategies
CREATE POLICY "owners see own strategies"
ON strategies FOR ALL
USING (owner_id = auth.uid());

-- Tasks: owners see only their own tasks
CREATE POLICY "owners see own tasks"
ON tasks FOR ALL
USING (owner_id = auth.uid());

-- Content: owners see only their own content
CREATE POLICY "owners see own content"
ON content FOR ALL
USING (owner_id = auth.uid());

-- Sequences: owners see only their own sequences
CREATE POLICY "owners see own sequences"
ON sequences FOR ALL
USING (owner_id = auth.uid());

-- Daily costs: owners see only their own costs
CREATE POLICY "owners see own daily costs"
ON daily_costs FOR ALL
USING (owner_id = auth.uid());

-- ============================================
-- DONE
-- ============================================
-- Copy the entire SQL above.
-- Go to https://supabase.com/dashboard → SQL Editor
-- Paste it and click "Run"
-- You should see "Executed successfully"
-- Done! All tables are ready.
