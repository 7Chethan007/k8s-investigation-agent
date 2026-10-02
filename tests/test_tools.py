"""Unit tests for ADK tools (get_pod_logs, get_pod_events, get_deployment_history, and investigate_kubernetes_logs)."""

import json
from unittest.mock import MagicMock, patch
import pytest

from k8s_agent.agent import root_agent
from k8s_agent.tools import (
    get_deployment_history,
    get_deployment_history_tool,
    get_pod_events,
    get_pod_logs,
    investigate_kubernetes_logs,
)


def test_adk_agent_tools_registered():
    """Verify that get_pod_logs, get_pod_events, get_deployment_history, and investigate_kubernetes_logs are registered."""
    tool_names = [getattr(t, "__name__", str(t)) for t in root_agent.tools]
    assert "get_pod_logs" in tool_names
    assert "get_pod_events" in tool_names
    assert "get_deployment_history" in tool_names
    assert "investigate_kubernetes_logs" in tool_names
    assert "investigate_log_file" not in tool_names


# ============================================================================
# get_pod_logs Tests
# ============================================================================

@patch("kubernetes.config.load_incluster_config")
@patch("kubernetes.config.load_kube_config")
@patch("kubernetes.client.CoreV1Api")
def test_get_pod_logs_via_k8s_client(mock_core_v1, mock_kube_config, mock_incluster):
    """Test retrieving pod logs using the Kubernetes Python client."""
    mock_api_instance = MagicMock()
    mock_api_instance.read_namespaced_pod_log.return_value = (
        "2026-10-02T19:00:10Z [INFO] Service starting\n"
        "2026-10-02T19:00:15Z [ERROR] Out of memory killed\n"
    )
    mock_core_v1.return_value = mock_api_instance

    res = get_pod_logs(
        pod_name="payment-service-abc",
        namespace="prod",
        container="payment-app",
        tail_lines=100,
        previous=False,
    )

    assert res["status"] == "success"
    assert res["pod_name"] == "payment-service-abc"
    assert res["namespace"] == "prod"
    assert res["container"] == "payment-app"
    assert res["log_lines_count"] == 2
    assert "Out of memory killed" in res["logs"]
    mock_api_instance.read_namespaced_pod_log.assert_called_once_with(
        name="payment-service-abc",
        namespace="prod",
        container="payment-app",
        tail_lines=100,
        previous=False,
    )


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_logs_kubectl_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test falling back to kubectl CLI when Kubernetes client throws an exception."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = (
        "2026-10-02T19:00:10Z [INFO] Worker running\n"
        "2026-10-02T19:00:12Z [ERROR] Fatal crash\n"
    )
    mock_subprocess.return_value = mock_proc

    res = get_pod_logs(
        pod_name="worker-pod",
        namespace="staging",
        previous=True,
    )

    assert res["status"] == "success"
    assert res["pod_name"] == "worker-pod"
    assert res["namespace"] == "staging"
    assert res["previous"] is True
    assert "Fatal crash" in res["logs"]
    assert mock_subprocess.called


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_logs_mock_sample_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test falling back to sample logs when both live API and kubectl fail (offline/test mode)."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "error: unable to connect to server"
    mock_subprocess.return_value = mock_proc

    res = get_pod_logs(
        pod_name="oom-killed-pod",
        namespace="default",
    )

    assert res["status"] == "success"
    assert res["source"] == "simulated_sample"
    assert "out of memory" in res["logs"].lower()


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_logs_error_when_nonexistent(mock_subprocess, mock_kube_config, mock_incluster):
    """Test returning error status when pod logs cannot be fetched from any source."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Error from server (NotFound): pods 'ghost-pod-xyz-999' not found"
    mock_subprocess.return_value = mock_proc

    res = get_pod_logs(
        pod_name="ghost-pod-xyz-999",
        namespace="nonexistent-ns",
    )

    assert res["status"] == "error"
    assert "Unable to fetch logs for pod" in res["error"]
    assert res["pod_name"] == "ghost-pod-xyz-999"


# ============================================================================
# get_pod_events Tests
# ============================================================================

@patch("kubernetes.config.load_incluster_config")
@patch("kubernetes.config.load_kube_config")
@patch("kubernetes.client.CoreV1Api")
def test_get_pod_events_via_k8s_client(mock_core_v1, mock_kube_config, mock_incluster):
    """Test retrieving pod events using the Kubernetes client."""
    mock_api = MagicMock()

    mock_event1 = MagicMock()
    mock_event1.type = "Normal"
    mock_event1.reason = "Scheduled"
    mock_event1.message = "Successfully assigned default/my-pod to node-1"
    mock_event1.count = 1
    mock_event1.first_timestamp = None
    mock_event1.event_time = None
    mock_event1.last_timestamp = None
    mock_event1.source.component = "default-scheduler"

    mock_event2 = MagicMock()
    mock_event2.type = "Warning"
    mock_event2.reason = "BackOff"
    mock_event2.message = "Back-off restarting failed container"
    mock_event2.count = 5
    mock_event2.first_timestamp = None
    mock_event2.event_time = None
    mock_event2.last_timestamp = None
    mock_event2.source.component = "kubelet"

    mock_event_list = MagicMock()
    mock_event_list.items = [mock_event1, mock_event2]
    mock_api.list_namespaced_event.return_value = mock_event_list
    mock_core_v1.return_value = mock_api

    res = get_pod_events(pod_name="my-pod", namespace="default")

    assert res["status"] == "success"
    assert res["pod_name"] == "my-pod"
    assert res["namespace"] == "default"
    assert res["event_count"] == 2
    assert res["events"][0]["reason"] == "Scheduled"
    assert res["events"][1]["reason"] == "BackOff"
    assert "BackOff" in res["raw_events_text"]


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_events_kubectl_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test falling back to kubectl CLI for events."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({
        "items": [
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "MountVolume.SetUp failed for volume data",
                "count": 3,
                "reportingComponent": "kubelet",
            }
        ]
    })
    mock_subprocess.return_value = mock_proc

    res = get_pod_events(pod_name="storage-pod", namespace="prod")

    assert res["status"] == "success"
    assert res["pod_name"] == "storage-pod"
    assert res["event_count"] == 1
    assert res["events"][0]["reason"] == "FailedMount"
    assert "FailedMount" in res["raw_events_text"]


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_events_mock_sample_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test falling back to sample event lines in offline mode."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "error: unable to connect to server"
    mock_subprocess.return_value = mock_proc

    # crashloop_db_exhaustion.log contains "Warning BackOff 5s kubelet ..."
    res = get_pod_events(pod_name="crashloop-db-exhaustion", namespace="default")

    assert res["status"] == "success"
    assert res["source"] == "simulated_sample"
    assert res["event_count"] >= 1
    assert any("BackOff" in ev["reason"] for ev in res["events"])


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_pod_events_error_when_nonexistent(mock_subprocess, mock_kube_config, mock_incluster):
    """Test error handling when events cannot be retrieved from any source."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "No resources found"
    mock_subprocess.return_value = mock_proc

    res = get_pod_events(pod_name="phantom-pod-999", namespace="unknown-ns")

    assert res["status"] == "error"
    assert "Unable to fetch events" in res["error"]


