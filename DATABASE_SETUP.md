# Database Setup Instructions

## You Only Need to Do This ONCE

Your ORB platform needs a Supabase database. Here's how to set it up in 2 minutes:

---

## STEP 1: Create a Supabase Account (if you don't have one)

1. Go to https://supabase.com
2. Click "Sign Up"
3. Use your email or GitHub account
4. Create a password
5. You'll see "Create a new project" button

---

## STEP 2: Create Your First Project

1. Click "New Project"
2. Give it a name: `ORB` (or whatever you want)
3. Create a strong password (save it somewhere safe, you'll see it only once)
4. Choose a region close to you
5. Click "Create new project"
6. Wait 2-3 minutes for it to initialize

---

## STEP 3: Run the Database Setup SQL

1. In your Supabase dashboard, click **SQL Editor** in the left sidebar
2. Click **New Query** (top-left button)
3. You'll see a blank text area
4. Open the file `database/schema.sql` from your ORB folder
5. Copy the ENTIRE content
6. Paste it into the Supabase SQL Editor text area
7. Click the blue **Run** button (or press Ctrl+Enter)
8. You should see green checkmarks and "Executed successfully"

That's it! Your database is now ready.

---

## STEP 4: Get Your Supabase Connection Info

You need 3 pieces of information that ORB will use:

1. In Supabase dashboard, click **Settings** (bottom-left gear icon)
2. Click **API** in the left menu
3. You'll see two values:
   - **Project URL** — Looks like: `https://xxxxx.supabase.co`
   - **anon public key** — A long random string

4. Also need your **Database Password** — You created this in Step 2 (check your password manager)

---

## STEP 5: Add Connection Info to ORB

1. In your ORB folder, open `.env` file (it's a hidden file)
2. Find these lines:
   ```
   SUPABASE_URL=
   SUPABASE_KEY=
   SUPABASE_PASSWORD=
   ```

3. Fill them in:
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_KEY=your-long-anon-key-here
   SUPABASE_PASSWORD=your-database-password-from-step-2
   ```

4. Save the file
5. Now ORB can connect to your database

---

## ✅ DONE!

Your database is ready. All 10 tables are created:
- ✓ owners (you and your team)
- ✓ agents (Rex, Aria, Nova, Orion, Sage)
- ✓ leads (prospects for Rex)
- ✓ activity_log (everything ORB does)
- ✓ paper_trades (Orion's practice trades)
- ✓ strategies (Orion's trading rules)
- ✓ tasks (Aria reminders)
- ✓ content (Nova drafts)
- ✓ sequences (N8N follow-ups)
- ✓ daily_costs (cost tracking)

---

## Troubleshooting

**"Error: syntax error at line 42"**
- Make sure you copied the ENTIRE schema.sql file
- Look for any partial copy/paste
- Try Step 3 again with a fresh copy

**"Permission denied on table creation"**
- Make sure you're using the Supabase SQL Editor, not a different tool
- Database creation requires admin permissions (which SQL Editor has)

**"Connection refused"**
- Check your SUPABASE_URL has no typos
- Make sure .env file was saved
- Restart ORB after updating .env

**"No tables found"**
- Go back to Supabase SQL Editor
- In left menu, click **Database** → **Tables**
- You should see all 10 tables listed
- If not, the SQL didn't run. Try Step 3 again.

---

## Next: Email Integration

After database setup, you'll need to:
1. Connect Gmail for Aria (email reading, calendar)
2. Connect Twilio for Rex (SMS sending)
3. Connect Claude API key for all agents

These will be in the main ORB setup guide.
