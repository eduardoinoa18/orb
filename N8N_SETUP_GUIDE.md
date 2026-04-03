# N8N Workflow Setup Guide for ORB

## What is N8N?

N8N is an automation tool that runs scheduled follow-ups. ORB uses N8N to:
- Send follow-up sequences to cold leads
- Schedule reminder emails
- Automate daily reports
- Execute pre-built workflows

---

## STEP 1: Create N8N Account

1. Go to https://n8n.cloud
2. Click "Get started free"
3. Sign up with your email
4. Create a local account or use OAuth
5. You'll land on the dashboard

---

## STEP 2: Connect N8N to ORB

N8N needs to know where to send webhooks when workflows complete.

1. In N8N, click **Settings** (bottom-left padlock icon)
2. Click **Environment variables**
3. Add these variables:
   - `ORB_WEBHOOK_URL` = `http://localhost:8000/webhooks/n8n/sequence_complete` (during testing) or your production URL
   - `ORB_API_KEY` = (blank for now, we'll add token auth later)

4. Click Save

---

## STEP 3: Create Your First Workflow - "30 Day Lead Nurture"

This workflow will send 3 follow-up emails over 30 days to cold leads.

### Creating the Workflow

1. In N8N dashboard, click **New** → **Workflow**
2. Name it: `30_day_lead_nurture`

### Step 1: Webhook Trigger (When ORB starts the sequence)

1. Right-click canvas → **Add Node**
2. Search for "Webhook"
3. Select "Webhook"
4. In the panel on right:
   - HTTP Method: **POST**
   - Path: **lead_nurture_start**
   - Authentication: None
5. Copy the webhook URL (you'll need it in Step 7)

### Step 2: Extract Lead Data

1. Right-click canvas → **Add Node**
2. Search for "Set"
3. Select "Set (Set data)**
4. In the panel:
   - Add fields:
     - `lead_phone` = `{{ $json.body.phone }}`
     - `lead_email` = `{{ $json.body.email }}`
     - `lead_name` = `{{ $json.body.name }}`
     - `owner_phone` = `{{ $json.body.owner_phone }}`

### Step 3: Wait 3 Days

1. Right-click canvas → **Add Node**
2. Search for "Wait"
3. Select "Wait"
4. In the panel:
   - Wait time: **3**
   - Time unit: **Days**

### Step 4: Send First Email

1. Right-click canvas → **Add Node**
2. Search for "Gmail"
3. Select "Gmail"
4. Click **Connect** and authenticate with your Gmail account
5. In the panel:
   - Method: **Send Email**
   - Email: `{{ $json.lead_email }}`
   - Subject: `Quick question about {{ $json.lead_name }}`
   - Text:
     ```
     Hi {{ $json.lead_name }},
     
     I noticed you visited our site. Have any questions I can answer?
     
     Feel free to reply to this email or call {{ $json.owner_phone }}
     
     Best
     ORB
     ```

### Step 5: Wait 5 Days

1. Add another **Wait** node (3 days)

### Step 6: Send Second Email

1. Add another **Gmail** node with subject: `Following up...`
2. Text:
   ```
   Hi {{ $json.lead_name }},
   
   Just wanted to make sure you got my first email. 
   
   Let me know if you have any questions!
   
   Best
   ORB
   ```

### Step 7: Notify ORB When Done

1. Right-click canvas → **Add Node**
2. Search for "HTTP Request"
3. Select "HTTP Request"
4. In the panel:
   - Method: **POST**
   - URL: `{{ env.ORB_WEBHOOK_URL }}`
   - Body:
     ```json
     {
       "event": "sequence_complete",
       "lead_email": "{{ $json.lead_email }}",
       "workflow_name": "30_day_lead_nurture",
       "completed_at": "{{ $json.now }}"
     }
     ```

### Step 8: Activate the Workflow

1. Click the **Save** button (top-right)
2. Toggle the **Activate** switch to ON
3. You should see "Workflow is active" message

---

## STEP 4: Create Second Workflow - "Hot Lead Urgent"

This runs immediately for hot prospects.

1. Create new workflow: `hot_lead_urgent`
2. Similar steps, but:
   - Step 3: Wait **0 Hours** (send immediately)
   - Subject: `⚡ Time-Sensitive Opportunity`
   - Add a phone call step (we'll use Twilio)

---

## STEP 5: Talk ORB Workflows

In `integrations/n8n_workflows.py`, add this configuration:

```python
N8N_WORKFLOWS = {
    "30_day_nurture": {
        "workflow_id": "12345",  # From N8N URL after creating workflow
        "webhook_url": "https://your-n8n-instance.n8n.cloud/webhook/lead_nurture_start",
        "trigger_event": "new_lead",
        "total_steps": 6,
        "duration_days": 30
    },
    "hot_lead_urgent": {
        "workflow_id": "12346",
        "webhook_url": "https://your-n8n-instance.n8n.cloud/webhook/hot_lead_start",
        "trigger_event": "hot_lead_detected",
        "total_steps": 4,
        "duration_days": 1
    }
}
```

---

## STEP 6: Test It

1. In N8N, click your workflow
2. Click **Test workflow** (top-right)
3. Click **Execute workflow**
4. You should see nodes light up as they execute
5. Wait 3 seconds for the HTTP Request to fire
6. You should see data flowing through

---

## STEP 7: Connect from ORB

When ORB detects a new lead, it will call:

```python
import requests

def start_lead_sequence(lead_id, lead_phone, lead_email, lead_name):
    """Starts the N8N nurture sequence for this lead."""
    
    webhook_url = "https://your-n8n-instance.n8n.cloud/webhook/lead_nurture_start"
    
    payload = {
        "lead_id": lead_id,
        "phone": lead_phone,
        "email": lead_email,
        "name": lead_name,
        "owner_phone": settings.my_phone_number
    }
    
    response = requests.post(webhook_url, json=payload)
    return response.json()
```

---

## STEP 8: N8N Sends Webhook Back to ORB

When the workflow completes (after 30 days), N8N calls:

```
POST http://localhost:8000/webhooks/n8n/sequence_complete
```

With payload:
```json
{
  "event": "sequence_complete",
  "lead_email": "prospect@company.com",
  "workflow_name": "30_day_lead_nurture",
  "completed_at": "2026-04-30T15:30:00Z"
}
```

ORB receives this and updates:
- `sequences.status` = "completed"
- `sequences.last_action_at` = now
- `leads.status` = "nurtured" (if no response)

---

## Troubleshooting

**"Workflow not triggering"**
- Make sure workflow is toggled to **Active** (not Inactive)
- Check that the webhook URL in N8N matches what ORB is calling

**"Gmail auth failed"**
- Click the Gmail node
- Click "Disconnect"
- Click "Connect" again
- Allow Gmail access when prompted

**"Email not sending"**
- Check Gmail node for:
  - Valid email addresses
  - Subject is not empty
  - Gmail account has 2FA enabled (optional)

**"Can't find N8N workflow_id"**
- In N8N, click your workflow
- Look at the URL: `https://app.n8n.cloud/workflow/[WORKFLOW_ID]`
- That number is your workflow_id

---

## Next Steps

1. Create the two workflows above
2. Get their IDs
3. Update `integrations/n8n_workflows.py`
4. Test by creating a lead in ORB
5. Watch it get added to Supabase `sequences` table
6. See the N8N workflow fire automatically

---

## N8N Pricing

- **Free**: Up to 5 workflows, limited executions
- **Professional**: $50/month, unlimited workflows (recommended for ORB)
- **Enterprise**: Custom pricing

For full ORB functionality, **Professional plan recommended**.