# ============================================================================
# get_deployment_history Tests & ADK Schema Verification
# ============================================================================

def test_get_deployment_history_adk_schema():
    """Verify that get_deployment_history complies with Google ADK FunctionTool declarations and schema."""
    decl = get_deployment_history_tool._get_declaration()
    assert decl.name == "get_deployment_history"
    assert "revisions" in decl.description.lower()
    schema = decl.parameters_json_schema
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "namespace" in schema["properties"]
    assert "max_revisions" in schema["properties"]
    assert "name" in schema["required"]


@patch("kubernetes.config.load_incluster_config")
@patch("kubernetes.config.load_kube_config")
@patch("kubernetes.client.AppsV1Api")
def test_get_deployment_history_via_k8s_client(mock_apps_v1, mock_kube_config, mock_incluster):
    """Test retrieving deployment history and detecting container image tag changes."""
    mock_apps = MagicMock()

    mock_dep = MagicMock()
    mock_dep.status.replicas = 3
    mock_dep.status.ready_replicas = 3
    mock_dep.status.updated_replicas = 3
    mock_dep.status.available_replicas = 3
    mock_dep.status.observed_generation = 2
    mock_apps.read_namespaced_deployment.return_value = mock_dep

    # RS 1 (old)
    rs1 = MagicMock()
    rs1.metadata.name = "payment-service-old"
    rs1.metadata.owner_references = [MagicMock(kind="Deployment", name="payment-service")]
    rs1.metadata.annotations = {
        "deployment.kubernetes.io/revision": "1",
        "kubernetes.io/change-cause": "Initial release",
    }
    rs1.metadata.creation_timestamp = None
    rs1.spec.replicas = 0
    c1 = MagicMock()
    c1.image = "payment-service:v1.0.0"
    rs1.spec.template.spec.containers = [c1]
    rs1.status.ready_replicas = 0

    # RS 2 (new)
    rs2 = MagicMock()
    rs2.metadata.name = "payment-service-new"
    rs2.metadata.owner_references = [MagicMock(kind="Deployment", name="payment-service")]
    rs2.metadata.annotations = {
        "deployment.kubernetes.io/revision": "2",
        "kubernetes.io/change-cause": "Upgrade to v1.1.0",
    }
    rs2.metadata.creation_timestamp = None
    rs2.spec.replicas = 3
    c2 = MagicMock()
    c2.image = "payment-service:v1.1.0"
    rs2.spec.template.spec.containers = [c2]
    rs2.status.ready_replicas = 3

    rs_list = MagicMock()
    rs_list.items = [rs1, rs2]
    mock_apps.list_namespaced_replica_set.return_value = rs_list
    mock_apps_v1.return_value = mock_apps

    res = get_deployment_history(name="payment-service", namespace="prod")

    assert res["status"] == "success"
    assert res["deployment_name"] == "payment-service"
    assert res["current_revision"] == 2
    assert res["previous_revision"] == 1
    assert len(res["image_changes"]) == 1
    assert res["image_changes"][0]["previous_image"] == "payment-service:v1.0.0"
    assert res["image_changes"][0]["current_image"] == "payment-service:v1.1.0"
    assert "payment-service:v1.1.0" in res["summary"]


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_deployment_history_kubectl_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test fallback to kubectl rollout history CLI."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = (
        "REVISION  CHANGE-CAUSE\n"
        "1         <none>\n"
        "2         Deploy version 2.0.0\n"
    )
    mock_subprocess.return_value = mock_proc

    res = get_deployment_history(name="orders-worker", namespace="staging")

    assert res["status"] == "success"
    assert res["deployment_name"] == "orders-worker"
    assert res["current_revision"] == 2
    assert res["previous_revision"] == 1
    assert len(res["revisions"]) == 2


