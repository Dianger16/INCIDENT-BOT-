# bot/monitor.py
# Polls CloudWatch for CPU, status checks, and log errors
# Returns structured incident objects when thresholds are breached

import boto3
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
import os

logger = logging.getLogger(__name__)


@dataclass
class Incident:
    """Represents a detected incident"""
    type: str           # cpu_high | status_check | http_500 | app_error | deploy_fail
    severity: str       # critical | high | medium | low
    title: str
    description: str
    metric_value: Optional[float]
    threshold: Optional[float]
    instance_id: str
    timestamp: datetime
    raw_data: dict


class CloudWatchMonitor:
    """
    Monitors AWS CloudWatch for incidents across 4 categories:
    - High CPU / Memory
    - Application error logs
    - Failed deployments
    - HTTP 500 errors
    """

    def __init__(self):
        self.cw = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
        self.logs = boto3.client("logs", region_name=os.getenv("AWS_REGION", "us-east-1"))
        self.instance_id = os.getenv("EC2_INSTANCE_ID", "")
        self.cpu_threshold = float(os.getenv("CPU_THRESHOLD", 80))
        self.log_group = f"/ec2/iac-monitoring/app"

    def check_all(self) -> list[Incident]:
        """Run all checks and return list of active incidents"""
        incidents = []

        checks = [
            self._check_cpu,
            self._check_status,
            self._check_log_errors,
            self._check_alarms,
        ]

        for check in checks:
            try:
                result = check()
                if result:
                    incidents.extend(result if isinstance(result, list) else [result])
            except Exception as e:
                logger.error(f"Check {check.__name__} failed: {e}")

        return incidents

    def _get_metric(self, metric_name: str, namespace: str = "AWS/EC2",
                    period: int = 300, stat: str = "Average") -> Optional[float]:
        """Fetch latest metric value from CloudWatch"""
        now = datetime.now(timezone.utc)
        resp = self.cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": self.instance_id}],
            StartTime=now - timedelta(minutes=15),
            EndTime=now,
            Period=period,
            Statistics=[stat],
        )
        datapoints = sorted(resp.get("Datapoints", []), key=lambda x: x["Timestamp"])
        if datapoints:
            return datapoints[-1][stat]
        return None

    # ── Check 1: High CPU ────────────────────────────────────────────────────
    def _check_cpu(self) -> Optional[Incident]:
        cpu = self._get_metric("CPUUtilization")
        if cpu is None:
            logger.warning("No CPU data returned from CloudWatch")
            return None

        logger.info(f"CPU: {cpu:.1f}%")

        if cpu >= self.cpu_threshold:
            severity = "critical" if cpu >= 95 else "high"
            return Incident(
                type="cpu_high",
                severity=severity,
                title=f"High CPU Usage: {cpu:.1f}%",
                description=(
                    f"EC2 instance {self.instance_id} CPU is at {cpu:.1f}%, "
                    f"exceeding threshold of {self.cpu_threshold}%. "
                    f"This may indicate a runaway process, traffic spike, or memory leak."
                ),
                metric_value=cpu,
                threshold=self.cpu_threshold,
                instance_id=self.instance_id,
                timestamp=datetime.now(timezone.utc),
                raw_data={"cpu_percent": cpu, "threshold": self.cpu_threshold},
            )
        return None

    # ── Check 2: Instance status ──────────────────────────────────────────────
    def _check_status(self) -> Optional[Incident]:
        status = self._get_metric("StatusCheckFailed", stat="Maximum", period=60)
        if status is None:
            return None

        logger.info(f"Status check: {status}")

        if status > 0:
            return Incident(
                type="status_check",
                severity="critical",
                title="EC2 Instance Status Check Failed",
                description=(
                    f"Instance {self.instance_id} is failing status checks. "
                    f"This may indicate hardware failure, kernel panic, or network issue. "
                    f"Immediate action required."
                ),
                metric_value=status,
                threshold=0,
                instance_id=self.instance_id,
                timestamp=datetime.now(timezone.utc),
                raw_data={"status_check_failed": status},
            )
        return None

    # ── Check 3: App error logs ───────────────────────────────────────────────
    def _check_log_errors(self) -> list[Incident]:
        """Scan CloudWatch logs for ERROR, HTTP 500, and deploy failures"""
        incidents = []
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=15)

        patterns = [
            {
                "filter": '"ERROR"',
                "type": "app_error",
                "severity": "high",
                "title": "Application Errors Detected in Logs",
            },
            {
                "filter": '"500"',
                "type": "http_500",
                "severity": "high",
                "title": "HTTP 500 Errors Detected",
            },
            {
                "filter": '"DEPLOY FAILED"',
                "type": "deploy_fail",
                "severity": "critical",
                "title": "Deployment Failure Detected",
            },
        ]

        for pattern in patterns:
            try:
                resp = self.logs.filter_log_events(
                    logGroupName=self.log_group,
                    startTime=int(start.timestamp() * 1000),
                    endTime=int(now.timestamp() * 1000),
                    filterPattern=pattern["filter"],
                    limit=10,
                )
                events = resp.get("events", [])
                if not events:
                    continue

                sample_logs = "\n".join(
                    e.get("message", "")[:200] for e in events[:5]
                )

                incidents.append(Incident(
                    type=pattern["type"],
                    severity=pattern["severity"],
                    title=f"{pattern['title']} ({len(events)} occurrences)",
                    description=(
                        f"Found {len(events)} log entries matching '{pattern['filter']}' "
                        f"in the last 15 minutes.\n\nSample logs:\n{sample_logs}"
                    ),
                    metric_value=float(len(events)),
                    threshold=0.0,
                    instance_id=self.instance_id,
                    timestamp=datetime.now(timezone.utc),
                    raw_data={"event_count": len(events), "sample": sample_logs},
                ))

            except self.logs.exceptions.ResourceNotFoundException:
                logger.warning(f"Log group {self.log_group} not found — skipping log check")
            except Exception as e:
                logger.error(f"Log check failed for pattern {pattern['filter']}: {e}")

        return incidents

    # ── Check 4: CloudWatch alarm states ─────────────────────────────────────
    def _check_alarms(self) -> list[Incident]:
        """Check if any CloudWatch alarms are in ALARM state"""
        incidents = []
        resp = self.cw.describe_alarms(
            AlarmNamePrefix="iac-monitoring",
            StateValue="ALARM",
        )

        for alarm in resp.get("MetricAlarms", []):
            incidents.append(Incident(
                type="cloudwatch_alarm",
                severity="high",
                title=f"CloudWatch Alarm: {alarm['AlarmName']}",
                description=alarm.get("AlarmDescription", "No description"),
                metric_value=None,
                threshold=alarm.get("Threshold"),
                instance_id=self.instance_id,
                timestamp=datetime.now(timezone.utc),
                raw_data={"alarm_name": alarm["AlarmName"], "reason": alarm.get("StateReason", "")},
            ))

        return incidents