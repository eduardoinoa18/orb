-- ORB Integration Hub Schema
-- Run this inside Supabase SQL Editor to add integration management tables.

create table if not exists integration_providers (
    id uuid primary key default gen_random_uuid(),
    slug text unique not null,
    name text not null,
    category text not null,
    auth_type text not null,
    description text,
    docs_url text,
    logo_emoji text,
    required_fields jsonb default '[]'::jsonb,
    optional_fields jsonb default '[]'::jsonb,
    is_active boolean default true,
    created_at timestamptz default now()
);

create index if not exists idx_integration_providers_slug on integration_providers(slug);
create index if not exists idx_integration_providers_category on integration_providers(category);
create index if not exists idx_integration_providers_is_active on integration_providers(is_active);

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

create index if not exists idx_owner_integrations_owner_id on owner_integrations(owner_id);
create index if not exists idx_owner_integrations_provider_slug on owner_integrations(provider_slug);
create index if not exists idx_owner_integrations_status on owner_integrations(status);

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

create index if not exists idx_integration_credentials_owner_id on integration_credentials(owner_id);
create index if not exists idx_integration_credentials_provider_slug on integration_credentials(provider_slug);

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

create index if not exists idx_integration_sync_logs_owner_id on integration_sync_logs(owner_id);
create index if not exists idx_integration_sync_logs_provider_slug on integration_sync_logs(provider_slug);
create index if not exists idx_integration_sync_logs_created_at on integration_sync_logs(created_at);

create table if not exists agent_settings (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references owners(id) on delete cascade,
    agent_slug text not null,
    daily_budget_cents integer default 500,
    is_enabled boolean default true,
    autonomy_level integer default 5,
    channels jsonb default '[]'::jsonb,
    permissions jsonb default '{}'::jsonb,
    schedule_config jsonb default '{}'::jsonb,
    memory_context jsonb default '{}'::jsonb,
    kill_switch boolean default false,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(owner_id, agent_slug)
);

create index if not exists idx_agent_settings_owner_id on agent_settings(owner_id);
create index if not exists idx_agent_settings_agent_slug on agent_settings(agent_slug);
create index if not exists idx_agent_settings_is_enabled on agent_settings(is_enabled);

-- Seed integration_providers with all required providers
insert into integration_providers (slug, name, category, auth_type, description, logo_emoji, required_fields, optional_fields)
values
    ('twilio', 'Twilio', 'messaging', 'api_key', 'SMS and voice calls', '📱', '["account_sid", "auth_token"]'::jsonb, '["from_number"]'::jsonb),
    ('anthropic', 'Anthropic', 'ai', 'api_key', 'Claude AI API', '🤖', '["api_key"]'::jsonb, '[]'::jsonb),
    ('openai', 'OpenAI', 'ai', 'api_key', 'GPT models API', '🧠', '["api_key"]'::jsonb, '[]'::jsonb),
    ('google_oauth', 'Google OAuth', 'auth', 'oauth2', 'Google account integration', '🔐', '["client_id", "client_secret"]'::jsonb, '[]'::jsonb),
    ('bland_ai', 'Bland AI', 'messaging', 'api_key', 'Voice agent platform', '☎️', '["api_key"]'::jsonb, '[]'::jsonb),
    ('stripe', 'Stripe', 'payments', 'api_key', 'Payment processing', '💳', '["secret_key"]'::jsonb, '["publishable_key"]'::jsonb),
    ('resend', 'Resend', 'messaging', 'api_key', 'Email API', '📧', '["api_key"]'::jsonb, '[]'::jsonb),
    ('alpha_vantage', 'Alpha Vantage', 'data', 'api_key', 'Stock market data', '📈', '["api_key"]'::jsonb, '[]'::jsonb),
    ('n8n', 'n8n', 'automation', 'webhook', 'Workflow automation', '⚙️', '[]'::jsonb, '["webhook_url"]'::jsonb),
    ('tradingview', 'TradingView', 'data', 'webhook', 'Trading signals', '📊', '[]'::jsonb, '["webhook_secret"]'::jsonb),
    ('whatsapp', 'WhatsApp', 'messaging', 'api_key', 'WhatsApp messaging', '💬', '["phone_number_id", "access_token"]'::jsonb, '[]'::jsonb)
on conflict (slug) do nothing;
