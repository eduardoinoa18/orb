# ORB Platform — Simple Setup & Use Guide

## What is ORB?

**ORB is an AI team that works 24/7 to help run your business.**

It's like having 5 smart assistants:
- 🗣️ **Aria** — Reads emails and reminds you what's important
- 📱 **Nova** — Writes social media posts and listings
- 📈 **Orion** — Tests trading strategies and watches the market
- 💬 **Rex** — Handles customer messages and schedules calls
- 👁️ **Sage** — Watches your business for problems and opportunities

**You stay in control.** Every action needs your approval first.

## Getting Started (5 Minutes)

### Step 1: Download & Install

```powershell
# Clone or download the code
cd orb-platform

# Create a virtual environment (like a sandbox for Python)
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Add Your Settings

Create a `.env` file in the `orb-platform` folder with:

```
# Your phone number (for SMS alerts)
MY_PHONE_NUMBER=+1978390xxxx

# Your email (so Aria can read your calendar)
MY_EMAIL=your.email@gmail.com

# Get these from https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-xxx

# Get these from https://www.twilio.com/console
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_PHONE_NUMBER=+1978390xxxx

# Get these from https://supabase.com/dashboard
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyxxx

# Optional: Get from https://platform.openai.com/account/api-keys
OPENAI_API_KEY=sk-xxx
```

**Don't have all of these?** That's OK. Start with just:
- `MY_PHONE_NUMBER`
- `MY_EMAIL`
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`

### Step 3: Start ORB

```powershell
.\scripts\start_api.ps1 -PreferredPort 8000 -BindHost 127.0.0.1 -Reload
```

Then open **http://localhost:8000** in your browser.

Health checks:

- `GET /health` uses standard mode (fast, low-cost, config-aware checks).
- `GET /health?deep=true` runs live dependency probes including external AI API calls.

### Optional: Verify Database Schema Readiness

```powershell
.\.venv\Scripts\python.exe .\scripts\setup_database.py --strict
```

If any checks fail, run the SQL in [scripts/database_migration_patch.sql](scripts/database_migration_patch.sql)
inside your Supabase SQL editor, then rerun the command above.

### Optional: Run Full Platform Preflight

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/setup/preflight"
```

This returns a readiness score with blockers and warnings (schema + key quality).

To view the platform core-values scorecard (simplicity, reliability, owner control, learning velocity):

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/setup/core-values"
```

Use this to track whether the platform is getting simpler and better over time.

You can also run preflight directly from CLI (works before API startup):

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_check.py --strict
```

To enforce schema preflight during startup (hard stop on failure):

```powershell
.\scripts\start_api.ps1 -PreferredPort 8000 -BindHost 127.0.0.1 -Reload -EnforcePreflight
```

For daily startup script, set environment variable first:

```powershell
$env:ORB_ENFORCE_PREFLIGHT="1"
.\scripts\daily_startup.bat
```

### Step 4: Set Up Your First Agent

1. Click **"Go to Aria"** on the home page
2. Click **"Send Briefing Now"** to test it
3. That's it! Aria is now active.

## What Each Agent Does (Simple Explanation)

| Agent | What It Does | How Long to Set Up |
|-------|-------------|-------------------|
| **Aria** | Sends you a morning briefing about your calendar and tasks | 2 minutes |
| **Nova** | Writes social media posts for you to approve | 5 minutes |
| **Orion** | Tests trading strategies with fake money | 10 minutes |
| **Rex** | Answers customer messages and schedules calls | 5 minutes |
| **Sage** | Watches your business for problems (automatic) | 0 minutes |

## Common Questions

### Q: Do I need all the settings before I start?
**No.** Start with just Aria (needs email and phone). Add more later.

### Q: Will this cost me money?
**Only what you use:**
- Claude AI: ~$0-10/day depending on how much you use it
- Twilio SMS: ~$0.01 per message
- Supabase: Free tier included

### Q: What if ORB does something wrong?
**You approve everything first.** No emails sent, no trades made, nothing posted until you click "Yes".

### Q: Can I turn off an agent?
**Yes.** Go to Settings and toggle agents on/off anytime.

### Q: Is my data private?
**Yes.** Your data stays in your own Supabase database. OBR never has access to your personal information.

## Next Steps

1. **Read the full guides:**
   - [GETTING_STARTED.md](GETTING_STARTED.md) — plain English step-by-step guide
   - [HOW_IT_WORKS.md](HOW_IT_WORKS.md) — how the AI actually works
   - [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — fixing common problems

2. **Join the community:**
   - Start with Aria (simplest)
   - Use it for 1 week
   - Then add Nova or Rex based on what you need

3. **Get help:**
   - Check the dashboard for helpful tooltips
   - Read the full guides above
   - Ask questions (the platform explains everything)

## File Structure (Don't Worry About This Yet)

```
orb-platform/
├── agents/              ← AI logic for each agent type
├── app/                 ← Web interface and API
├── integrations/        ← connections to Twilio, Claude, etc.
├── config/              ← settings and strategies
├── tests/               ← automated tests
├── .env                 ← YOUR settings go here
└── requirements.txt     ← Python packages needed
```

```powershell
cd .\orb-platform
uvicorn app.api.main:app --reload
```

### 5. Test the health endpoint

Open this in your browser:

```text
http://localhost:8000/health
```

Expected response:

```json
{"status": "healthy", "platform": "ORB", "version": "0.1.0"}
```

## Need Help Setting Up?

1. **Follow the detailed guide:** [GETTING_STARTED.md](GETTING_STARTED.md)
2. **Check troubleshooting:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
3. **Understand how it works:** [HOW_IT_WORKS.md](HOW_IT_WORKS.md)

---

**Remember: Start simple. Get one agent working. Then add more complexity when you're comfortable.**

Good luck! 🚀
COMPUTER_USE_ENABLED=false
COMPUTER_USE_SCREENSHOT_DIR=artifacts/screenshots
TRADINGVIEW_WEBHOOK_SECRET=
```

