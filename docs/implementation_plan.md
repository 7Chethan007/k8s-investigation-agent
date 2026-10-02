# Kubernetes Investigation Agent in Python

Design and implementation plan for a lightweight, modular Kubernetes log investigation agent in Python. The agent ingests Kubernetes logs (pod logs, container stdout/stderr, events), performs automated diagnostic investigation, isolates root causes with verbatim supporting evidence, and produces comprehensive reports (Markdown / JSON).

## User Review Required

> [!IMPORTANT]
> The agent is designed with a **hybrid architecture**:
> 1. **Built-in Diagnostic & Evidence Engine**: High-speed, deterministic root-cause analyzer that requires no external API keys or network calls. It parses Kubernetes log formats, detects patterns (OOMKilled, CrashLoopBackOff, probe timeouts, DNS/network partitions, DB pool exhaustion, missing configs, app stack traces), builds an incident timeline, and extracts verbatim log evidence with line numbers.
> 2. **Optional LLM Reasoning Layer**: If `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` is present in the environment (or passed via CLI flag), the agent can optionally invoke the LLM to provide deeper natural language synthesis, incident triage narratives, and contextual runbook steps.
>
> Please confirm if this hybrid approach (runs standalone offline, with optional LLM augmentation) fits your expectations.

## Proposed Architecture

```
                 Kubernetes Logs
           (file, stdin pipe, raw text)
                        │
                        ▼
            ┌──────────────────────┐
            │      Log Parser      │ (Timestamps, log levels, k8s components,
            └──────────┬───────────┘  JSON logs, multi-line traces)
                       │
                       ▼
            ┌──────────────────────┐
            │ Diagnostic Detectors │ (OOMKilled, CrashLoop, Probe Failures,
            └──────────┬───────────┘  DNS/Network, Auth/RBAC, DB issues, etc.)
                       │
                       ▼
            ┌──────────────────────┐
            │  Timeline & Evidence │ (Correlates log lines, isolates trigger
            │      Correlator      │  events, attaches exact log lines & line numbers)
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │ Investigation Engine │ (Deduces root cause, blast radius,
            └──────────┬───────────┘  confidence level, and remediation)
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
┌──────────────┐              ┌─────────────────┐
│ LLM Reasoner │ (Optional)   │ Built-in Expert │ (Default)
└──────┬───────┘              └────────┬────────┘
       │                               │
       └───────────────┬───────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   Report Generator   │ (Terminal Markdown & JSON format)
            └──────────────────────┘
```

## Proposed Changes

### `k8s-investigation-agent` Package

#### [NEW] [requirements.txt](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/requirements.txt)
Dependencies: `click`, `pydantic`, `rich` (for terminal formatting), `pytest` (for tests). Optional: `google-genai` / `anthropic`.

#### [NEW] [pyproject.toml](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/pyproject.toml)
Project metadata and CLI entrypoint `k8s-investigate = k8s_agent.cli:main`.

#### [NEW] [k8s_agent/models.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/models.py)
Pydantic data models:
- `LogEntry`: parsed timestamp, log level, message, raw line, line number, container/pod metadata.
- `EvidenceItem`: log line, line number, timestamp, matched rule/signature, context lines.
- `RootCause`: category, severity, confidence score, description.
- `Remediation`: immediate action, prevention recommendations, kubectl/manifest remediation commands.
- `InvestigationReport`: incident summary, timeline, root cause, supporting evidence, recommendations.

#### [NEW] [k8s_agent/parser.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/parser.py)
Multi-format log parser supporting:
- Standard container logs (RFC3339 timestamps + stdout/stderr stream).
- Structured JSON logs.
- Plain application stack traces (Python, Java, Go, Node.js).
- Kubernetes event dump formats (`kubectl get events` or `kubectl describe`).

#### [NEW] [k8s_agent/detectors.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/detectors.py)
Rule-based heuristic signatures for:
- `OOM_KILLED`: exit code 137, "Out of memory: Kill process", "cgroup out of memory: kill process".
- `CRASH_LOOP`: exit code 1, 2, 255, uncaught runtime panic/exception.
- `PROBE_FAILURE`: liveness/readiness/startup probe timeout or connection refused.
- `DNS_NETWORK_FAILURE`: dial tcp, i/o timeout, could not resolve host, CoreDNS upstream error.
- `IMAGE_PULL_FAILURE`: ErrImagePull, ImagePullBackOff, manifest unknown, unauthorized.
- `STORAGE_FAILURE`: FailedMount, VolumeBindingFailed, permission denied on volume mount.
- `DATABASE_EXHAUSTION`: pool full, connection limit exceeded, deadlocks.
- `RBAC_DENIED`: 403 Forbidden from `system:serviceaccount` to Kubernetes API.

#### [NEW] [k8s_agent/engine.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/engine.py)
Core investigator:
- Runs parsers and detectors.
- Constructs incident timeline leading up to failure.
- Computes confidence scores and ranks primary vs contributing root causes.
- Pairs each finding with verbatim supporting evidence (including context lines around failure points).
- Generates specific Kubernetes remediation commands (e.g. updating resource limits, configmaps, probe parameters).

#### [NEW] [k8s_agent/llm.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/llm.py)
Optional LLM augmentation layer that queries Gemini or Anthropic if an API key is available, generating deeper conversational incident summaries while preserving the deterministic evidence.

#### [NEW] [k8s_agent/reporter.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/reporter.py)
Formats the report into:
1. Rich terminal / Markdown report with tables, callout blocks, and exact code quotes for evidence.
2. JSON structure suitable for programmatic consumption.

#### [NEW] [k8s_agent/cli.py](file:///Users/chethanmn/Desktop/Growth/k8s-investigation-agent/k8s_agent/cli.py)
CLI interface:
- `k8s-investigate analyze <log-file-or-pipe>`
- Flags: `--format [markdown|json]`, `--output <file>`, `--use-llm`, `--context-lines <N>`.

### Sample Incident Logs & Tests

#### [NEW] Sample logs in `samples/`:
- `samples/oom_killed.log`: Pod killed by memory cgroup exhaustion.
- `samples/crashloop_db_timeout.log`: Pod failing on database connection pool exhaustion.
- `samples/liveness_probe_timeout.log`: Pod restarted because readiness/liveness health check timed out.
- `samples/dns_lookup_failure.log`: Pod failing to resolve external and in-cluster services.
- `samples/image_pull_backoff.log`: K8s pod event log showing image pull auth failure.

#### [NEW] Unit tests in `tests/`:
- `tests/test_parser.py`: Verify parsing of RFC3339, JSON, and unstructured logs.
- `tests/test_detectors.py`: Verify detection of OOM, probe failures, network issues, and crashloops.
- `tests/test_investigation.py`: End-to-end investigation verification asserting that root cause, evidence quotes, and remediations are accurately identified.

## Verification Plan

### Automated Tests
Run pytest across all components:
```bash
pytest -v tests/
```

### Manual Verification
Run the CLI against real sample logs and verify outputs:
```bash
python3 -m k8s_agent.cli analyze samples/oom_killed.log
python3 -m k8s_agent.cli analyze samples/crashloop_db_timeout.log --format json
cat samples/liveness_probe_timeout.log | python3 -m k8s_agent.cli analyze -
```
Verify that:
1. Primary root causes are accurately isolated.
2. Exact supporting evidence lines with line numbers and timestamps are displayed.
3. Concrete kubectl / manifest remediation instructions are provided.
