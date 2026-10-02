"""Unit tests for Kubernetes log parsing."""

import pytest
from k8s_agent.parser import LogParser


def test_parse_cri_log_format():
    parser = LogParser()
    raw = "2026-10-02T18:15:06.110Z stderr F memory cgroup out of memory: kill process 1248"
    entry = parser.parse_line(raw, line_number=42)

    assert entry.line_number == 42
    assert entry.timestamp == "2026-10-02T18:15:06.110Z"
    assert entry.stream == "stderr"
    assert "memory cgroup out of memory" in entry.message
    assert entry.raw_content == raw


def test_parse_json_structured_log():
    parser = LogParser()
    json_line = (
        '{"timestamp": "2026-10-02T19:00:00Z", "level": "error", "message": "DB timeout", "stream": "stderr"}'
    )
    entry = parser.parse_line(json_line, line_number=10)

    assert entry.line_number == 10
    assert entry.is_json is True
    assert entry.level == "ERROR"
    assert entry.message == "DB timeout"
    assert entry.timestamp == "2026-10-02T19:00:00Z"


def test_parse_k8s_events_format():
    parser = LogParser()
    event_line = "Warning  Unhealthy  40s  kubelet  Liveness probe failed: HTTP probe failed with statuscode: 500"
    entry = parser.parse_line(event_line, line_number=5)

    assert entry.line_number == 5
    assert entry.level == "WARN"
    assert entry.component == "kubelet"
    assert "[Unhealthy]" in entry.message


def test_parse_multiline_text():
    parser = LogParser()
    text = """[INFO] Server starting
[WARN] Connection pool saturated
[ERROR] Database crashed"""
    entries = parser.parse_text(text)

    assert len(entries) == 3
    assert entries[0].line_number == 1
    assert entries[0].level == "INFO"
    assert entries[1].line_number == 2
    assert entries[1].level == "WARN"
    assert entries[2].line_number == 3
    assert entries[2].level == "ERROR"
