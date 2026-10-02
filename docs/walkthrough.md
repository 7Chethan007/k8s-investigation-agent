# Kubernetes Investigation Agent Walkthrough

We have built an enterprise-grade Kubernetes Log Investigation Agent in Python that ingests container and cluster logs, deterministically diagnoses incidents, isolates verbatim log evidence with surrounding context windows, constructs chronological timelines, and provides actionable remediation commands and manifest patches.

## Key Capabilities Implemented

1. **Multi-Format Ingestion**:
   - CRI-O / containerd runtime timestamp formats (`stdout F`, `stderr F`).
   - Structured JSON logs (zap, bunyan, winston, python-json-logger).
   - Kubernetes event streams (`kubectl describe pod` / `kubectl get events`).
   - Uncaught multi-line application stack traces (Python, Go, Java JVM, Node.js).
2. **Diagnostic Knowledge Base & Detectors**:
   - `OOM_KILLED`: Exit code 137, cgroup limit violations, kernel OOM-killer, JVM heap space exhaustion.
   - `CRASH_LOOP_BACKOFF`: Repeated container exits and backoff states.
   - `APPLICATION_PANIC`: Unhandled Go panics, Python ModuleNotFoundError/Tracebacks, Node unhandled rejections.
   - `LIVENESS_PROBE_FAILURE` & `READINESS_PROBE_FAILURE`: HTTP 5xx errors, timeouts, connection refused.
   - `DNS_RESOLUTION_FAILURE`: CoreDNS timeouts, `lookup ... no such host`, `getaddrinfo` errors.
   - `NETWORK_CONNECTIVITY_FAILURE`: Connection resets, broken pipes, dial timeouts.
   - `IMAGE_PULL_FAILURE`: `ErrImagePull`, `ImagePullBackOff`, registry 401/403 authentication failures.
   - `STORAGE_MOUNT_FAILURE`: `FailedMount`, `VolumeBindingFailed`, read-only filesystem errors.
   - `RBAC_PERMISSION_DENIED`: Kubernetes API 403 Forbidden for Pod ServiceAccounts.
   - `DATABASE_EXHAUSTION`: Connection pool starvation, superuser reserved slots, deadlocks.
3. **Verbatim Evidence Extraction**:
   - Pinpoints exact line numbers and timestamps.
   - Captures contextual lines before and after the trigger line with `<-- [TRIGGER]` annotation.
   - Assigns rule explanations and confidence scores.
4. **Lifecycle Timeline Reconstruction**:
   - Tracks incident phases: `STARTUP` -> `DEGRADATION` -> `CRASH_EVENT` / `FAILURE` -> `BACKOFF`.
5. **Actionable Remediation Engine**:
   - Immediate triage commands (`kubectl describe`, `kubectl top`, `kubectl logs --previous`).
   - Tactical patches (`kubectl patch deployment ...`).
   - Production preventative recommendations and ready-to-apply YAML manifest snippets.
6. **Optional LLM Synthesis**:
   - Plug-and-play support for Google Gemini, Anthropic Claude, and OpenAI when environment keys are set (`GEMINI_API_KEY`, etc.), operating 100% offline and deterministic by default.
7. **CI/CD Integration**:
   - `--format json` for alert managers or pipelines.
   - `--fail-on-critical` returns exit code 2 when critical root causes are detected.

---

## Verification & Test Results

### 1. Test Suite & Coverage

Ran 25 unit and end-to-end integration tests using `pytest` and `pytest-cov`:

```
============================== 25 passed in 0.84s ==============================

Name                     Stmts   Miss  Cover
--------------------------------------------
k8s_agent/__init__.py        6      0   100%
k8s_agent/cli.py            61      7    89%
k8s_agent/detectors.py      16      0   100%
k8s_agent/engine.py        117      8    93%
k8s_agent/llm.py            52     14    73%
k8s_agent/models.py         73      0   100%
k8s_agent/parser.py         59      2    97%
k8s_agent/reporter.py       96      9    91%
k8s_agent/timeline.py       35      1    97%
--------------------------------------------
TOTAL                      515     41    92%
```

### 2. Sample Incident Investigations Verified

| Sample Incident Log | Primary Root Cause Detected | Severity | Confidence | Evidence Captured |
|---|---|---|---|---|
| `samples/oom_killed.log` | `OOM_KILLED` | 🔴 CRITICAL | 98.0% | Exit code 137, kernel OOM-killer lines with context |
| `samples/crashloop_db_exhaustion.log` | `DATABASE_EXHAUSTION` | 🔴 CRITICAL | 94.0% | Connection pool exhausted, PostgreSQL superuser slots |
| `samples/liveness_probe_failure.log` | `LIVENESS_PROBE_FAILURE` | 🟠 HIGH | 95.0% | HTTP 500 probe failures and container kill events |
| `samples/dns_resolution_failure.log` | `DNS_RESOLUTION_FAILURE` | 🟠 HIGH | 92.0% | Dial tcp lookup timeout & no such host |
| `samples/image_pull_backoff.log` | `IMAGE_PULL_FAILURE` | 🟠 HIGH | 96.0% | `ErrImagePull`, `ImagePullBackOff`, unauthorized token |
| `samples/rbac_forbidden.log` | `RBAC_PERMISSION_DENIED` | 🟠 HIGH | 95.0% | HTTP 403 Forbidden on secret creation for serviceaccount |

### 3. CLI Execution Example

```bash
# Analyze OOM crash log with terminal rendering
k8s-investigate analyze samples/oom_killed.log

# Stream directly from kubectl and output JSON
kubectl logs my-pod --previous | k8s-investigate analyze - --format json

# Enforce CI/CD pipeline gate
k8s-investigate analyze samples/oom_killed.log --fail-on-critical
# (Exited with code 2)
```
