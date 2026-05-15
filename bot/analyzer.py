# bot/analyzer.py
# Sends incident details to OpenRouter and gets structured fix suggestions
# OpenRouter: openrouter.ai — supports 100+ models, many free
# Free models: meta-llama/llama-3-70b, mistralai/mistral-7b, etc.

import logging
import json
import os
import requests
from bot.monitor import Incident

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-70b-instruct:nitro")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are an expert DevOps Site Reliability Engineer (SRE) with 10+ years of experience.
You analyze infrastructure incidents and provide clear, actionable fix suggestions.

Always respond in this exact JSON format with no extra text, no markdown, no backticks:
{
  "root_cause": "Brief explanation of what likely caused this incident (2-3 sentences)",
  "severity_assessment": "Why this severity level is correct",
  "immediate_actions": [
    "Step 1 — specific command or action",
    "Step 2 — specific command or action",
    "Step 3 — specific command or action"
  ],
  "investigation_commands": [
    "exact bash command to run for diagnosis",
    "another diagnostic command"
  ],
  "prevention": "How to prevent this from happening again (1-2 sentences)",
  "estimated_resolution_time": "e.g. 5-10 minutes"
}

Be specific. Include actual commands. Reference AWS services when relevant."""


def analyze_incident(incident: Incident) -> dict:
    """
    Send incident to OpenRouter and return structured fix suggestions.
    Falls back gracefully if API is unavailable.
    """
    prompt = _build_prompt(incident)

    try:
        response = requests.post(
            url=API_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/incident-bot",  # required by OpenRouter
                "X-Title": "AI Incident Response Bot",               # shows in OpenRouter dashboard
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if model adds them
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)
        logger.info(f"OpenRouter analysis complete for: {incident.type} using {MODEL}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"OpenRouter returned invalid JSON: {e}")
        return _fallback_analysis(incident)
    except requests.exceptions.Timeout:
        logger.error("OpenRouter request timed out")
        return _fallback_analysis(incident)
    except requests.exceptions.HTTPError as e:
        logger.error(f"OpenRouter HTTP error: {e.response.status_code} — {e.response.text}")
        return _fallback_analysis(incident)
    except Exception as e:
        logger.error(f"OpenRouter call failed: {e}")
        return _fallback_analysis(incident)


def _build_prompt(incident: Incident) -> str:
    """Build a detailed prompt from the incident object"""
    lines = [
        "INCIDENT REPORT",
        "================",
        f"Type:        {incident.type}",
        f"Severity:    {incident.severity}",
        f"Title:       {incident.title}",
        f"Timestamp:   {incident.timestamp.isoformat()}",
        f"Instance ID: {incident.instance_id}",
        "",
        "Description:",
        incident.description,
    ]

    if incident.metric_value is not None:
        lines.append(f"\nMetric Value: {incident.metric_value}")
    if incident.threshold is not None:
        lines.append(f"Threshold:    {incident.threshold}")
    if incident.raw_data:
        lines.append(f"\nRaw Data:\n{json.dumps(incident.raw_data, indent=2)}")

    lines.append("\nAnalyze this incident and respond with JSON only — no markdown, no explanation outside the JSON.")
    return "\n".join(lines)


def _fallback_analysis(incident: Incident) -> dict:
    """
    Returns hardcoded fix suggestions when OpenRouter is unavailable.
    Ensures the bot still works without AI.
    """
    fallbacks = {
        "cpu_high": {
            "root_cause": "CPU utilization exceeded threshold. Common causes: runaway process, traffic spike, or inefficient code.",
            "severity_assessment": f"CPU at {incident.metric_value:.0f}% requires immediate attention to prevent service degradation.",
            "immediate_actions": [
                "SSH into instance: ssh -i scripts/ec2_key ubuntu@EC2_IP",
                "Identify top processes: top -bn1 | head -20",
                "Kill runaway process if found: sudo kill -9 <PID>",
            ],
            "investigation_commands": [
                "top -bn1 | head -20",
                "ps aux --sort=-%cpu | head -10",
                "sudo journalctl -u demo-app --no-pager -n 50",
            ],
            "prevention": "Set up auto-scaling or optimize the application code. Add CPU-based scaling policies.",
            "estimated_resolution_time": "5-15 minutes",
        },
        "http_500": {
            "root_cause": "Application returning HTTP 500 errors indicating server-side failures.",
            "severity_assessment": "500 errors directly impact users and indicate broken functionality.",
            "immediate_actions": [
                "Check application logs: sudo journalctl -u demo-app -n 100",
                "Restart the service: sudo systemctl restart demo-app",
                "Verify health endpoint: curl http://localhost:3000/health",
            ],
            "investigation_commands": [
                "sudo journalctl -u demo-app --no-pager -n 100",
                "sudo systemctl status demo-app",
                "curl -v http://localhost:3000/health",
            ],
            "prevention": "Add proper error handling, input validation, and circuit breakers to the application.",
            "estimated_resolution_time": "5-10 minutes",
        },
        "deploy_fail": {
            "root_cause": "Deployment pipeline failed, possibly due to test failures, build errors, or infrastructure issues.",
            "severity_assessment": "Failed deployments block new features and fixes from reaching production.",
            "immediate_actions": [
                "Check deployment logs in GitHub Actions",
                "Verify previous stable version is still running",
                "Roll back if needed: git revert HEAD && git push",
            ],
            "investigation_commands": [
                "git log --oneline -10",
                "docker ps -a",
                "sudo journalctl -u demo-app --no-pager -n 50",
            ],
            "prevention": "Add more comprehensive pre-deployment tests and staging environment validation.",
            "estimated_resolution_time": "10-30 minutes",
        },
        "status_check": {
            "root_cause": "EC2 instance failing status checks — possible hardware issue, kernel panic, or network problem.",
            "severity_assessment": "Status check failure means the instance may be completely unreachable.",
            "immediate_actions": [
                "Check instance status in AWS Console → EC2 → Instances",
                "Try to reboot: aws ec2 reboot-instances --instance-ids INSTANCE_ID",
                "If unreachable, stop and start from AWS Console → Instance State",
            ],
            "investigation_commands": [
                "aws ec2 describe-instance-status --instance-ids INSTANCE_ID",
                "aws ec2 get-console-output --instance-id INSTANCE_ID",
            ],
            "prevention": "Set up EC2 Auto Recovery to automatically recover failed instances.",
            "estimated_resolution_time": "5-20 minutes",
        },
    }

    return fallbacks.get(incident.type, {
        "root_cause": f"Incident of type '{incident.type}' detected.",
        "severity_assessment": f"Severity: {incident.severity}",
        "immediate_actions": ["Investigate the incident", "Check system logs", "Contact on-call engineer"],
        "investigation_commands": ["sudo journalctl -n 100", "top -bn1", "df -h"],
        "prevention": "Add monitoring and alerting for this incident type.",
        "estimated_resolution_time": "Unknown",
    })