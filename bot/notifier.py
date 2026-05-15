# bot/notifier.py
# Sends rich formatted incident alerts to Slack
# Uses Block Kit for professional formatting

import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from bot.monitor import Incident
import os

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

SEVERITY_COLOR = {
    "critical": "#d13212",
    "high":     "#FF9900",
    "medium":   "#f0ad4e",
    "low":      "#36a64f",
}

TYPE_EMOJI = {
    "cpu_high":        "💻",
    "status_check":    "🖥️",
    "http_500":        "🌐",
    "app_error":       "⚠️",
    "deploy_fail":     "🚀",
    "cloudwatch_alarm":"📊",
}


class SlackNotifier:
    def __init__(self):
        self.client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
        self.channel = os.getenv("SLACK_CHANNEL_ID")

    def send_incident(self, incident: Incident, analysis: dict) -> bool:
        """Send a rich formatted incident alert to Slack"""
        try:
            blocks = self._build_blocks(incident, analysis)

            self.client.chat_postMessage(
                channel=self.channel,
                text=f"{SEVERITY_EMOJI.get(incident.severity, '⚠️')} Incident: {incident.title}",
                blocks=blocks,
                attachments=[{
                    "color": SEVERITY_COLOR.get(incident.severity, "#808080"),
                }]
            )
            logger.info(f"Slack alert sent: {incident.title}")
            return True

        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            return False

    def send_resolved(self, incident_title: str) -> bool:
        """Send a resolution notice when incident clears"""
        try:
            self.client.chat_postMessage(
                channel=self.channel,
                text=f"✅ Resolved: {incident_title}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *Incident Resolved*\n_{incident_title}_\n\nSystem has returned to normal."
                        }
                    }
                ]
            )
            return True
        except SlackApiError as e:
            logger.error(f"Slack error: {e.response['error']}")
            return False

    def _build_blocks(self, incident: Incident, analysis: dict) -> list:
        """Build Slack Block Kit message"""
        severity_emoji = SEVERITY_EMOJI.get(incident.severity, "⚠️")
        type_emoji = TYPE_EMOJI.get(incident.type, "⚠️")

        immediate = analysis.get("immediate_actions", [])
        commands  = analysis.get("investigation_commands", [])

        # Format immediate actions
        actions_text = "\n".join(f"*{i+1}.* {a}" for i, a in enumerate(immediate))

        # Format investigation commands
        commands_text = "\n".join(f"`{c}`" for c in commands[:3])

        blocks = [
            # ── Header ──────────────────────────────────────────────────────
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} INCIDENT ALERT — {incident.severity.upper()}",
                }
            },
            # ── Incident info ────────────────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{type_emoji} *{incident.title}*\n_{incident.description[:300]}..._"
                            if len(incident.description) > 300
                            else f"{type_emoji} *{incident.title}*\n_{incident.description}_"
                },
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity_emoji} {incident.severity.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{incident.type}"},
                    {"type": "mrkdwn", "text": f"*Instance:*\n`{incident.instance_id}`"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{incident.timestamp.strftime('%H:%M:%S UTC')}"},
                ]
            },
            {"type": "divider"},
            # ── AI root cause ────────────────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🤖 *AI Root Cause Analysis*\n{analysis.get('root_cause', 'Analysis unavailable')}",
                }
            },
            # ── Immediate actions ────────────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔧 *Immediate Actions*\n{actions_text}",
                }
            },
            # ── Investigation commands ───────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔍 *Investigation Commands*\n{commands_text}",
                }
            },
            # ── Prevention + ETA ─────────────────────────────────────────────
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*🛡️ Prevention:*\n{analysis.get('prevention', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*⏱️ Est. Resolution:*\n{analysis.get('estimated_resolution_time', 'Unknown')}"
                    },
                ]
            },
            {"type": "divider"},
            # ── Footer ──────────────────────────────────────────────────────
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"🤖 AI Incident Response Bot | Powered by OpenRouter | Project #10"
                }]
            }
        ]

        return blocks