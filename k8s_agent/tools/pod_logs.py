"""ADK tool for fetching Kubernetes pod logs."""

import logging
from typing import Any, Dict, Optional

from k8s_agent.tools.common import (
    find_mock_sample_content,
    get_core_v1_api,
    run_kubectl_command,
)

logger = logging.getLogger(__name__)


def get_pod_logs(
    pod_name: str,
    namespace: str = "default",
    container: Optional[str] = None,
    tail_lines: Optional[int] = 500,
    previous: bool = False,
) -> Dict[str, Any]:
    """Fetches the logs of a specific Kubernetes pod from the cluster.

    Args:
        pod_name: Name of the Kubernetes pod to retrieve logs from.
        namespace: Kubernetes namespace where the pod is running (defaults to 'default').
        container: Name of the specific container (optional, for multi-container pods).
        tail_lines: Number of most recent log lines to retrieve (defaults to 500).
        previous: If True, retrieve logs for the previous instance of the container (e.g. after restart/crash).

    Returns:
        dict: A dictionary containing:
            - status: "success" or "error"
            - pod_name: The target pod name
            - namespace: The target namespace
            - container: The container name if specified
            - tail_lines: Number of lines requested
            - previous: Boolean indicating if previous instance logs were requested
            - log_lines_count: Number of lines in the retrieved logs
            - logs: The raw log text string (if success)
            - error: Detailed error message (if error)
    """
    tail = int(tail_lines) if tail_lines is not None else 500
    prev = bool(previous)
    k8s_api_err = None
    kubectl_err = None

    # 1. Primary: Use Kubernetes Python Client
    try:
        core_v1 = get_core_v1_api()
        kwargs: Dict[str, Any] = {
            "name": pod_name,
            "namespace": namespace,
            "tail_lines": tail,
            "previous": prev,
        }
        if container:
            kwargs["container"] = container

        raw_logs = core_v1.read_namespaced_pod_log(**kwargs)
        if isinstance(raw_logs, bytes):
            raw_logs = raw_logs.decode("utf-8", errors="replace")

        lines = raw_logs.splitlines()
        return {
            "status": "success",
            "pod_name": pod_name,
            "namespace": namespace,
            "container": container,
            "tail_lines": tail,
            "previous": prev,
            "log_lines_count": len(lines),
            "logs": raw_logs,
        }
    except Exception as exc:
        k8s_api_err = str(exc)
        logger.debug("Kubernetes client log fetch failed: %s", exc)

    # 2. Secondary: Fall back to kubectl CLI
    args = ["logs", pod_name, "-n", namespace, f"--tail={tail}"]
    if container:
        args.extend(["-c", container])
    if prev:
        args.append("--previous")

    code, stdout, stderr = run_kubectl_command(args)
    if code == 0 and stdout.strip():
        lines = stdout.splitlines()
        return {
            "status": "success",
            "pod_name": pod_name,
            "namespace": namespace,
            "container": container,
            "tail_lines": tail,
            "previous": prev,
            "log_lines_count": len(lines),
            "logs": stdout,
        }
    kubectl_err = stderr.strip() or f"kubectl exited with code {code}"

    # 3. Fallback: Mock / Sample Pod Logs (offline / testing mode)
    mock_logs = find_mock_sample_content(pod_name)
    if mock_logs:
        lines = mock_logs.splitlines()
        if tail and len(lines) > tail:
            mock_logs = "\n".join(lines[-tail:])
            lines = mock_logs.splitlines()
        return {
            "status": "success",
            "pod_name": pod_name,
            "namespace": namespace,
            "container": container,
            "tail_lines": tail,
            "previous": prev,
            "source": "simulated_sample",
            "log_lines_count": len(lines),
            "logs": mock_logs,
        }

    # 4. Error response when all methods fail
    return {
        "status": "error",
        "pod_name": pod_name,
        "namespace": namespace,
        "container": container,
        "error": (
            f"Unable to fetch logs for pod '{pod_name}' in namespace '{namespace}'. "
            f"K8s API error: {k8s_api_err}. kubectl error: {kubectl_err}. "
            "Please ensure the cluster is accessible, kubeconfig is valid, and the pod exists."
        ),
    }
