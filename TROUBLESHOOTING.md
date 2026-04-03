# Troubleshooting — Fixing Common Problems

If something isn't working, you're probably in one of the situations below. Pick yours and follow the fix.

## "I started ORB but nothing is happening"

**What's probably wrong:** ORB isn't turned on or isn't configured yet.

**How to fix:**
1. Go to http://localhost:8000
2. Look for a "Settings" button
3. Make sure your phone number and email are filled in
4. Look for each agent (Aria, Nova, Orion, Rex, Sage)
5. Make sure at least one is toggled "ON"

If still nothing happens:
- Check that `MY_PHONE_NUMBER` and `MY_EMAIL` are in your `.env` file
- Restart ORB (stop and start the server again)

---

## "ORB says 'Unhealthy' on the health page"

**What's probably wrong:** One of the services (Claude, Supabase, or Twilio) isn't connected properly.

**How to fix:**

### If it says "Supabase — Unhealthy":
1. Go to your `.env` file
2. Check that `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are filled in
3. Make sure they're not empty or have extra spaces
4. Restart ORB

### If it says "Anthropic — Unhealthy":
1. Get your API key from https://console.anthropic.com/account/keys
2. Put it in `.env` as `ANTHROPIC_API_KEY=sk-ant-xxx`
3. Restart ORB

### If it says "OpenAI — Unhealthy":
1. This is optional. You can ignore it if you don't use OpenAI
2. Or get a key from https://platform.openai.com/account/api-keys
3. Add `OPENAI_API_KEY=sk-xxx` to `.env`
4. Restart ORB

---

## "Aria isn't sending me a briefing"

**What's probably wrong:** Aria doesn't have your email or phone number.

**How to fix:**
1. Check your `.env` file has:
   - `MY_EMAIL=your.real.email@gmail.com`
   - `MY_PHONE_NUMBER=+1978390xxxx` (include the + and country code)
2. Restart ORB
3. Click "Send Briefing Now" to test immediately

**If still not working:**
- Make sure your email account allows ORB to read it
- For Gmail: You may need to create an "app password" https://support.google.com/accounts/answer/185833
- Check your spam folder

---

## "Rex isn't responding to customer messages"

**What's probably wrong:** Twilio isn't set up or Rex isn't turned on.

**How to fix:**
1. Create a free Twilio account at https://www.twilio.com
2. Get your `ACCOUNT_SID`, `AUTH_TOKEN`, and `PHONE_NUMBER`
3. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxx
   TWILIO_AUTH_TOKEN=xxx
   TWILIO_PHONE_NUMBER=+1978390xxxx
   ```
4. Restart ORB
5. Go to Rex section and click "Provision Agent" with your phone number

**Quick test:**
- Send a text to your Twilio number
- Check that Rex gets it
- Check the dashboard log to see what Rex replied

---

## "Orion says 'Paper Trading Failed'"

**What's probably wrong:** Market data isn't loading or your strategy has an error.

**How to fix:**
1. Make sure your strategy is written correctly
2. Try with a simple strategy first: `Buy when price > 100`
3. Check that you have `ANTHROPIC_API_KEY` set (Claude reads your strategy)
4. Try the test again

**If still failing:**
- Check the error message carefully
- Copy the exact error and search Google for it
- Ask on the dashboard for help

---

## "I'm getting charged a lot and I don't know why"

**What's probably wrong:** An agent is running too much and burning through API credits.

**How to fix:**

1. **Turn off expensive agents:**
   - Orion costs more because it tests trading
   - Nova costs more because it generates content
   - Aria costs the least
   
2. **Set a spending limit:**
   - Go to Settings
   - Set `DAILY_BUDGET_CENTS` to how much you want to spend per day
   - ORB will stop working if you hit the limit

3. **Check which agent is costing the most:**
   - Go to Dashboard
   - Look at "Cost by Agent"
   - Turn off the expensive ones

4. **Use cheap models:**
   - Set `PREFERRED_MODEL=haiku` in settings (cheapest)
   - Use `sonnet` for normal work
   - Use `opus` only for hard thinking (expensive)

---

## "The dashboard is confusing"

**What's probably wrong:** You're looking at too much at once.

**How to fix:**
1. Close the dashboard
2. Go to http://localhost:8000 (the home page)
3. Click on ONE agent
4. Do one thing with that agent
5. Check how it went
6. Move to the next agent

**Pro tip:** Start with Aria. It's the simplest. Get comfortable with one agent before trying others.

---

## "ORB is doing something I don't want"

**What's probably wrong:** An agent's setting is wrong.

**How to fix:**
1. Turn the agent off immediately: Settings → Toggle OFF
2. Go to that agent's section
3. Change the settings
4. Turn it back on

**You're in control.** Nothing happens without your permission. If you don't like what an agent suggests, just reject it (click "No").

---

## "I don't understand what's happening"

**What's probably wrong:** You need more explanation.

**How to fix:**
1. Read [HOW_IT_WORKS.md](HOW_IT_WORKS.md) — explains how ORB works
2. Read [GETTING_STARTED.md](GETTING_STARTED.md) — simple step-by-step guide
3. Check the dashboard tooltips (hover over question marks)
4. Try one agent at a time, don't try everything at once

---

## "ORB crashed or isn't responding"

**What's probably wrong:** The server stopped.

**How to fix:**
1. Open PowerShell
2. Stop the old server: `Ctrl+C`
3. Check for errors in the output
4. Restart it: `python -m uvicorn app.api.main:app --reload`
5. Go to http://localhost:8000 again

**If it keeps crashing:**
1. Check if all your settings in `.env` are correct
2. Make sure `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set
3. Try again

---

## "I'm getting errors with error codes like 401, 404, 500"

| Error Code | What It Means | How to Fix |
|-----------|--------------|-----------|
| **401** | Authentication failed (API key wrong) | Check your API keys in `.env` |
| **404** | Page not found | Wrong URL - try http://localhost:8000 |
| **500** | ORB crashed | Restart the server |
| **503** | Database not available | Check `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` |

---

## Still stuck?

**Try this checklist:**
1. ✅ Is the server running? (Is http://localhost:8000 open?)
2. ✅ Is the agent turned ON in Settings?
3. ✅ Are all required settings in `.env` filled in?
4. ✅ Did you restart ORB after changing `.env`?
5. ✅ Did you read the error message? (it usually says what's wrong)

**When all else fails:**
- Restart your computer
- Delete the database and start fresh
- Start with just Aria (simplest)
- Add complexity one step at a time

---

**Remember:** ORB is designed to be simple. If something is confusing, that's a bug in the design, not a bug in you. Let us know what's confusing!
