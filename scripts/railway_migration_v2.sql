-- ═══════════════════════════════════════════════════════════════════════════
-- ORB v2 Database Migration
-- Run this in Supabase SQL Editor → New Query → Run
-- Safe to run multiple times (all use IF NOT EXISTS / ON CONFLICT DO NOTHING)
-- ═══════════════════════════════════════════════════════════════════════════

-- Enable pgcrypto if not already enabled
create extension if not exists "pgcrypto";

-- ── 1. Add password_hash to owners ─────────────────────────────────────────
alter table owners add column if not exists password_hash text;
alter table owners add column if not exists name text;
alter table owners add column if not exists industry text;
alter table owners add column if not exists onboarding_status text default 'pending';
alter table owners add column if not exists onboarding_completed_at timestamptz;
alter table owners add column if not exists is_superadmin boolean default false;

-- ── 2. Integration Providers (catalog) ─────────────────────────────────────
create table if not exists integration_providers (
    id uuid primary key default gen_random_uuid(),
    slug text unique not null,
    name text not null,
    category text not null,
    auth_type text not null,
    description text,
    docs_url text,
    logo_emoji text default '🔌',
    required_fields jsonb default '[]'::jsonb,
    optional_fields jsonb default '[]'::jsonb,
    is_active boolean default true,
    created_at timestamptz default now()
);

-- ── 3. Owner Integrations (connection state) ────────────────────────────────
create table if not exists owner_integrations (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    provider_slug text not null,
    status text default 'disconnected',
    last_tested_at timestamptz,
    last_sync_at timestamptz,
    error_message text,
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(owner_id, provider_slug)
);

-- ── 4. Integration Credentials (encrypted) ─────────────────────────────────
create table if not exists integration_credentials (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    provider_slug text not null,
    field_name text not null,
    encrypted_value text not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(owner_id, provider_slug, field_name)
);

-- ── 5. Integration Sync Logs ────────────────────────────────────────────────
create table if not exists integration_sync_logs (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    provider_slug text not null,
    event_type text not null,
    status text not null,
    message text,
    latency_ms integer,
    created_at timestamptz default now()
);

-- ── 6. Per-Agent Settings ───────────────────────────────────────────────────
create table if not exists agent_settings (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    agent_slug text not null,
    daily_budget_cents integer default 500,
    is_enabled boolean default true,
    autonomy_level integer default 5,
    channels jsonb default '["sms"]'::jsonb,
    permissions jsonb default '{}'::jsonb,
    schedule_config jsonb default '{}'::jsonb,
    memory_context jsonb default '{}'::jsonb,
    kill_switch boolean default false,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(owner_id, agent_slug)
);

-- ── 7. Extend commander_config ──────────────────────────────────────────────
alter table commander_config add column if not exists safe_mode boolean default false;
alter table commander_config add column if not exists autonomy_level integer default 5;
alter table commander_config add column if not exists channel_preferences jsonb default '["sms"]'::jsonb;
alter table commander_config add column if not exists approval_rules jsonb default '{}'::jsonb;
alter table commander_config add column if not exists persona text default '';
alter table commander_config add column if not exists training_examples jsonb default '[]'::jsonb;

-- ── 7b. Platform Settings (encrypted key-value store) ───────────────────────
create table if not exists platform_settings (
    id          uuid primary key default gen_random_uuid(),
    key         text not null unique,
    value       text not null,
    description text default '',
    category    text default 'general',
    owner_id    text default '',
    created_at  timestamptz default now(),
    updated_at  timestamptz default now()
);

-- ── 8. Ensure columns exist (handles tables created by an older schema) ──────
-- If an older schema used `integration_key`, rename it to `provider_slug`.
do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'owner_integrations'
          and column_name = 'integration_key'
    ) and not exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'owner_integrations'
          and column_name = 'provider_slug'
    ) then
        alter table owner_integrations rename column integration_key to provider_slug;
    end if;
end $$;

alter table owner_integrations       add column if not exists provider_slug text not null default '';
alter table integration_credentials  add column if not exists provider_slug text not null default '';
alter table integration_credentials  add column if not exists field_name    text not null default '';
alter table integration_sync_logs    add column if not exists provider_slug text not null default '';
alter table agent_settings           add column if not exists agent_slug    text not null default '';