Plain-English explanation:

- `RAILWAY_API_TOKEN`: lets Sage inspect Railway status later.
- `RAILWAY_PROJECT_ID`: tells Sage which Railway project to monitor.
- `TOKEN_CACHE_TTL_MINUTES`: how long token optimizer cache entries stay reusable.
- `COMPUTER_USE_ENABLED`: master on/off switch for browser-control features.
- `COMPUTER_USE_SCREENSHOT_DIR`: where before/after computer-use screenshots are stored.
- `TRADINGVIEW_WEBHOOK_SECRET`: older trading webhook code still uses this to validate alerts.

### Addendum test commands

Run these from PowerShell inside `orb-platform`.

1. Addendum-only tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -k addendum -q
```

What this does: runs only the new addendum tests so you can confirm the new work in isolation.

2. Full regression tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

What this does: re-checks the entire project to make sure the new addendum code did not break previous levels.

### Token optimizer behavior

The optimizer now does four practical things before an AI call is made:

- Reuses a recent cached answer when the same task was already solved inside `TOKEN_CACHE_TTL_MINUTES`
- Skips obvious non-AI tasks
- Tracks daily per-agent AI spend against the addendum budget caps
- Switches agents into `minimal` mode near the budget limit and `deferred` mode after the limit is exhausted for non-critical work

The optimizer route accepts two optional fields now:

- `agent_id`: lets the route apply that agent's daily budget
- `is_critical`: keeps urgent work from being deferred when a budget cap is hit

### Starter endpoints added

- `GET /agents/optimizer/status`
- `POST /agents/optimizer/optimize`
- `GET /agents/optimizer/efficiency`
- `GET /agents/rex/status`
- `POST /agents/rex/learn-owner`
- `POST /agents/rex/learn-outcomes`
- `POST /agents/orion/learn-outcomes`
- `POST /agents/nova/learn-outcomes`
- `POST /agents/nova/owner-needs`
- `GET /agents/sage/status`
- `POST /agents/sage/platform-monitor`
- `POST /agents/sage/learn-outcomes`
- `POST /aria/learn-outcomes`
- `POST /aria/learn-owner-style`
- `GET /agents/computer-use/status`
- `POST /agents/computer-use/safety-check`
- `GET /dashboard/integrations`
- `POST /dashboard/integrations/live-check`
- `GET /dashboard/command-center`
- `GET /dashboard/setup-checklist`

### UI-first integration operations

The `/dashboard` shell now includes an **Integration Control Center** panel so you can:

- See integration readiness with masked credential previews
- Run live checks for Supabase, Anthropic, OpenAI, and Twilio
- View UI control values such as `COMPUTER_USE_ENABLED` and token cache TTL

It also includes an **Operations Index** and now uses a consolidated payload from
`/dashboard/command-center` to keep the command center organized and fast.

The dashboard now includes a **Setup Wizard** panel that reads from
`/dashboard/setup-checklist` and stores local completion progress in the browser.

The dashboard shell also now supports:

- **Owner Mode** for daily workflows and high-signal summaries
- **Operator Mode** for setup, integrations, provisioning, and platform controls
- Browser-persistent UI preferences for section collapse state and commonly reused non-secret form values

### First confirmation test before the next addendum

Use this simple proof-of-concept test first:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/agents/optimizer/optimize" -ContentType "application/json" -Body '{"prompt":"Write a short sms reminder for a demo tomorrow at 2pm.","task_type":"sms_compose","max_budget_cents":3,"agent_id":"rex"}'
```

What this does: asks the token optimizer to choose the cheapest safe model and token cap for a short SMS task while also checking Rex's daily budget state. If this returns JSON successfully, look for `selected_model`, `max_tokens`, `budget_mode`, and `remaining_budget_cents` in the response.
