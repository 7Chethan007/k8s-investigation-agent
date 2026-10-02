"""Unit tests for diagnostic rules and failure detectors."""

from k8s_agent.detectors import RULES
from k8s_agent.models import IncidentCategory
from k8s_agent.parser import LogParser


def test_oom_killed_detection():
    line = "command terminated with exit code 137"
    matched_categories = []
    for rule in RULES:
        for p in rule.patterns:
            if p.search(line):
                matched_categories.append(rule.category)
                break
    assert IncidentCategory.OOM_KILLED in matched_categories


def test_crashloop_backoff_detection():
    line = "Back-off restarting failed container"
    matched = any(p.search(line) for r in RULES if r.category == IncidentCategory.CRASH_LOOP_BACKOFF for p in r.patterns)
    assert matched is True


def test_dns_failure_detection():
    line = "dial tcp: lookup order-service.prod on 10.96.0.10:53: i/o timeout"
    matched = any(p.search(line) for r in RULES if r.category == IncidentCategory.DNS_RESOLUTION_FAILURE for p in r.patterns)
    assert matched is True


def test_probe_failure_detection():
    line = "Liveness probe failed: HTTP probe failed with statuscode: 500"
    matched = any(p.search(line) for r in RULES if r.category == IncidentCategory.LIVENESS_PROBE_FAILURE for p in r.patterns)
    assert matched is True


def test_rbac_denied_detection():
    line = 'secrets is forbidden: User "system:serviceaccount:staging:my-sa" cannot get resource "secrets"'
    matched = any(p.search(line) for r in RULES if r.category == IncidentCategory.RBAC_PERMISSION_DENIED for p in r.patterns)
    assert matched is True
