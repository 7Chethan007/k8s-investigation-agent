"""ADK tool for running automated root-cause analysis on Kubernetes logs."""

import json
from typing import Any, Union
from k8s_agent.engine import InvestigationEngine
from k8s_agent.reporter import ReportRenderer


def investigate_kubernetes_logs(log_content: Union[str, dict]) -> str:
    """Analyzes raw Kubernetes log content (e.g. from get_pod_logs, get_pod_events, or kubectl).

    Performs automated root cause analysis, identifies failures (OOMKilled, CrashLoopBackOff,
    probe failures, DNS/networking issues, RBAC, etc.), extracts verbatim log evidence,
    reconstructs incident timeline, and returns actionable remediation steps.

    Args:
        log_content: The text content of Kubernetes logs or events to analyze. Can also be
                     a dictionary output from get_pod_logs or get_pod_events.

    Returns:
        A comprehensive Markdown investigation report.
    """
    actual_logs = ""
    if isinstance(log_content, dict):
        # Extract logs or raw_events_text if dictionary passed
        actual_logs = log_content.get("logs") or log_content.get("raw_events_text") or str(log_content)
    elif isinstance(log_content, str):
        actual_logs = log_content
        if log_content.strip().startswith("{"):
            try:
                parsed = json.loads(log_content)
                if isinstance(parsed, dict):
                    actual_logs = parsed.get("logs") or parsed.get("raw_events_text") or log_content
            except Exception:
                pass

    engine = InvestigationEngine()
    report = engine.investigate(actual_logs, source_name="k8s-pod-investigation")
    return ReportRenderer.render_markdown(report)
