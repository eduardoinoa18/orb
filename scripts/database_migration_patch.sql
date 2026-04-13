-- ORB schema patch: launch hardening + OTG/admin compatibility

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1) Ensure activity_log has metadata for modern agent logs
ALTER TABLE public.activity_log
ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;

ALTER TABLE public.activity_log
ADD COLUMN IF NOT EXISTS request_id text;

-- 2) Ensure onboarding integration tracking table exists
CREATE TABLE IF NOT EXISTS public.owner_integrations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  integration_key text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  connection_mode text NOT NULL DEFAULT 'skip',
  connected_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(owner_id, integration_key)
);

CREATE INDEX IF NOT EXISTS idx_owner_integrations_owner_id ON public.owner_integrations(owner_id);
CREATE INDEX IF NOT EXISTS idx_owner_integrations_key ON public.owner_integrations(integration_key);

-- 3) Super admin + role controls for owners
ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS role text DEFAULT 'user'
CHECK (role IN ('superadmin', 'admin', 'user', 'trial'));

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS is_superadmin boolean DEFAULT false;

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS monthly_cost_override_cents integer DEFAULT NULL;

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS name text;

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS spend_limit_cents integer DEFAULT 0;

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS plan text DEFAULT 'user';

ALTER TABLE public.owners
ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

UPDATE public.owners
SET
  role = COALESCE(NULLIF(role, ''), CASE WHEN is_superadmin THEN 'superadmin' ELSE 'user' END)
WHERE role IS NULL
   OR role = '';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'owners' AND column_name = 'full_name'
  ) THEN
    EXECUTE $sql$
      UPDATE public.owners
      SET name = COALESCE(NULLIF(name, ''), full_name)
      WHERE name IS NULL OR name = '';
    $sql$;
  END IF;
END
$$;

-- 4) Feature flag framework
CREATE TABLE IF NOT EXISTS public.feature_flags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  flag_name text UNIQUE NOT NULL,
  is_enabled boolean DEFAULT false,
  enabled_for_plans text[] DEFAULT '{}',
  description text,
  updated_by text,
  updated_at timestamptz DEFAULT now()
);

INSERT INTO public.feature_flags (flag_name, is_enabled, enabled_for_plans, description)
VALUES
  ('computer_use', false, '{full_team}', 'Allow agents to control browser'),
  ('whatsapp_commander', true, '{professional,full_team}', 'Commander accessible via WhatsApp'),
  ('custom_agent_builder', true, '{professional,full_team}', 'Users can create custom agents'),
  ('voice_input', true, '{starter,professional,full_team}', 'Voice input to Commander'),
  ('leaderboard', false, '{}', 'Public opt-in leaderboard')
ON CONFLICT (flag_name) DO UPDATE SET
  description = EXCLUDED.description,
  enabled_for_plans = EXCLUDED.enabled_for_plans,
  is_enabled = EXCLUDED.is_enabled,
  updated_at = now();

