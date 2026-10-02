"""ADK agent definition for compatibility with Google agents-cli."""

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from k8s_agent.tools import (
    get_deployment_history,
    get_pod_events,
    get_pod_logs,
    investigate_kubernetes_logs,
)

MODEL = "gemini-2.5-flash"

root_agent = Agent(
    name="k8s_investigation_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an expert Kubernetes Site Reliability Engineer (SRE). "
        "When users ask you to investigate Kubernetes errors, cluster issues, or pod failures: "
        "1. Retrieve the pod's live container logs directly from the cluster using `get_pod_logs`. "
        "   Do not read log files from local disk as input. "
        "   If the user specifies a container or requests previous logs (for crashed/restarted containers), pass those parameters. "
        "2. Retrieve the pod's lifecycle and failure events from the cluster using `get_pod_events` "
        "   (vital for diagnosing Warning events, OOMKilled, BackOff restarts, scheduling errors, and probe failures). "
        "3. Check for recent rollouts, image tag updates, or manifest revisions using `get_deployment_history` "
        "   to verify if a recent code or container version change triggered the incident. "
        "4. Use `investigate_kubernetes_logs` with the retrieved log content to perform automated root-cause analysis, "
        "   isolate anomalies, and build an incident timeline. "
        "5. Correlate log evidence, cluster events, and deployment version changes to present a comprehensive post-mortem "
        "   with root cause, confidence score, blast radius, verbatim evidence, and actionable kubectl remediation commands."
    ),
    tools=[get_pod_logs, get_pod_events, get_deployment_history, investigate_kubernetes_logs],
)

app = App(
    root_agent=root_agent,
    name="k8s_agent",
)
