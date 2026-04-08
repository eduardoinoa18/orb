# How ORB Works (Plain English)

This guide explains how ORB works, without the technical jargon.

## The Basic Idea

ORB has 5 AI assistants. Each one:
1. **Watches** for things it should do
2. **Thinks** about what action is needed  
3. **Asks you** to approve ("Is this okay?")
4. **Does it** only after you say yes

**You're always in control.** ORB never does anything without your permission.

## How Each Agent Works

### Aria — Your Morning Briefing

**What happens:**
1. Every morning at 7am, Aria reads your email and calendar
2. It figures out what's most important today
3. It sends you a text or email with a briefing
4. You read it and decide what to do

**Example:**
- "You have a meeting with Sarah at 2pm"
- "3 urgent emails came in"
- "Your dentist appointment is in 1 week"

**Key point:** Aria just informs you. You decide what to do.

### Nova — Content Creator

**What happens:**
1. You tell Nova what you want (e.g., "Write a listing for a house")
2. Nova creates a draft
3. You review it
4. If you approve, Nova posts it to social media automatically
5. If you reject, Nova learns and tries again next time

**Example:**
- You: "Generate a tweet about our new service"
- Nova: [writes draft]
- You: "Perfect! Post it" (or "Too casual, try again")

**Key point:** You always review before posting. Nothing goes public without permission.

### Orion — Trading Bot

**What happens:**
1. You give Orion a trading strategy (rules for buying/selling)
2. Orion **tests it with fake money** (paper trading)
3. It tells you "This strategy would make $500 profit on AAPL"
4. You decide if you want to try it with real money
5. Only when you approve does it trade with real money

**Example:**
- You: "Buy when price crosses above 50-day average"
- Orion: [tests on last 6 months of data]
- Orion: "This strategy would have made $1,200"
- You: "Looks good, run it with real money" (or "Not yet, test more")

**Key point:** Paper trading lets you test ideas safely. No real money is ever risked without permission.

### Rex — Sales Assistant

**What happens:**
1. A customer texts or emails asking about your product
2. Rex reads the message
3. Rex writes a response (or schedules a call)
4. Rex sends you the message for approval
5. You approve and it goes out

**Example:**
- Customer: "How much does your service cost?"
- Rex prepares: "Our service costs $X for Y features. Would you like a 15-min demo on Tuesday?"
- You: "Great! Send it" or "Change Z and send it"

**Key point:** Rex handles the repetitive stuff, but you approve every response.

### Sage — Business Analytics

**What happens:**
1. Sage watches your business 24/7 automatically
2. It checks: Are customers happy? Are sales going up? Any problems?
3. If something's wrong, Sage alerts you
4. Sage gives you weekly insights

**Example alerts:**
- "Customer complaints up 20% this week"
- "Best seller is Sarah - 8 sales this month"
- "Response time is slow on Tuesday afternoons"

**Key point:** Sage monitors automatically. You just read reports.

## The Approval Process

Every major action goes through 4 steps:

```
1. AI Thinks      → "I should send an email"
2. AI Proposes    → Shows you what it wants to do
3. You Approve    → You click "Yes" or "No"
4. AI Acts        → Only then does it actually happen
```

**This means:**
- Nothing happens without your permission
- You see exactly what ORB will do before it does it
- You can change your mind anytime
- You learn what ORB is doing (transparency)

## How ORB Learns

ORB gets smarter over time by:

1. **Understanding what you approve** — "Eduardo likes formal emails" or "Eduardo prefers short messages"
2. **Learning from your feedback** — If you reject something, ORB tries a different approach next time
3. **Remembering context** — ORB knows about past decisions ("Last time you rejected a message like this")

**You don't need to train it.** Just use it normally, approve/reject, and it learns.

## Data Safety & Privacy

### Your data is kept safe because:

1. **It stays in your database** — ORB stores data in YOUR Supabase account, not ORB's servers
2. **You own the keys** — Your API keys are in YOUR .env file, not shared with ORB
3. **No personal data shared** — ORB AI (Claude) never sees your name, email, or personal info. It just sees "Customer asked about pricing"
4. **Encryption by default** — Supabase encrypts everything automatically

### What ORB knows:
- ✅ What tasks you ask it to do
- ✅ Which actions you approved/rejected
- ❌ Your personal email contents  
- ❌ Your phone number
- ❌ Your private customer data

## How Much Does It Cost?

You only pay for what you actually use:

| Service | Cost | When You Pay |
|---------|------|------------|
| Claude AI | ~$0.02 per 1000 words | Every time an agent thinks |
| SMS (Twilio) | ~$0.01 per text | When Aria texts you or Rex texts a customer |
| Email | Free | ORB uses your own email account |
| Database (Supabase) | Free tier, then ~$25/month for unlimited | When you store lots of data |

**Example costs:**
- Using Aria for 1 month: ~$5-10
- Using Rex for 100 customer messages: ~$1
- Using Orion for testing 1 strategy: ~$0.50

**You control spending** with budgets and alerts. ORB stops working if you hit a budget limit.

## Getting Started

1. **Set up Aria first** (easiest, lowest cost)
2. **Use it for 1 week** to see how it works
3. **Add another agent** like Nova or Rex
4. **Gradually build up** to using all 5 agents

Don't activate everything at once. Start small.

## Common Concerns

### "Will ORB replace me?"
**No.** ORB handles repetitive tasks so you can focus on important decisions. You're still the boss.

### "What if ORB makes a mistake?"
**You're the safety net.** Every action needs approval first. If ORB suggests something wrong, you just click "No".

### "Can I shut it off?"
**Yes, instantly.** Go to Settings and toggle any agent off immediately.

### "How do I know what it's doing?"
**Everything is logged.** The dashboard shows a history of every action ORB proposed and every decision you made.

---

**Bottom line:** ORB is a helper, not a replacement. You stay in control. Try it, see what happens, adjust as needed.