-- 5) Commander persistence (mobile + chat + owner config)
CREATE TABLE IF NOT EXISTS public.commander_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES public.owners(id) ON DELETE CASCADE UNIQUE,
  commander_name text DEFAULT 'Max',
  personality_style text DEFAULT 'professional',
  communication_style text DEFAULT 'concise',
  proactivity_level integer DEFAULT 7,
  morning_briefing_enabled boolean DEFAULT true,
  briefing_time text DEFAULT '07:00',
  weekly_review_enabled boolean DEFAULT true,
  review_day text DEFAULT 'sunday',
  language text DEFAULT 'en',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES public.owners(id) ON DELETE CASCADE,
  agent_role text NOT NULL,
  role text NOT NULL,
  message text NOT NULL,
  structured_payload jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.commander_mobile_prefs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES public.owners(id) ON DELETE CASCADE UNIQUE,
  alerts_enabled boolean NOT NULL DEFAULT true,
  approvals_enabled boolean NOT NULL DEFAULT true,
  quiet_hours_start text,
  quiet_hours_end text,
  updated_at timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commander_config_owner_id ON public.commander_config(owner_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_id ON public.chat_sessions(owner_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_created_at ON public.chat_sessions(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commander_mobile_prefs_owner_id ON public.commander_mobile_prefs(owner_id);

-- 6) Encrypted runtime settings store
CREATE TABLE IF NOT EXISTS public.platform_settings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,
  value text NOT NULL,
  description text DEFAULT '',
  category text DEFAULT 'general',
  owner_id text DEFAULT '',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_platform_settings_category ON public.platform_settings(category);

-- 7) Trading approval table used by SMS/WhatsApp YES/NO/STOP flow
CREATE TABLE IF NOT EXISTS public.trades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id uuid REFERENCES public.agents(id) ON DELETE CASCADE,
  instrument text NOT NULL,
  direction text NOT NULL,
  entry_price numeric(12, 4),
  exit_price numeric(12, 4),
  pnl_dollars numeric(12, 2),
  setup_name text,
  confidence_score integer,
  status text NOT NULL DEFAULT 'pending_approval',
  approved_by_human boolean NOT NULL DEFAULT false,
  stop_loss numeric(12, 4),
  take_profit numeric(12, 4),
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  closed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_trades_agent_id ON public.trades(agent_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON public.trades(status);

-- 8) Ensure feature flag defaults include email channel rollout toggle
INSERT INTO public.feature_flags (flag_name, is_enabled, enabled_for_plans, description)
VALUES
  ('email_commander', true, '{starter,professional,full_team}', 'Commander accessible via inbound email')
ON CONFLICT (flag_name) DO UPDATE SET
  description = EXCLUDED.description,
  enabled_for_plans = EXCLUDED.enabled_for_plans,
  is_enabled = EXCLUDED.is_enabled,
  updated_at = now();

-- 9) Billing governance controls (token caps + PAYG settings)
CREATE TABLE IF NOT EXISTS public.owner_billing_controls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  hourly_token_cap integer NOT NULL DEFAULT 25000,
  daily_token_cap integer NOT NULL DEFAULT 100000,
  weekly_token_cap integer NOT NULL DEFAULT 500000,
  monthly_token_cap integer NOT NULL DEFAULT 1000000,
  payg_enabled boolean NOT NULL DEFAULT true,
  auto_refill_enabled boolean NOT NULL DEFAULT false,
  auto_refill_threshold_tokens integer NOT NULL DEFAULT 0,
  auto_refill_amount_usd integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(owner_id)
);

CREATE INDEX IF NOT EXISTS idx_owner_billing_controls_owner_id
  ON public.owner_billing_controls(owner_id);

-- 10) Token usage ledger (model-level usage accounting)
CREATE TABLE IF NOT EXISTS public.token_usage_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  agent_slug text,
  model_name text,
  input_tokens integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  total_tokens integer NOT NULL DEFAULT 0,
  cost_cents integer NOT NULL DEFAULT 0,
  source text NOT NULL DEFAULT 'runtime',
  request_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_token_usage_ledger_owner_created
  ON public.token_usage_ledger(owner_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_token_usage_ledger_request_id_unique
  ON public.token_usage_ledger(request_id)
  WHERE request_id IS NOT NULL;

-- 11) Wallet balance + wallet ledger for PAYG top-ups
CREATE TABLE IF NOT EXISTS public.owner_wallets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL UNIQUE,
  balance_cents integer NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'usd',
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_owner_wallets_owner_id
  ON public.owner_wallets(owner_id);

CREATE TABLE IF NOT EXISTS public.wallet_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  wallet_id uuid REFERENCES public.owner_wallets(id) ON DELETE CASCADE,
  direction text NOT NULL CHECK (direction IN ('credit', 'debit')),
  amount_cents integer NOT NULL DEFAULT 0,
  reason text NOT NULL DEFAULT 'manual',
  stripe_reference text,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_owner_created
  ON public.wallet_transactions(owner_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_transactions_stripe_ref_unique
  ON public.wallet_transactions(stripe_reference)
  WHERE stripe_reference IS NOT NULL;
