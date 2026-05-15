# bot/main.py
# Main entrypoint — runs the monitoring loop
# Usage: python -m bot.main

import logging
import os
import schedule
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from bot.monitor import CloudWatchMonitor, Incident
from bot.analyzer import analyze_incident
from bot.notifier import SlackNotifier

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Track active incidents to avoid duplicate alerts
# key = incident type, value = timestamp first seen
active_incidents: dict[str, datetime] = {}


def run_checks():
    """
    Main polling loop:
    1. Check CloudWatch for incidents
    2. For each new incident → analyze with OpenAI
    3. Send Slack alert with fix suggestions
    4. Send resolution when incident clears
    """
    monitor  = CloudWatchMonitor()
    notifier = SlackNotifier()

    logger.info("Running incident checks...")
    incidents = monitor.check_all()

    if not incidents:
        logger.info("✅ All systems healthy — no incidents detected")
        # Resolve any previously active incidents
        for inc_type in list(active_incidents.keys()):
            logger.info(f"Incident resolved: {inc_type}")
            notifier.send_resolved(f"{inc_type} incident cleared")
            del active_incidents[inc_type]
        return

    # Process each detected incident
    current_types = {inc.type for inc in incidents}

    for incident in incidents:
        if incident.type in active_incidents:
            logger.info(f"Incident already active, skipping duplicate alert: {incident.type}")
            continue

        logger.info(f"🚨 New incident detected: {incident.type} ({incident.severity})")

        # Analyze with OpenAI
        logger.info("Calling OpenRouter for analysis...")
        analysis = analyze_incident(incident)

        # Send to Slack
        sent = notifier.send_incident(incident, analysis)
        if sent:
            active_incidents[incident.type] = datetime.now(timezone.utc)
            logger.info(f"Alert sent to Slack: {incident.title}")
        else:
            logger.error(f"Failed to send Slack alert for: {incident.title}")

    # Resolve incidents that have cleared
    for inc_type in list(active_incidents.keys()):
        if inc_type not in current_types:
            logger.info(f"Incident resolved: {inc_type}")
            notifier.send_resolved(f"{inc_type} has resolved")
            del active_incidents[inc_type]


def validate_env():
    """Validate all required environment variables before starting"""
    required = [
        "OPENROUTER_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "EC2_INSTANCE_ID",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Copy .env.example to .env and fill in your values")
        return False
    return True


def main():
    logger.info("=" * 50)
    logger.info("  AI Incident Response Bot — Starting")
    logger.info("=" * 50)

    if not validate_env():
        return

    interval = int(os.getenv("POLL_INTERVAL_SECONDS", 60))
    logger.info(f"Polling CloudWatch every {interval} seconds")
    logger.info(f"Monitoring instance: {os.getenv('EC2_INSTANCE_ID')}")
    logger.info(f"Alerting to Slack channel: {os.getenv('SLACK_CHANNEL_ID')}")

    # Run immediately on start
    run_checks()

    # Then on schedule
    schedule.every(interval).seconds.do(run_checks)

    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    main()