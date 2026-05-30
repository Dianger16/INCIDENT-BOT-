# AI-Powered Incident Response Bot
### Stack: openrouter api + Slack + Python + CloudWatch

> Project #10 from the DevOps + AI Project Sheet
> Integrates with Project #2 (Terraform + CloudWatch)

---

## What It Does

```
CloudWatch (every 60s)
    │
    ├── CPU > 80%?          ──┐
    ├── Status check failed? ─┤
    ├── HTTP 500 in logs?   ──┤──► Groq (Llama 3)
    ├── App errors in logs? ──┤        │
    └── Deploy failures?   ──┘        │ AI Analysis:
                                      │  - Root cause
                                      │  - Immediate actions
                                      │  - Investigation commands
                                      │  - Prevention advice
                                      ▼
                                  Slack Alert
                                  (rich formatted)
```

---

## Project Structure

```
incident-bot/
├── bot/
│   ├── main.py         → Orchestrates: poll → analyze → notify
│   ├── monitor.py      → Polls CloudWatch for 4 incident types
│   ├── analyzer.py     → Sends incidents to Groq, gets fix suggestions
│   └── notifier.py     → Sends rich Slack Block Kit messages
├── simulator/
│   └── simulate.py     → Test the bot locally without real incidents
├── tests/
│   └── test_bot.py     → Unit tests (no AWS/Slack needed)
├── .env.example        → Environment variables template
├── requirements.txt
└── README.md
```

---

## Step 1 — Get a Groq API Key

1. Go to https://console.groq.com/
2. Sign up or log in
3. Navigate to **API Keys** → **Create API Key**
4. Name it: `incident-bot`
5. Copy the key (starts with `gsk_`) — shown only once

**Free tier:** Groq offers a generous free tier with fast inference — no billing setup required to get started.

---

## Step 2 — Create a Slack App

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Name: `Incident Response Bot` | Workspace: your workspace

**Add Bot Token Scopes:**
- Go to **OAuth & Permissions** → Scopes → Bot Token Scopes
- Add: `chat:write`, `chat:write.public`

**Install to workspace:**
- Click **Install to Workspace** → Allow
- Copy the **Bot User OAuth Token** (starts with `xoxb-`)

**Get Signing Secret:**
- Go to **Basic Information** → App Credentials → copy **Signing Secret**

**Get Channel ID:**
- In Slack, right-click the channel you want alerts in
- Click **View channel details** → scroll to bottom → copy Channel ID (starts with `C`)

**Invite the bot to the channel:**
```
/invite @Incident Response Bot
```

---

## Step 3 — Configure Environment

```bash
cd incident-bot
cp .env.example .env
```

Edit `.env`:
```
GROQ_API_KEY=gsk_...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL_ID=C0XXXXXXXXX
AWS_ACCESS_KEY_ID=...          # same as Project #2
AWS_SECRET_ACCESS_KEY=...      # same as Project #2
AWS_REGION=us-east-1
EC2_INSTANCE_ID=i-0...         # from Project #2 terraform output
```

---

## Step 4 — Install and Run

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate       # Mac/Linux
# venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests first (no AWS/Slack needed)
python -m pytest tests/ -v

# Test the bot with a simulated incident
python simulator/simulate.py cpu       # simulate high CPU
python simulator/simulate.py http500   # simulate HTTP 500 errors
python simulator/simulate.py deploy    # simulate deploy failure
python simulator/simulate.py status    # simulate EC2 status check failure

# Start the bot (runs continuously)
python -m bot.main
```

---

## Demo: Trigger a Real Incident

With Project #2 EC2 running, trigger the CPU alarm:

```bash
# Terminal 1 — start the bot
python -m bot.main

# Terminal 2 — trigger CPU spike on EC2
bash ../iac-monitoring/scripts/stress_test.sh YOUR_EC2_IP
```

Watch your Slack channel receive a rich alert with:
- Incident details
- AI-generated root cause
- Step-by-step fix commands
- Prevention advice
- Estimated resolution time

---

## What a Slack Alert Looks Like

```
🔴 INCIDENT ALERT — CRITICAL
💻 High CPU Usage: 97.3%
   EC2 instance i-0abc123... CPU at 97.3%, threshold 80%

Severity: 🔴 Critical    Type: cpu_high
Instance: i-0abc123      Time: 14:32:01 UTC

🤖 AI Root Cause Analysis
A runaway process is consuming excessive CPU. This is commonly
caused by an infinite loop, memory leak, or sudden traffic spike.

🔧 Immediate Actions
1. SSH into instance: ssh -i scripts/ec2_key ubuntu@EC2_IP
2. Identify top processes: top -bn1 | head -20
3. Kill runaway process: sudo kill -9 <PID>

🔍 Investigation Commands
`top -bn1 | head -20`
`ps aux --sort=-%cpu | head -10`
`sudo journalctl -u demo-app -n 50`

🛡️ Prevention: Add auto-scaling policy
⏱️ Est. Resolution: 5-15 minutes
```

---

## What This Demonstrates

| Skill | Evidence |
|---|---|
| Groq API | Llama 3 for incident analysis, JSON structured output |
| Slack API | Block Kit rich messages, bot setup, channel integration |
| Python | OOP design, dataclasses, error handling, scheduling |
| AWS CloudWatch | Metrics polling, log filtering, alarm state checking |
| boto3 | CloudWatch + CloudWatch Logs client |
| System design | Monitor → Analyze → Notify pipeline |
| Resilience | Fallback analysis when Groq unavailable |
| Testing | Unit tests with mocking, no credentials needed |
| Project integration | Connects to Project #2 infrastructure |
