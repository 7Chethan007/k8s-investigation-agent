"""Unit tests for the core InvestigationEngine."""

from pathlib import Path
from k8s_agent.engine import InvestigationEngine
from k8s_agent.models import IncidentCategory, Severity


def test_investigate_oom_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "oom_killed.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine(context_lines=2)
    report = engine.investigate(content, source_name="oom_killed.log")

    assert report.root_cause.category == IncidentCategory.OOM_KILLED
    assert report.root_cause.severity == Severity.CRITICAL
    assert report.root_cause.confidence_score >= 0.95
    assert len(report.evidence) > 0

    # Verify verbatim evidence properties
    trigger_lines = [e.trigger_line for e in report.evidence]
    assert any("exit code 137" in t or "out of memory" in t for t in trigger_lines)

    # Context window verification
    first_ev = report.evidence[0]
    assert isinstance(first_ev.context_before, list)
    assert isinstance(first_ev.context_after, list)
    assert first_ev.line_number > 0

    # Remediation verification
    assert len(report.remediation.immediate_actions) > 0
    assert any("kubectl" in cmd for cmd in report.remediation.remediation_commands)


def test_investigate_dns_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "dns_resolution_failure.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine()
    report = engine.investigate(content, source_name="dns_resolution_failure.log")

    assert report.root_cause.category == IncidentCategory.DNS_RESOLUTION_FAILURE
    assert report.root_cause.severity == Severity.HIGH
    assert any("CoreDNS" in act or "dns" in act.lower() for act in report.remediation.immediate_actions)


def test_investigate_healthy_logs():
    healthy_logs = """2026-10-02T10:00:00Z [INFO] Application started successfully
2026-10-02T10:00:01Z [INFO] Health check probe /healthz 200 OK
2026-10-02T10:00:05Z [INFO] Processed 100 requests with 0 errors
"""
    engine = InvestigationEngine()
    report = engine.investigate(healthy_logs, source_name="healthy.log")

    assert report.root_cause.category == IncidentCategory.UNKNOWN_ANOMALY
    assert report.root_cause.severity == Severity.LOW
    assert len(report.evidence) == 0


def test_investigate_crashloop_db_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "crashloop_db_exhaustion.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine()
    report = engine.investigate(content, source_name="crashloop_db_exhaustion.log")

    # DB exhaustion + Crashloop + Panics
    assert report.root_cause.category in (
        IncidentCategory.DATABASE_EXHAUSTION,
        IncidentCategory.CRASH_LOOP_BACKOFF,
        IncidentCategory.APPLICATION_PANIC,
    )
    assert report.root_cause.severity == Severity.CRITICAL
    assert len(report.evidence) >= 2


def test_investigate_liveness_probe_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "liveness_probe_failure.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine()
    report = engine.investigate(content, source_name="liveness_probe_failure.log")

    assert report.root_cause.category == IncidentCategory.LIVENESS_PROBE_FAILURE
    assert report.root_cause.severity == Severity.HIGH
    assert any("probe" in e.trigger_line.lower() for e in report.evidence)


def test_investigate_image_pull_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "image_pull_backoff.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine()
    report = engine.investigate(content, source_name="image_pull_backoff.log")

    assert report.root_cause.category == IncidentCategory.IMAGE_PULL_FAILURE
    assert report.root_cause.severity == Severity.HIGH
    assert any("image" in cmd.lower() or "secret" in cmd.lower() for cmd in report.remediation.remediation_commands)


def test_investigate_rbac_forbidden_sample():
    sample_path = Path(__file__).parent.parent / "samples" / "rbac_forbidden.log"
    content = sample_path.read_text(encoding="utf-8")

    engine = InvestigationEngine()
    report = engine.investigate(content, source_name="rbac_forbidden.log")

    assert report.root_cause.category == IncidentCategory.RBAC_PERMISSION_DENIED
    assert report.root_cause.severity == Severity.HIGH
    assert any("auth can-i" in cmd for cmd in report.remediation.remediation_commands)

