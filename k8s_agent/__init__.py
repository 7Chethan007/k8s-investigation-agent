"""Kubernetes Investigation Agent."""

from k8s_agent.engine import InvestigationEngine
from k8s_agent.models import (
    EvidenceItem,
    IncidentCategory,
    InvestigationReport,
    LogEntry,
    Remediation,
    RootCause,
    Severity,
    TimelineEvent,
)
from k8s_agent.parser import LogParser
from k8s_agent.reporter import ReportRenderer
from k8s_agent.tools import (
    get_deployment_history,
    get_pod_events,
    get_pod_logs,
    investigate_kubernetes_logs,
)

__version__ = "0.1.0"

__all__ = [
    "InvestigationEngine",
    "LogParser",
    "ReportRenderer",
    "get_pod_logs",
    "get_pod_events",
    "get_deployment_history",
    "investigate_kubernetes_logs",
    "InvestigationReport",
    "EvidenceItem",
    "RootCause",
    "Remediation",
    "TimelineEvent",
    "IncidentCategory",
    "Severity",
    "LogEntry",
]
