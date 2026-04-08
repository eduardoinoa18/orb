-- ORB Platform schema (Level 1 foundation)
-- Run this file in Supabase SQL editor.

create extension if not exists "pgcrypto";

-- Owners (platform users)
create table if not exists owners (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  full_name text,
  business_name text,
  business_address text,
  phone text,
  plan text default 'personal',
  stripe_customer_id text,
  stripe_subscription_id text,
  stripe_card_last4 text,
  subscription_status text default 'inactive',
  subscription_plan text default 'free',
  subscription_amount_cents integer default 0,
  subscription_current_period_end timestamptz,
  trial_ends_at timestamptz,
  grace_period_ends_at timestamptz,
  spend_limit_cents integer default 15000,
  is_active boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Agent identities
create table if not exists agents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references owners(id),
  name text not null,
  role text not null,
  persona_description text,
  phone_number text,
  email_address text,
  brain_provider text default 'claude',
  brain_model text,
  brain_api_key text,
  status text default 'active',
  trust_score integer default 0,
  total_actions integer default 0,
  monthly_cost_cents integer default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- All agent activity
create table if not exists activity_log (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  owner_id uuid references owners(id),
  action_type text not null,
  description text,
  outcome text,
  cost_cents integer default 0,
  tokens_used integer default 0,
  needs_approval boolean default false,
  approved boolean,
  approved_at timestamptz,
  metadata jsonb,
  created_at timestamptz default now()
);

-- Wholesale leads (Rex)
create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  owner_id uuid references owners(id),
  contact_name text,
  phone text,
  email text,
  property_address text,
  city text,
  state text,
  motivation_score integer default 0,
  status text default 'new',
  source text,
  call_count integer default 0,
  last_contact timestamptz,
  next_followup timestamptz,
  notes text,
  transcript text,
  metadata jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Sequence enrollments
create table if not exists sequences (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id),
  agent_id uuid references agents(id),
  sequence_type text,
  current_step integer default 0,
  total_steps integer,
  next_action_at timestamptz,
  status text default 'active',
  created_at timestamptz default now()
);

-- Paper trades (Orion only - no live trading)
create table if not exists paper_trades (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  instrument text not null,
  direction text not null,
  entry_price decimal(10,4),
  exit_price decimal(10,4),
  quantity decimal(10,2) default 1,
  stop_loss decimal(10,4),
  take_profit decimal(10,4),
  pnl_dollars decimal(10,2),
  setup_name text,
  strategy_version text,
  confidence_score integer,
  entry_reason text,
  exit_reason text,
  market_conditions jsonb,
  status text default 'open',
  opened_at timestamptz default now(),
  closed_at timestamptz,
  created_at timestamptz default now()
);

-- Strategy versions (Orion tracks improvements)
create table if not exists strategies (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  name text not null,
  version text default '1.0',
  description text,
  rules_json jsonb,
  source_notes text,
  win_rate decimal(5,2),
  profit_factor decimal(5,2),
  total_paper_trades integer default 0,
  is_active boolean default false,
  created_at timestamptz default now()
);

-- Tasks (Atlas/all agents)
create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  owner_id uuid references owners(id),
  title text not null,
  description text,
  priority text default 'normal',
  status text default 'pending',
  due_at timestamptz,
  completed_at timestamptz,
  related_lead_id uuid references leads(id),
  created_at timestamptz default now()
);

-- Content queue (Nova)
create table if not exists content (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid references agents(id),
  owner_id uuid references owners(id),
  content_type text,
  platform text,
  title text,
  body text,
  image_url text,
  status text default 'draft',
  scheduled_for timestamptz,
  published_at timestamptz,
  performance_data jsonb,
  created_at timestamptz default now()
);

-- Daily cost tracking
create table if not exists daily_costs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references owners(id),
  date date default current_date,
  anthropic_cents integer default 0,
  openai_cents integer default 0,
  twilio_cents integer default 0,
  bland_cents integer default 0,
  total_cents integer default 0,
  created_at timestamptz default now()
);

-- Commander personalization
create table if not exists commander_config (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references owners(id) unique,
  commander_name text default 'Max',
  personality_style text default 'professional',
  communication_style text default 'concise',
  proactivity_level integer default 7,
  morning_briefing_enabled boolean default true,
  briefing_time text default '07:00',
  weekly_review_enabled boolean default true,
  review_day text default 'sunday',
  language text default 'en',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Commander conversation transcript
create table if not exists chat_sessions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references owners(id) on delete cascade,
  agent_role text not null,
  role text not null,
  message text not null,
  structured_payload jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_commander_config_owner_id on commander_config(owner_id);
create index if not exists idx_chat_sessions_owner_id on chat_sessions(owner_id);
