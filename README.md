# Kubernetes Investigation Agent 🔍

An enterprise-ready Kubernetes log investigation agent built with Python. It ingests container stdout/stderr, CRI-O/containerd streams, JSON structured logs, and Kubernetes events, detects anomalies across failure domains, and synthesizes root-cause analysis backed by verbatim log evidence and prescriptive remediation runbooks.

---

## ⚡ Features

- **Multi-Format Ingestion**: Supports raw container logs, CRI-O / containerd timestamps, JSON logs (zap, bunyan, winston), multi-line stack traces (Go, Python, Java, Node.js), and Kubernetes event streams (`kubectl describe`).
- **Comprehensive Failure Domain Detection**:
  - `OOM_KILLED`: Exit code 137, cgroup limits, Linux kernel OOM killer, JVM heap exhaustion.
  - `CRASH_LOOP_BACKOFF`: Process exit codes, uncaught exceptions, and panics.
  - `PROBE_FAILURES`: Liveness, readiness, and startup probe timeouts and HTTP 5xx errors.
  - `NETWORK_DNS_FAILURES`: CoreDNS throttling, lookup timeouts, upstream connection reset, broken pipes.
  - `STORAGE_FAILURES`: `FailedMount`, `VolumeBindingFailed`, read-only filesystems.
  - `RBAC_DENIED`: 403 Forbidden errors for ServiceAccounts querying the Kubernetes API.
  - `DATABASE_EXHAUSTION`: Connection pool starvation, max clients reached, lock timeouts.
  - `CONFIG_SECRET_MISSING`: `CreateContainerConfigError`, missing secrets/configmaps.
