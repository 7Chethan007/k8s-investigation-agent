"""ADK Tools package for Kubernetes diagnostics and investigation.

Provides modular tools conforming to Google Agent Development Kit (ADK) specifications:
- get_pod_logs: Fetches container stdout/stderr logs from cluster.
- get_pod_events: Fetches lifecycle/warning events for a pod.
- get_deployment_history: Analyzes recent rollouts and container image version changes.
- investigate_kubernetes_logs: Analyzes raw logs and events with automated RCA.
"""

from k8s_agent.tools.deployment_history import (
    get_deployment_history,
    get_deployment_history_tool,
)
from k8s_agent.tools.investigate import investigate_kubernetes_logs
from k8s_agent.tools.pod_events import get_pod_events
from k8s_agent.tools.pod_logs import get_pod_logs

__all__ = [
    "get_pod_logs",
    "get_pod_events",
    "get_deployment_history",
    "get_deployment_history_tool",
    "investigate_kubernetes_logs",
]
