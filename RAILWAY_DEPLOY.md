# ORB Platform — Railway Deployment Guide

## What You Need Before You Start

| Requirement | Where to get it | Time |
|---|---|---|
| Railway account | railway.app | 2 min |
| Supabase project | supabase.com | 5 min |
| Anthropic API key | console.anthropic.com | 2 min |
| GitHub repo connected | already have it | — |

---

## Step 1 — Supabase Database Setup

1. Go to **supabase.com** → your project → **SQL Editor**
2. Click **New Query**
3. Paste the entire contents of `scripts/railway_migration_v2.sql`
4. Click **Run** — you should see: `ORB v2 migration complete ✓`

**Get your Supabase credentials** (Project Settings → API):
- `SUPABASE_URL` → Project URL
- `SUPABASE_SERVICE_KEY` → service_role key (secret)
- `SUPABASE_ANON_KEY` → anon / public key

---

## Step 2 — Deploy to Railway

### Option A: Deploy from GitHub (Recommended)

1. Go to **railway.app** → **New Project** → **Deploy from GitHub repo**
2. Select your `eduardoinoa18/orb` repo
3. Set the **Root Directory** to: `orb-platform`
4. Railway will detect the `Dockerfile` automatically

### Option B: Railway CLI

```bash
npm install -g @railway/cli
railway login
cd orb-platform
railway init
railway up
```

---

## Step 3 — Set Environment Variables in Railway

Go to your service → **Variables** → Add these one by one:

### REQUIRED (app will not start without these)

```
PLATFORM_NAME=ORB
PLATFORM_DOMAIN=yourapp.up.railway.app
JWT_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
ENVIRONMENT=production
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...
MY_EMAIL=you@yourdomain.com
MY_PHONE_NUMBER=+1XXXXXXXXXX
MY_BUSINESS_ADDRESS=Your address here
```

### RECOMMENDED (add now for core features)

```
ANTHROPIC_API_KEY=sk-ant-...
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```

### OPTIONAL (add later via Integration Hub UI)

Everything else — Stripe, Google OAuth, Bland AI, market data, etc.
These can all be configured post-deploy from the dashboard.

---

## Step 4 — Verify Deployment

Once deployed, check these URLs:

| URL | Expected Response |
|---|---|
| `https://yourapp.up.railway.app/health` | `{"status": "healthy", ...}` |
| `https://yourapp.up.railway.app/api` | `{"message": "Welcome to ORB"}` |
| `https://yourapp.up.railway.app/docs` | Swagger UI |
| `https://yourapp.up.railway.app/setup/preflight` | Preflight checklist JSON |

If health returns `"status": "degraded"`, check which dependency failed:
- `supabase: unhealthy` → Check SUPABASE_URL and SUPABASE_SERVICE_KEY
- `anthropic: unhealthy` → Add ANTHROPIC_API_KEY in Variables

---

## Step 5 — Deploy the Frontend (orb-landing)

The dashboard UI (`orb-landing`) is a separate Next.js app. Deploy it to:
- **Vercel** (easiest): Connect GitHub → select `orb-landing` folder → deploy
- **Railway**: Add another service, set root to `orb-landing`

Set these environment variables in your frontend deployment:
```
NEXT_PUBLIC_ORB_API_URL=https://yourapp.up.railway.app
NEXT_PUBLIC_STRIPE_PK=pk_live_...  (optional)
```

---

## Step 6 — First Login

1. Go to `https://your-frontend.vercel.app/register`
2. Complete the 6-step onboarding wizard
3. Go to `/dashboard` — you're in!
4. Go to `/dashboard/integrations` to connect Anthropic, Twilio, etc. from the UI

---

## Troubleshooting

### "Missing required environment variables"
→ Add `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY` in Railway Variables

### "relation owners does not exist"
→ You haven't run the SQL migration. Go to Supabase → SQL Editor → run `railway_migration_v2.sql`

### App starts but agents don't respond
→ Add `ANTHROPIC_API_KEY` in Railway Variables (or via Integration Hub)

### Twilio SMS not sending
→ Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` in Variables

### CORS errors from frontend
→ Make sure `PLATFORM_DOMAIN` matches your frontend's domain (without https://)

### Login returns 503
→ Database is unreachable — check Supabase connection strings

---

## Railway Custom Domain

1. Railway → your service → **Settings** → **Domains**
2. Add your custom domain
3. Update `PLATFORM_DOMAIN` variable to your custom domain
4. Update `GOOGLE_REDIRECT_URI` if using Google OAuth

---

## Cost Estimates

| Service | Free tier | Paid |
|---|---|---|
| Railway | $5/mo hobby | ~$5-20/mo for this app |
| Supabase | Free (500MB) | $25/mo for Pro |
| Anthropic | Pay per use | ~$5-30/mo typical use |
| Twilio | $1 credit trial | ~$0.0075/SMS |

**Estimated monthly cost for personal beta: ~$10-30/mo**
