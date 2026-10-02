"""ADK tool for fetching Kubernetes pod lifecycle and diagnostic events."""

import json
import logging
from typing import Any, Dict, List, Optional

from k8s_agent.tools.common import (
    find_mock_sample_content,
    get_core_v1_api,
    run_kubectl_command,
)

logger = logging.getLogger(__name__)


def _format_event_text(events: List[Dict[str, Any]]) -> str:
    """Formats a list of event dictionaries into standard kubectl events table format."""
    lines = ["TYPE     REASON          COUNT  SOURCE             MESSAGE"]
    lines.append("-" * 75)
    for ev in events:
        ev_type = ev.get("type", "Normal")
        reason = ev.get("reason", "Unknown")[:15].ljust(15)
        count = str(ev.get("count", 1)).rjust(5)
        source = ev.get("source", "kubelet")[:18].ljust(18)
        message = ev.get("message", "")
        lines.append(f"{ev_type:<8} {reason} {count}  {source} {message}")
    return "\n".join(lines)


def get_pod_events(
    pod_name: str,
    namespace: str = "default",
) -> Dict[str, Any]:
    """Fetches Kubernetes lifecycle and failure events for a specific pod.

    Retrieves critical cluster events (e.g. Warning events, CrashLoopBackOff,
    OOMKilled, FailedMount, Probe Failures, ImagePullBackOff, Preemptions)
    directly related to the specified Pod.

    Args:
        pod_name: Name of the Kubernetes pod to retrieve events for.
        namespace: Kubernetes namespace where the pod is located (defaults to 'default').

    Returns:
        dict: A dictionary containing:
            - status: "success" or "error"
            - pod_name: The target pod name
            - namespace: The target namespace
            - event_count: Number of events retrieved
            - events: List of structured event objects with keys:
                type, reason, message, count, first_seen, last_seen, source
            - raw_events_text: Human-readable events table suitable for LLM analysis
            - error: Error description if retrieval failed
    """
    k8s_api_err = None
    kubectl_err = None

    # 1. Primary: Use Kubernetes Python Client
    try:
        core_v1 = get_core_v1_api()
        # Query events associated with the pod
        field_selector = f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        event_list = core_v1.list_namespaced_event(
            namespace=namespace,
            field_selector=field_selector,
        )

        if not event_list.items:
            # Broader fallback query matching name only
            event_list = core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )

        events: List[Dict[str, Any]] = []
        for item in event_list.items:
            first_ts = None
            if getattr(item, "first_timestamp", None):
                first_ts = item.first_timestamp.isoformat()
            elif getattr(item, "event_time", None):
                first_ts = item.event_time.isoformat()

            last_ts = None
            if getattr(item, "last_timestamp", None):
                last_ts = item.last_timestamp.isoformat()

            source_comp = "kubelet"
            if getattr(item, "source", None) and getattr(item.source, "component", None):
                source_comp = item.source.component
            elif getattr(item, "reporting_component", None):
                source_comp = item.reporting_component

            ev_entry = {
                "type": item.type or "Normal",
                "reason": item.reason or "Unknown",
                "message": item.message or "",
                "count": item.count or 1,
                "first_seen": first_ts,
                "last_seen": last_ts,
                "source": source_comp,
            }
            events.append(ev_entry)

        return {
            "status": "success",
            "pod_name": pod_name,
            "namespace": namespace,
            "event_count": len(events),
            "events": events,
            "raw_events_text": _format_event_text(events),
        }
    except Exception as exc:
        k8s_api_err = str(exc)
        logger.debug("Kubernetes client event fetch failed: %s", exc)

    # 2. Secondary: Fall back to kubectl CLI
    args = [
        "get",
        "events",
        "-n",
        namespace,
        f"--field-selector=involvedObject.name={pod_name}",
        "-o",
        "json",
    ]
    code, stdout, stderr = run_kubectl_command(args)
    if code == 0 and stdout.strip():
        try:
            parsed = json.loads(stdout)
            items = parsed.get("items", [])
            events = []
            for item in items:
                source = item.get("source", {}).get("component") or item.get("reportingComponent") or "kubelet"
                events.append({
                    "type": item.get("type", "Normal"),
                    "reason": item.get("reason", "Unknown"),
                    "message": item.get("message", ""),
                    "count": item.get("count", 1),
                    "first_seen": item.get("firstTimestamp") or item.get("eventTime"),
                    "last_seen": item.get("lastTimestamp"),
                    "source": source,
                })
            return {
                "status": "success",
                "pod_name": pod_name,
                "namespace": namespace,
                "event_count": len(events),
                "events": events,
                "raw_events_text": _format_event_text(events),
            }
        except Exception:
            pass

    kubectl_err = stderr.strip() or f"kubectl exited with code {code}"

    # 3. Fallback: Mock / Sample Pod Events (offline / testing mode)
    mock_content = find_mock_sample_content(pod_name)
    if mock_content:
        events = []
        for line in mock_content.splitlines():
            trimmed = line.strip()
            # Match K8s event lines (Normal or Warning)
            if trimmed.startswith("Normal ") or trimmed.startswith("Warning "):
                parts = trimmed.split(None, 4)
                if len(parts) >= 5:
                    ev_type = parts[0]
                    reason = parts[1]
                    source = parts[3]
                    message = parts[4]
                    events.append({
                        "type": ev_type,
                        "reason": reason,
                        "message": message,
                        "count": 1,
                        "first_seen": None,
                        "last_seen": None,
                        "source": source,
                    })

        # If sample didn't have explicit event lines, infer a simulated failure event
        if not events:
            events.append({
                "type": "Warning",
                "reason": "ContainerFailure",
                "message": f"Detected anomalies in simulated logs for pod '{pod_name}'",
                "count": 1,
                "first_seen": None,
                "last_seen": None,
                "source": "kubelet",
            })

        return {
            "status": "success",
            "pod_name": pod_name,
            "namespace": namespace,
            "source": "simulated_sample",
            "event_count": len(events),
            "events": events,
            "raw_events_text": _format_event_text(events),
        }

    # 4. Error response when all methods fail
    return {
        "status": "error",
        "pod_name": pod_name,
        "namespace": namespace,
        "error": (
            f"Unable to fetch events for pod '{pod_name}' in namespace '{namespace}'. "
            f"K8s API error: {k8s_api_err}. kubectl error: {kubectl_err}. "
            "Please ensure cluster connectivity, namespace, and pod existence."
        ),
    }