- **Verbatim Evidence Extraction**: Automatically isolates trigger lines, line numbers, timestamps, and configurable context windows (lines before and after).
- **Incident Timeline Reconstruction**: Sequences lifecycle milestones (Startup -> Degradation -> Failure Trigger -> Crash -> Backoff).
- **Prescriptive Remediation**: Generates immediate tactical commands (`kubectl patch`, `kubectl describe`, etc.), long-term architectural prevention measures, and YAML manifest patches.
- **Zero-Token by Default**: The `analyze` and `live` CLI commands never call an LLM unless you explicitly pass `--use-llm` (and have an API key configured). `--no-llm` is a hard override that always wins. See [Zero-Token Architecture](#-zero-token-architecture).
- **Optional LLM Synthesis**: Seamlessly integrates with Google Gemini, Anthropic Claude, or OpenAI if API keys are set and `--use-llm` is passed.
- **CI/CD & Alert Automation Ready**: Supports JSON output mode (`--format json`) and automated gate enforcement with `--fail-on-critical` (returns exit code 2 on critical incidents).

---

## 🚀 Installation

```bash
git clone https://github.com/your-org/k8s-investigation-agent.git
cd k8s-investigation-agent

# Install dependencies and CLI tool in editable mode
pip install -e .
```

---

## 💻 CLI Usage

### 1. Analyze a log file

```bash
k8s-investigate analyze samples/oom_killed.log
```

### 2. Stream logs directly from `kubectl` via pipe

```bash
kubectl logs deployment/payment-service -n prod --previous | k8s-investigate analyze -
```

### 3. Generate structured JSON for automation or alerting

```bash
k8s-investigate analyze samples/crashloop_db_exhaustion.log --format json -o incident-report.json
```

### 4. Investigate a live pod directly from the cluster (also zero-token)

Fetches logs, events, and deployment rollout history in a fixed sequence — no LLM, no agent loop — then runs the same regex-based root-cause engine:

```bash
k8s-investigate live payment-service-7f8d9 -n prod
```

### 5. CI/CD Gate Enforcement (`--fail-on-critical`)

Returns exit code `2` if a `CRITICAL` severity incident is discovered (e.g. OOMKilled or CrashLoopBackOff), causing pipeline checks to halt:

```bash
k8s-investigate analyze logs/canary.log --fail-on-critical
```

### 6. Optional LLM Post-Mortem Augmentation (opt-in only)

Off by default on every command. Requires both an API key **and** `--use-llm`:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
k8s-investigate analyze samples/oom_killed.log --use-llm
k8s-investigate live payment-service-7f8d9 -n prod --use-llm
```

`--no-llm` always hard-disables it, regardless of any key or default.

---

## 🪙 Zero-Token Architecture

This agent is deterministic by design and only ever spends LLM tokens if you explicitly ask it to:

| Entrypoint | Token cost | How it decides what to do |
|---|---|---|
| `k8s-investigate analyze <file\|->` | **Zero** (unless `--use-llm`) | Fixed pipeline: parser → detectors → engine → reporter |
| `k8s-investigate live <pod>` | **Zero** (unless `--use-llm`) | Fixed Python sequence: `get_pod_logs` → `get_pod_events` → `get_deployment_history` → engine → reporter |
| ADK `root_agent` (`adk run k8s_agent`, `agents-cli run "..."`) | **Token-consuming** | Gemini decides which tool to call, in what order, how many times |

The regex/rule engine (`detectors.py`, `engine.py`) is the actual product. The ADK agent loop exists for open-ended, natural-language triage ("something's wrong with checkout, figure out why") where the target pod and failure mode aren't known up front — that's the only case where letting an LLM decide the next action is unavoidable. For anything else — a known pod, a known log file — use `analyze`/`live` and pay nothing.

---

## 🧪 Testing

Run the full pytest suite:

```bash
pytest -v tests/
```

---

---

## 🤖 Google ADK Agent & Tools

The repository includes a Google Agent Development Kit (ADK) agent configured for `agents-cli`.

### Modular ADK Diagnostic Tools (`k8s_agent/tools/`)

The repository features modular, enterprise-grade tools conforming to Google ADK specifications:

1. **`get_pod_logs`**: Fetches container stdout/stderr logs from a specific pod (via K8s API, fallback to `kubectl`, or offline mock):
   ```python
   from k8s_agent.tools import get_pod_logs

   logs_res = get_pod_logs(pod_name="payment-service-789", namespace="prod", tail_lines=200)
   ```

2. **`get_pod_events`**: Fetches Kubernetes lifecycle and warning events (e.g. `BackOff`, `OOMKilled`, `FailedMount`, `ProbeFailures`):
   ```python
   from k8s_agent.tools import get_pod_events

   events_res = get_pod_events(pod_name="payment-service-789", namespace="prod")
   ```

3. **`get_deployment_history`**: Analyzes recent rollout revisions and container image changes (via K8s AppsV1 API, fallback to `kubectl rollout history`, or offline mock):
   ```python
   from k8s_agent.tools import get_deployment_history

   history_res = get_deployment_history(name="payment-service-789", namespace="prod")
   ```

4. **`investigate_kubernetes_logs`**: Evaluates logs or events with the automated root-cause engine:
   ```python
   from k8s_agent.tools import investigate_kubernetes_logs

   report = investigate_kubernetes_logs(logs_res["logs"])
   ```

All four tools are plain Python functions — calling them never costs a token. They're used two ways in this repo: directly, in a fixed sequence, by `k8s-investigate live` (zero-token); or as ADK `FunctionTool`s that Gemini can choose to call via `root_agent` (token-consuming, see [Zero-Token Architecture](#-zero-token-architecture)).

### Running with Google agents-cli / ADK

```bash
# Verify project configuration
agents-cli info

# Run agent with a prompt
agents-cli run "Check events and logs for payment-service in prod namespace"
```

---

## 📁 Repository Structure

```
k8s-investigation-agent/
├── agents-cli-manifest.yaml # Google agents-cli project configuration
├── k8s_agent/
│   ├── __init__.py          # Package exports
│   ├── agent.py             # ADK Root Agent definition
│   ├── tools/               # Modular ADK tools package
│   │   ├── __init__.py      # Tool exports
│   │   ├── common.py        # Shared K8s client & CLI helpers
│   │   ├── pod_logs.py      # get_pod_logs implementation
│   │   ├── pod_events.py    # get_pod_events implementation
│   │   ├── deployment_history.py # get_deployment_history implementation
│   │   └── investigate.py   # investigate_kubernetes_logs implementation
│   ├── models.py            # Pydantic data schemas
│   ├── parser.py            # Multi-format log parser
│   ├── detectors.py         # Diagnostic catalog & pattern rules
│   ├── timeline.py          # Lifecycle timeline sequencer
│   ├── engine.py            # Investigation coordinator
│   ├── reporter.py          # Terminal, Markdown, JSON formatters
│   ├── llm.py               # Optional LLM integration
│   └── cli.py               # Click command-line interface
├── samples/                 # Realistic failure scenario logs
│   ├── oom_killed.log
│   ├── crashloop_db_exhaustion.log
│   ├── liveness_probe_failure.log
│   ├── dns_resolution_failure.log
│   ├── image_pull_backoff.log
│   └── rbac_forbidden.log
├── tests/                   # Unit and integration test suite
│   ├── test_cli.py
│   ├── test_detectors.py
│   ├── test_engine.py
│   ├── test_llm.py
│   ├── test_parser.py
│   └── test_tools.py        # ADK tools tests
├── pyproject.toml
├── requirements.txt
└── Dockerfile
```

---

## 📄 License
Apache-2.0
