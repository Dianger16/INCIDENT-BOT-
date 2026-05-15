# simulator/simulate.py
# Simulates incidents locally to test the full bot pipeline
# without needing real CloudWatch alerts
# Usage: python simulator/simulate.py [incident_type]

import sys
import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot.monitor import Incident
from bot.analyzer import analyze_incident
from bot.notifier import SlackNotifier

SIMULATED_INCIDENTS = {
    "cpu": Incident(
        type="cpu_high",
        severity="critical",
        title="High CPU Usage: 97.3%",
        description=(
            "EC2 instance i-0abc123def456789 CPU is at 97.3%, "
            "exceeding threshold of 80%. "
            "This may indicate a runaway process, traffic spike, or memory leak."
        ),
        metric_value=97.3,
        threshold=80.0,
        instance_id=os.getenv("EC2_INSTANCE_ID", "i-0simulated123"),
        timestamp=datetime.now(timezone.utc),
        raw_data={"cpu_percent": 97.3, "threshold": 80.0},
    ),
    "http500": Incident(
        type="http_500",
        severity="high",
        title="HTTP 500 Errors Detected (12 occurrences)",
        description=(
            "Found 12 log entries matching HTTP 500 in the last 15 minutes.\n\n"
            "Sample logs:\n"
            "Error: Cannot read property 'id' of undefined at /api/users\n"
            "Error: Database connection timeout after 30000ms\n"
            "Error: Unhandled promise rejection in payment processor"
        ),
        metric_value=12.0,
        threshold=0.0,
        instance_id=os.getenv("EC2_INSTANCE_ID", "i-0simulated123"),
        timestamp=datetime.now(timezone.utc),
        raw_data={"event_count": 12, "sample": "Error: Cannot read property 'id' of undefined"},
    ),
    "deploy": Incident(
        type="deploy_fail",
        severity="critical",
        title="Deployment Failure Detected",
        description=(
            "DEPLOY FAILED: GitHub Actions pipeline failed on job 'deploy' at step "
            "'Deploy to EC2'. Health check returned HTTP 500 after 8 attempts. "
            "Auto rollback triggered. Previous version v1.0.2 restored."
        ),
        metric_value=1.0,
        threshold=0.0,
        instance_id=os.getenv("EC2_INSTANCE_ID", "i-0simulated123"),
        timestamp=datetime.now(timezone.utc),
        raw_data={"pipeline": "deploy.yml", "failed_step": "health_check"},
    ),
    "status": Incident(
        type="status_check",
        severity="critical",
        title="EC2 Instance Status Check Failed",
        description=(
            "Instance i-0abc123def456789 is failing status checks. "
            "StatusCheckFailed metric value: 1. "
            "This may indicate hardware failure, kernel panic, or network issue."
        ),
        metric_value=1.0,
        threshold=0.0,
        instance_id=os.getenv("EC2_INSTANCE_ID", "i-0simulated123"),
        timestamp=datetime.now(timezone.utc),
        raw_data={"status_check_failed": 1},
    ),
}


def simulate(incident_type: str = "cpu"):
    incident = SIMULATED_INCIDENTS.get(incident_type)
    if not incident:
        print(f"Unknown type: {incident_type}")
        print(f"Available: {list(SIMULATED_INCIDENTS.keys())}")
        return

    print(f"\n{'='*50}")
    print(f"  Simulating incident: {incident_type}")
    print(f"{'='*50}\n")

    print("Step 1 — Analyzing with OpenAI...")
    analysis = analyze_incident(incident)

    import json
    print("\nAI Analysis:")
    print(json.dumps(analysis, indent=2))

    print("\nStep 2 — Sending to Slack...")
    notifier = SlackNotifier()
    sent = notifier.send_incident(incident, analysis)

    if sent:
        print("✅ Slack alert sent successfully!")
        print(f"   Check your #{os.getenv('SLACK_CHANNEL_ID')} channel")
    else:
        print("❌ Slack send failed — check your SLACK_BOT_TOKEN and SLACK_CHANNEL_ID")


if __name__ == "__main__":
    incident_type = sys.argv[1] if len(sys.argv) > 1 else "cpu"
    simulate(incident_type)