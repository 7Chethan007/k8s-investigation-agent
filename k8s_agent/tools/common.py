"""Shared helpers and Kubernetes client resolution for ADK tools."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_core_v1_api() -> Any:
    """Initializes and returns a Kubernetes CoreV1Api instance.

    Attempts in-cluster configuration first (for pods/operators running inside a cluster),
    then falls back to local kubeconfig (~/.kube/config).
    """
    from kubernetes import client, config
    from kubernetes.config.config_exception import ConfigException

    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()

    return client.CoreV1Api()


def get_apps_v1_api() -> Any:
    """Initializes and returns a Kubernetes AppsV1Api instance.

    Attempts in-cluster configuration first (for pods/operators running inside a cluster),
    then falls back to local kubeconfig (~/.kube/config).
    """
    from kubernetes import client, config
    from kubernetes.config.config_exception import ConfigException

    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()

    return client.AppsV1Api()


def run_kubectl_command(args: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    """Executes a kubectl CLI command and returns (returncode, stdout, stderr)."""
    try:
        cmd = ["kubectl"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as exc:
        return 1, "", str(exc)


def find_mock_sample_content(pod_name: str) -> Optional[str]:
    """Retrieves simulated log or event content from samples/ or K8S_MOCK_LOGS_DIR.

    Used when running in offline or test environments without an active cluster.
    """
    search_dirs = []
    env_dir = os.environ.get("K8S_MOCK_LOGS_DIR")
    if env_dir:
        search_dirs.append(Path(env_dir))

    # Project samples directory
    project_samples = Path(__file__).resolve().parent.parent.parent / "samples"
    if project_samples.is_dir():
        search_dirs.append(project_samples)

    cleaned_name = pod_name.lower().replace("-", "_")

    for directory in search_dirs:
        if not directory.is_dir():
            continue

        # Exact match
        for candidate in [directory / f"{pod_name}.log", directory / f"{cleaned_name}.log"]:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")

        # Fuzzy match across .log files
        for file in directory.glob("*.log"):
            stem = file.stem.lower()
            if stem in cleaned_name or cleaned_name in stem:
                return file.read_text(encoding="utf-8", errors="replace")

    return None
