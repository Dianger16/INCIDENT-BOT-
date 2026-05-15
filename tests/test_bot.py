# tests/test_bot.py
# Unit tests — run without needing real AWS, Slack, or OpenRouter credentials

import pytest
import sys
import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from bot.monitor import Incident
from bot.analyzer import _fallback_analysis, _build_prompt
from bot.notifier import SlackNotifier, SEVERITY_EMOJI, SEVERITY_COLOR


def make_incident(type="cpu_high", severity="high", value=85.0):
    return Incident(
        type=type,
        severity=severity,
        title=f"Test incident: {type}",
        description="Test description for unit testing",
        metric_value=value,
        threshold=80.0,
        instance_id="i-0test123",
        timestamp=datetime.now(timezone.utc),
        raw_data={"test": True},
    )


class TestFallbackAnalysis:
    def test_cpu_fallback_returns_all_keys(self):
        inc = make_incident("cpu_high")
        result = _fallback_analysis(inc)
        for key in ["root_cause", "immediate_actions", "investigation_commands", "prevention"]:
            assert key in result

    def test_http500_fallback(self):
        inc = make_incident("http_500")
        result = _fallback_analysis(inc)
        assert "root_cause" in result
        assert len(result["immediate_actions"]) >= 2

    def test_deploy_fail_fallback(self):
        inc = make_incident("deploy_fail")
        result = _fallback_analysis(inc)
        assert len(result["immediate_actions"]) >= 2

    def test_unknown_type_returns_generic(self):
        inc = make_incident("unknown_type")
        result = _fallback_analysis(inc)
        assert "root_cause" in result

    def test_status_check_fallback(self):
        inc = make_incident("status_check")
        result = _fallback_analysis(inc)
        assert "root_cause" in result
        assert "estimated_resolution_time" in result


class TestPromptBuilder:
    def test_prompt_contains_incident_fields(self):
        inc = make_incident()
        prompt = _build_prompt(inc)
        assert inc.type in prompt
        assert inc.severity in prompt
        assert inc.instance_id in prompt
        assert inc.description in prompt

    def test_prompt_contains_metric_value(self):
        inc = make_incident(value=95.5)
        prompt = _build_prompt(inc)
        assert "95.5" in prompt

    def test_prompt_ends_with_json_instruction(self):
        inc = make_incident()
        prompt = _build_prompt(inc)
        assert "JSON" in prompt


class TestSlackNotifier:
    def test_severity_emoji_coverage(self):
        for sev in ["critical", "high", "medium", "low"]:
            assert sev in SEVERITY_EMOJI

    def test_severity_color_coverage(self):
        for sev in ["critical", "high", "medium", "low"]:
            assert sev in SEVERITY_COLOR

    def test_build_blocks_structure(self):
        notifier = SlackNotifier.__new__(SlackNotifier)
        inc = make_incident()
        analysis = {
            "root_cause": "Test root cause",
            "immediate_actions": ["Action 1", "Action 2"],
            "investigation_commands": ["top -bn1", "ps aux"],
            "prevention": "Test prevention",
            "estimated_resolution_time": "5 minutes",
        }
        blocks = notifier._build_blocks(inc, analysis)
        assert len(blocks) > 0
        assert any(b.get("type") == "header" for b in blocks)
        assert any(b.get("type") == "section" for b in blocks)


class TestIncidentDataclass:
    def test_incident_creation(self):
        inc = make_incident()
        assert inc.type == "cpu_high"
        assert inc.severity == "high"
        assert inc.metric_value == 85.0

    def test_incident_all_types(self):
        types = ["cpu_high", "status_check", "http_500", "app_error", "deploy_fail"]
        for t in types:
            inc = make_incident(type=t)
            assert inc.type == t

    def test_incident_timestamp_is_utc(self):
        inc = make_incident()
        assert inc.timestamp.tzinfo is not None