-- ── 9. Indexes ───────────────────────────────────────────────────────────────
create index if not exists idx_owner_integrations_owner_id on owner_integrations(owner_id);
create index if not exists idx_owner_integrations_slug on owner_integrations(provider_slug);
create index if not exists idx_integration_credentials_owner_id on integration_credentials(owner_id);
create index if not exists idx_integration_credentials_slug on integration_credentials(provider_slug);
create index if not exists idx_integration_sync_logs_owner_id on integration_sync_logs(owner_id);
create index if not exists idx_integration_sync_logs_slug on integration_sync_logs(provider_slug);
create index if not exists idx_agent_settings_owner_id on agent_settings(owner_id);
create index if not exists idx_agent_settings_slug on agent_settings(agent_slug);

-- ── 10. Seed Integration Providers ─────────────────────────────────────────
insert into integration_providers (slug, name, category, auth_type, description, docs_url, logo_emoji, required_fields, optional_fields)
values
    ('anthropic',     'Anthropic Claude',     'ai',          'api_key', 'Powers all Commander and agent reasoning', 'https://console.anthropic.com', '🤖', '["anthropic_api_key"]', '[]'),
    ('openai',        'OpenAI',               'ai',          'api_key', 'GPT-4o for health checks and DALL-E images', 'https://platform.openai.com', '🧠', '["openai_api_key"]', '[]'),
    ('groq',          'Groq',                 'ai',          'api_key', 'Ultra-fast free LLM for SMS composition', 'https://console.groq.com', '⚡', '["groq_api_key"]', '[]'),
    ('twilio',        'Twilio',               'messaging',   'api_key', 'SMS and voice for Rex and inbound leads', 'https://console.twilio.com', '📱', '["twilio_account_sid","twilio_auth_token","twilio_from_number"]', '[]'),
    ('bland_ai',      'Bland AI',             'messaging',   'api_key', 'AI voice calls for Rex outreach', 'https://app.bland.ai', '📞', '["bland_ai_api_key"]', '[]'),
    ('google_oauth',  'Google (Calendar/Gmail)', 'calendar', 'oauth2',  'Aria calendar events and email management', 'https://console.cloud.google.com', '📅', '["google_client_id","google_client_secret","google_redirect_uri"]', '["google_workspace_admin_email"]'),
    ('stripe',        'Stripe',               'payments',    'api_key', 'Subscription billing and checkout', 'https://dashboard.stripe.com', '💳', '["stripe_secret_key","stripe_publishable_key"]', '["stripe_webhook_secret"]'),
    ('resend',        'Resend',               'email',       'api_key', 'Transactional email for onboarding', 'https://resend.com', '✉️', '["resend_api_key"]', '[]'),
    ('alpha_vantage', 'Alpha Vantage',        'data',        'api_key', 'Market data for Orion trading agent', 'https://www.alphavantage.co', '📈', '["alpha_vantage_api_key"]', '[]'),
    ('n8n',           'n8n Workflows',        'automation',  'webhook', 'Low-code automation and workflow triggers', 'https://n8n.io', '🔄', '["n8n_base_url"]', '[]'),
    ('tradingview',   'TradingView',          'data',        'webhook', 'Strategy alert webhooks for Orion', 'https://www.tradingview.com', '📊', '["tradingview_webhook_secret"]', '[]'),
    ('sentry',        'Sentry',               'monitoring',  'api_key', 'Error tracking and performance monitoring', 'https://sentry.io', '🔍', '["sentry_dsn"]', '[]')
on conflict (slug) do nothing;

-- ── 11. RLS Policies (Enable for production) ────────────────────────────────
-- Uncomment these after verifying your auth flow works
-- alter table owners enable row level security;
-- alter table agents enable row level security;
-- alter table activity_log enable row level security;
-- alter table leads enable row level security;
-- alter table tasks enable row level security;
-- alter table agent_settings enable row level security;
-- alter table owner_integrations enable row level security;
-- alter table integration_credentials enable row level security;

-- create policy "owners_isolation" on owners for all using (id = auth.uid()::uuid);
-- create policy "agents_isolation" on agents for all using (owner_id = auth.uid()::uuid);
-- create policy "activity_log_isolation" on activity_log for all using (owner_id = auth.uid()::uuid);
-- create policy "leads_isolation" on leads for all using (owner_id = auth.uid()::uuid);
-- create policy "agent_settings_isolation" on agent_settings for all using (owner_id = auth.uid()::uuid);
-- create policy "owner_integrations_isolation" on owner_integrations for all using (owner_id = auth.uid()::uuid);
-- create policy "integration_credentials_isolation" on integration_credentials for all using (owner_id = auth.uid()::uuid);

select 'ORB v2 migration complete ✓' as status;