@patch("kubernetes.config.load_incluster_config", side_effect=RuntimeError("No incluster"))
@patch("kubernetes.config.load_kube_config", side_effect=RuntimeError("No kubeconfig"))
@patch("subprocess.run")
def test_get_deployment_history_simulated_fallback(mock_subprocess, mock_kube_config, mock_incluster):
    """Test fallback to simulated deployment revision in offline testing environment."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "error: dial tcp: connect: connection refused"
    mock_subprocess.return_value = mock_proc

    res = get_deployment_history(name="payment-service-5899c7594d-xyz", namespace="default")

    assert res["status"] == "success"
    assert res["source"] == "simulated_sample"
    assert res["current_revision"] == 2
    assert len(res["image_changes"]) >= 1


# ============================================================================
# investigate_kubernetes_logs Tests
# ============================================================================

def test_investigate_kubernetes_logs_raw_text():
    """Test running automated investigation on raw log text."""
    sample_logs = (
        "2026-10-02T19:00:10.001Z stdout F [INFO] Initializing service\n"
        "2026-10-02T19:00:15.000Z stderr F [FATAL] Memory cgroup out of memory: Killed process 42 (app)\n"
        "Warning  OOMKilled  10s  kubelet  Container app in pod payment-service was killed by OOM Killer\n"
    )

    report_md = investigate_kubernetes_logs(sample_logs)
    assert "# Kubernetes Incident Investigation Report" in report_md
    assert "OOM_KILLED" in report_md
    assert "Remediation" in report_md


def test_investigate_kubernetes_logs_dict_or_json():
    """Test investigate_kubernetes_logs handling dict and stringified JSON payloads from get_pod_logs."""
    sample_dict = {
        "status": "success",
        "pod_name": "db-client",
        "logs": (
            "2026-10-02T19:00:10Z [INFO] Connecting\n"
            "2026-10-02T19:00:20Z [ERROR] connection pool exhausted: remaining connection slots are reserved\n"
        ),
    }

    report_from_dict = investigate_kubernetes_logs(sample_dict)
    assert "DATABASE_EXHAUSTION" in report_from_dict

    report_from_json = investigate_kubernetes_logs(json.dumps(sample_dict))
    assert "DATABASE_EXHAUSTION" in report_from_json
