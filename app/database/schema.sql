-- ORB Platform Database Schema
-- Run this inside Supabase SQL Editor when you are ready to create the database tables.

create extension if not exists "pgcrypto";

create table if not exists owners (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    full_name text not null,
    business_name text,
    business_address text,
    address text,
    phone text,
    plan text not null,
    stripe_customer_id text,
    stripe_subscription_id text,
    stripe_card_last4 text,
    subscription_status text default 'inactive',
    subscription_plan text default 'free',
    subscription_amount_cents integer default 0,
    subscription_current_period_end timestamptz,
    trial_ends_at timestamptz,
    grace_period_ends_at timestamptz,
    spend_limit_cents integer not null default 0,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists agents (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    name text not null,
    role text not null,
    persona_description text,
    phone_number text,
    email_address text,
    brain_provider text not null,
    brain_model text,
    brain_api_key text,
    status text not null default 'active',
    trust_score integer not null default 0,
    total_actions integer not null default 0,
    monthly_cost_cents integer not null default 0,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists activity_log (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    owner_id uuid references owners(id) on delete cascade,
    action_type text not null,
    description text not null,
    outcome text,
    cost_cents integer not null default 0,
    needs_approval boolean not null default false,
    approved boolean,
    approved_at timestamptz,
    metadata jsonb,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists leads (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    owner_id uuid references owners(id) on delete cascade,
    contact_name text not null,
    phone text,
    email text,
    property_address text,
    city text,
    state text,
    motivation_score integer,
    status text not null default 'new',
    source text,
    call_count integer not null default 0,
    last_contact timestamptz,
    next_followup timestamptz,
    notes text,
    transcript text,
    metadata jsonb,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists tasks (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    owner_id uuid references owners(id) on delete cascade,
    title text not null,
    description text,
    priority text not null default 'normal',
    status text not null default 'pending',
    due_at timestamptz,
    completed_at timestamptz,
    related_lead_id uuid references leads(id) on delete set null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists paper_trades (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    instrument text not null,
    direction text not null,
    entry_price numeric(12, 4),
    exit_price numeric(12, 4),
    quantity numeric(12, 2) not null default 1,
    stop_loss numeric(12, 4),
    take_profit numeric(12, 4),
    pnl_dollars numeric(12, 2),
    setup_name text,
    strategy_version text,
    confidence_score integer,
    entry_reason text,
    exit_reason text,
    market_conditions jsonb,
    status text not null default 'open',
    opened_at timestamptz not null default timezone('utc', now()),
    closed_at timestamptz,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists content (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    owner_id uuid references owners(id) on delete cascade,
    content_type text,
    platform text,
    title text,
    body text,
    image_url text,
    status text not null default 'draft',
    scheduled_for timestamptz,
    published_at timestamptz,
    performance_data jsonb,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists trades (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    instrument text not null,
    direction text not null,
    entry_price numeric(12, 4),
    exit_price numeric(12, 4),
    pnl_dollars numeric(12, 2),
    setup_name text,
    confidence_score integer,
    status text not null default 'pending_approval',
    approved_by_human boolean not null default false,
    stop_loss numeric(12, 4),
    take_profit numeric(12, 4),
    created_at timestamptz not null default timezone('utc', now()),
    closed_at timestamptz
);

create table if not exists strategies (
    id uuid primary key default gen_random_uuid(),
    agent_id uuid references agents(id) on delete cascade,
    name text not null,
    description text,
    rules_json jsonb not null default '{}'::jsonb,
    source_trader text,
    win_rate numeric(5, 2),
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now())
);

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

create table if not exists chat_sessions (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    agent_role text not null,
    role text not null,
    message text not null,
    structured_payload jsonb,
    created_at timestamptz default now()
);

create index if not exists idx_agents_owner_id on agents(owner_id);
create index if not exists idx_activity_log_agent_id on activity_log(agent_id);
create index if not exists idx_leads_agent_id on leads(agent_id);
create index if not exists idx_trades_agent_id on trades(agent_id);
create index if not exists idx_strategies_agent_id on strategies(agent_id);
create index if not exists idx_tasks_agent_id on tasks(agent_id);
create index if not exists idx_paper_trades_agent_id on paper_trades(agent_id);
create index if not exists idx_content_owner_id on content(owner_id);
create index if not exists idx_commander_config_owner_id on commander_config(owner_id);
create index if not exists idx_chat_sessions_owner_id on chat_sessions(owner_id);
