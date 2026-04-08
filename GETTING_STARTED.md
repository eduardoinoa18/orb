# ORB Platform — Getting Started (Simple Guide)

Welcome! This guide explains ORB in plain English, so anyone can use it.

## What is ORB?

ORB is an **AI Team** that helps you run your business. Think of it like having smart assistants that work 24/7.

## Your AI Team Members

### 🗣️ **Aria** — Your Daily Assistant
- Reads your calendar and emails every morning
- Sends you a briefing with what's important today
- Reminds you about tasks and meetings
- Keeps you organized without overwhelming you

**How to use:** Set up in Settings → Add your email and phone

### 📱 **Nova** — Content Creator
- Writes social media posts for you
- Creates listings for properties you sell
- Generates marketing content automatically
- You review and approve before posting

**How to use:** Go to Nova section → Click "Generate Weekly Content" → Review and approve

### 📈 **Orion** — Trading Bot
- Watches the stock market for opportunities
- Tests trading strategies safely (paper trading)
- Alerts you when it finds good trades
- Completely safe — no real money is risked until you approve

**How to use:** Go to Orion → Add your trading strategy → Let it watch the market

### 💬 **Rex** — Sales Assistant
- Qualifies leads from your sales funnel
- Responds to customer inquiries automatically
- Schedules meetings with prospects
- Handles the boring sales work so you don't have to

**How to use:** Connect your phone number → Let it handle inbound messages

### 👁️ **Sage** — Business Intelligence
- Tracks what your competitors are doing
- Analyzes your customer success metrics
- Flags problems before they become big issues
- Gives you weekly insights about your business

**How to use:** Automatic — it works in the background daily

## Simple Setup Steps

1. **Go to http://localhost:8000**

2. **Click "Setup Wizard"** on the dashboard

3. **Follow the checklist:**
   - ✅ Add your phone number (for alerts and SMS)
   - ✅ Add your email (so Aria can read your calendar)
   - ✅ Add API keys (copy-paste from your accounts)

4. **Start with one agent** — Try Aria first since it's the simplest

5. **Let it run for a few days** and see what happens

## What Each Settings Item Means

| Setting | What It Does | Example |
|---------|-------------|---------|
| `ANTHROPIC_API_KEY` | Lets Claude think and plan on your behalf | From console.anthropic.com |
| `MY_PHONE_NUMBER` | Where to send alerts and reminders | +1-978-390-9619 |
| `MY_EMAIL` | Where Aria reads your calendar from | your.email@gmail.com |
| `SUPABASE_URL` | Database to store activity logs | https://xxx.supabase.co |
| `SUPABASE_SERVICE_KEY` | Permission to read/write to database | Long secret key from Supabase |
| `TWILIO_ACCOUNT_SID` | Lets Rex send and receive text messages | From Twilio console |
| `TWILIO_AUTH_TOKEN` | Permission to use Twilio | Long secret from Twilio |

## Common Questions

### Q: Is my data safe?
**A:** Yes. Your data stays in your own Supabase database or Twilio account. ORB never stores or sees your personal information.

### Q: Does it cost money?
**A:** Only if you use external services:
- **Claude AI**: ~$1-10/day depending on usage
- **Twilio SMS**: ~$0.01 per text message
- **Supabase database**: Free tier included

### Q: What if I don't like what an agent does?
**A:** Every major action requires your approval first. No trades happen, no messages sent, nothing posted until you click "Yes".

### Q: Can I turn off an agent?
**A:** Yes. In Settings → Agent Controls → Choose which agents are active.

### Q: What does "paper trading" mean?
**A:** Orion tests trades with fake money to see if strategies work. **No real money is lost.** You only trade with real money if you explicitly enable it and approve the trade.

### Q: How do I add agents to my team?
**A:** They're already there! Go to the Dashboard and you'll see each agent's controls. Just activate the ones you want.

## Your First 5 Minutes

1. Open http://localhost:8000
2. Click "Setup Wizard"
3. Add your phone number
4. Go to "Aria" section
5. Click "Send Briefing Now" (optional)

That's it! Aria is now active and will help you tomorrow morning.

## Getting Help

- **Something confusing?** Check this guide again or ask on the dashboard
- **Need technical help?** See [TECHNICAL_SETUP.md](TECHNICAL_SETUP.md)
- **Want to understand the AI?** See [HOW_IT_WORKS.md](HOW_IT_WORKS.md)

## Next Steps

- Set up Aria (easiest)
- Then add Rex if you get sales calls
- Then Orion if you trade stocks
- Nova if you post content
- Sage tracks things automatically

Start simple. Add complexity only when you're comfortable.

---

**Remember:** ORB is here to save you time and help you make better decisions. You're always in control. Enjoy! 🚀
