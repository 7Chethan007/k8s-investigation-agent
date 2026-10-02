"""Diagnostic rules and pattern detectors for Kubernetes failures."""

import re
from typing import List, NamedTuple, Pattern
from k8s_agent.models import IncidentCategory, Severity


class DiagnosticRule(NamedTuple):
    name: str
    category: IncidentCategory
    severity: Severity
    patterns: List[Pattern]
    explanation: str
    confidence: float


# Catalog of Kubernetes failure pattern rules
RULES: List[DiagnosticRule] = [
    # 1. Out Of Memory (OOM)
    DiagnosticRule(
        name="OOM_EXIT_CODE_137",
        category=IncidentCategory.OOM_KILLED,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"exit code[:\s]+137\b", re.IGNORECASE),
            re.compile(r"terminated with exit code 137", re.IGNORECASE),
            re.compile(r"OOMKilled:\s*true", re.IGNORECASE),
            re.compile(r"state:\s*terminated,\s*reason:\s*OOMKilled", re.IGNORECASE),
        ],
        explanation="Container was killed by Kubernetes kernel/cgroup killer due to exceeding memory limits (Exit code 137).",
        confidence=0.98,
    ),
    DiagnosticRule(
        name="OOM_KERNEL_CGROUP",
        category=IncidentCategory.OOM_KILLED,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"Out of memory:\s*Kill process", re.IGNORECASE),
            re.compile(r"memory cgroup out of memory", re.IGNORECASE),
            re.compile(r"invoked oom-killer:", re.IGNORECASE),
        ],
        explanation="Linux kernel OOM-killer was invoked after the container exceeded its allocated cgroup memory quota.",
        confidence=0.98,
    ),
    DiagnosticRule(
        name="JVM_HEAP_OOM",
        category=IncidentCategory.OOM_KILLED,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"java\.lang\.OutOfMemoryError:\s*Java heap space", re.IGNORECASE),
            re.compile(r"java\.lang\.OutOfMemoryError:\s*GC overhead limit exceeded", re.IGNORECASE),
            re.compile(r"java\.lang\.OutOfMemoryError:\s*Metaspace", re.IGNORECASE),
        ],
        explanation="JVM application exhausted its configured maximum heap size (-Xmx) or GC overhead limits.",
        confidence=0.95,
    ),

    # 2. CrashLoopBackOff & Application Panic
    DiagnosticRule(
        name="K8S_CRASHLOOP_BACKOFF",
        category=IncidentCategory.CRASH_LOOP_BACKOFF,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"Back-off restarting failed container", re.IGNORECASE),
            re.compile(r"CrashLoopBackOff", re.IGNORECASE),
        ],
        explanation="Kubelet is backing off restarting a failed container that repeatedly exits with error.",
        confidence=0.95,
    ),
    DiagnosticRule(
        name="GO_PANIC",
        category=IncidentCategory.APPLICATION_PANIC,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"panic:\s*runtime error:", re.IGNORECASE),
            re.compile(r"goroutine \d+ \[running\]:", re.IGNORECASE),
        ],
        explanation="Go binary crashed due to an unhandled runtime panic (e.g., nil pointer dereference or slice bounds out of range).",
        confidence=0.92,
    ),
    DiagnosticRule(
        name="PYTHON_UNCAUGHT_EXCEPTION",
        category=IncidentCategory.APPLICATION_PANIC,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
            re.compile(r"ModuleNotFoundError:\s*No module named", re.IGNORECASE),
        ],
        explanation="Python process crashed due to an unhandled exception or missing imported module at runtime.",
        confidence=0.90,
    ),
    DiagnosticRule(
        name="NODEJS_UNHANDLED_EXCEPTION",
        category=IncidentCategory.APPLICATION_PANIC,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"UnhandledPromiseRejection:", re.IGNORECASE),
            re.compile(r"FATAL ERROR:\s*CALL_AND_RETRY_LAST Allocation failed", re.IGNORECASE),
        ],
        explanation="Node.js runtime crashed due to an unhandled promise rejection or V8 memory allocation failure.",
        confidence=0.90,
    ),

    # 3. Probe Failures
    DiagnosticRule(
        name="LIVENESS_PROBE_FAILED",
        category=IncidentCategory.LIVENESS_PROBE_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"Liveness probe failed:\s*HTTP probe failed with statuscode:\s*5\d\d", re.IGNORECASE),
            re.compile(r"Liveness probe failed:\s*connection refused", re.IGNORECASE),
            re.compile(r"Liveness probe failed:\s*command.*timed out", re.IGNORECASE),
            re.compile(r"Container.*failed liveness probe", re.IGNORECASE),
        ],
        explanation="Container liveness probe failed repeatedly, causing Kubelet to kill and restart the container.",
        confidence=0.95,
    ),
    DiagnosticRule(
        name="READINESS_PROBE_FAILED",
        category=IncidentCategory.READINESS_PROBE_FAILURE,
        severity=Severity.MEDIUM,
        patterns=[
            re.compile(r"Readiness probe failed:\s*HTTP probe failed with statuscode:\s*5\d\d", re.IGNORECASE),
            re.compile(r"Readiness probe failed:\s*connection refused", re.IGNORECASE),
            re.compile(r"Container.*failed readiness probe", re.IGNORECASE),
        ],
        explanation="Container readiness probe failed, causing Kubernetes to detach the Pod from Service endpoints.",
        confidence=0.92,
    ),
    DiagnosticRule(
        name="STARTUP_PROBE_FAILED",
        category=IncidentCategory.STARTUP_PROBE_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"Startup probe failed:", re.IGNORECASE),
            re.compile(r"Container.*failed startup probe", re.IGNORECASE),
        ],
        explanation="Container exceeded failureThreshold on its startup probe before initializing, triggering termination.",
        confidence=0.95,
    ),

    # 4. Image Pull Failures
    DiagnosticRule(
        name="IMAGE_PULL_FAILURE",
        category=IncidentCategory.IMAGE_PULL_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"ErrImagePull\b", re.IGNORECASE),
            re.compile(r"ImagePullBackOff\b", re.IGNORECASE),
            re.compile(r"manifest unknown", re.IGNORECASE),
            re.compile(r"unauthorized:\s*authentication required", re.IGNORECASE),
            re.compile(r"failed to resolve reference", re.IGNORECASE),
        ],
        explanation="Kubelet failed to pull the requested container image due to invalid tag or missing registry credentials.",
        confidence=0.96,
    ),

    # 5. DNS & Network Failures
    DiagnosticRule(
        name="DNS_RESOLUTION_FAILURE",
        category=IncidentCategory.DNS_RESOLUTION_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"lookup.*no such host", re.IGNORECASE),
            re.compile(r"dial tcp:\s*lookup.*i/o timeout", re.IGNORECASE),
            re.compile(r"Name or service not known", re.IGNORECASE),
            re.compile(r"Could not resolve host:", re.IGNORECASE),
            re.compile(r"getaddrinfo ENOTFOUND", re.IGNORECASE),
            re.compile(r"getaddrinfo EAI_AGAIN", re.IGNORECASE),
        ],
        explanation="Container cannot resolve hostnames, indicating CoreDNS pod unavailability, DNS throttling, or incorrect service FQDN.",
        confidence=0.92,
    ),
    DiagnosticRule(
        name="NETWORK_CONNECTIVITY_FAILURE",
        category=IncidentCategory.NETWORK_CONNECTIVITY_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"connect:\s*connection refused", re.IGNORECASE),
            re.compile(r"connection reset by peer", re.IGNORECASE),
            re.compile(r"i/o timeout", re.IGNORECASE),
            re.compile(r"Client\.Timeout exceeded while awaiting headers", re.IGNORECASE),
            re.compile(r"upstream connect error or disconnect/reset before headers", re.IGNORECASE),
        ],
        explanation="Network requests failed due to remote target unreachable, network policy isolation, or socket connection reset.",
        confidence=0.88,
    ),

    # 6. Database Exhaustion
    DiagnosticRule(
        name="DATABASE_CONNECTION_EXHAUSTION",
        category=IncidentCategory.DATABASE_EXHAUSTION,
        severity=Severity.CRITICAL,
        patterns=[
            re.compile(r"remaining connection slots are reserved for non-replication superuser connections", re.IGNORECASE),
            re.compile(r"too many connections\b", re.IGNORECASE),
            re.compile(r"Connection pool exhausted", re.IGNORECASE),
            re.compile(r"Timeout waiting for idle object in pool", re.IGNORECASE),
            re.compile(r"Deadlock found when trying to get lock", re.IGNORECASE),
        ],
        explanation="Database connection pool is exhausted or database maximum client connections limit was hit.",
        confidence=0.94,
    ),

    # 7. Storage / PVC Failures
    DiagnosticRule(
        name="STORAGE_MOUNT_FAILURE",
        category=IncidentCategory.STORAGE_MOUNT_FAILURE,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"FailedMount\b", re.IGNORECASE),
            re.compile(r"VolumeBindingFailed\b", re.IGNORECASE),
            re.compile(r"Read-only file system", re.IGNORECASE),
            re.compile(r"failed to attach volume", re.IGNORECASE),
        ],
        explanation="Kubelet failed to mount persistent volume due to volume claim binding failure, cloud provider attach timeout, or read-only restriction.",
        confidence=0.92,
    ),

    # 8. RBAC / Permission Denied
    DiagnosticRule(
        name="RBAC_PERMISSION_DENIED",
        category=IncidentCategory.RBAC_PERMISSION_DENIED,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r'is forbidden:\s*User "system:serviceaccount:[^"]+" cannot', re.IGNORECASE),
            re.compile(r"HTTP status 403 Forbidden", re.IGNORECASE),
            re.compile(r"status code 403", re.IGNORECASE),
        ],
        explanation="Kubernetes API server rejected the request due to missing RBAC Role/ClusterRole permissions on the Pod's ServiceAccount.",
        confidence=0.95,
    ),

    # 9. Missing ConfigMap / Secret
    DiagnosticRule(
        name="CONFIG_SECRET_MISSING",
        category=IncidentCategory.CONFIG_SECRET_MISSING,
        severity=Severity.HIGH,
        patterns=[
            re.compile(r"CreateContainerConfigError\b", re.IGNORECASE),
            re.compile(r'secret "[^"]+" not found', re.IGNORECASE),
            re.compile(r'configmap "[^"]+" not found', re.IGNORECASE),
            re.compile(r"Missing required environment variable", re.IGNORECASE),
            re.compile(r"KeyError:\s*['\"][A-Z0-9_]+_KEY['\"]", re.IGNORECASE),
        ],
        explanation="Pod cannot start because a referenced Secret or ConfigMap does not exist in the namespace, or an essential environment variable is missing.",
        confidence=0.94,
    ),
]


class AnomalyMatch(NamedTuple):
    rule: DiagnosticRule
    line_number: int
    matched_text: str
    pattern_string: str
