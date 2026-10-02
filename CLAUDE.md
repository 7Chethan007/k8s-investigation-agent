# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable mode, pulls in click/pydantic/rich/requests)
pip install -e .

# Run full test suite
pytest -v tests/

# Run a single test file / test
pytest -v tests/test_detectors.py
pytest -v tests/test_cli.py::test_cli_analyze_file

# Run the CLI against a sample log (zero-token)
k8s-investigate analyze samples/oom_killed.log
k8s-investigate analyze samples/oom_killed.log --format json
kubectl logs deployment/payment-service -n prod --previous | k8s-investigate analyze -

# Run the CLI against a live pod (zero-token: logs -> events -> deployment history -> regex engine)
k8s-investigate live payment-service-7f8d9 -n prod

# ADK agent loop (the only token-consuming path in this repo — opt in deliberately)
adk run k8s_agent
agents-cli run "investigate payment-service in prod"
```

There is no lint/format config in this repo (no ruff/black/flake8 config present) and no CI workflow — `pytest` is the only gate.

## Zero-Token Rule (governs all new work in this repo)

**Every command and tool in this repo must default to zero LLM tokens.** The regex/rule engine (`detectors.py` + `engine.py`) is the product; an LLM is a garnish, never a dependency.

- `analyze` and `live` default `--use-llm/--no-llm` to **`--no-llm`**. An LLM call only happens if a developer explicitly passes `--use-llm` *and* has an API key configured — both conditions required. `--no-llm` always hard-disables it regardless of any other flag, env var, or future default change; treat it as a kill switch, not just the inverse of `--use-llm`.
- Before adding any new feature, climb the same ladder the existing pipeline already climbs: can a regex in `detectors.py`, a lookup table branch in `engine.py`, or a plain Python helper in `tools/` do it? Only reach for an LLM call when the task is genuinely unavoidable without one (e.g. free-form natural-language narrative synthesis, open-ended "what's wrong with checkout" triage where the target pod/cause isn't known up front) — and even then, keep it opt-in, not default.
- The ADK `root_agent` loop (`agent.py`) is the **only** token-consuming component in this codebase, because it lets Gemini decide which tool to call next. `analyze` and `live` call the same tools (`get_pod_logs`, `get_pod_events`, `get_deployment_history`, `investigate_kubernetes_logs`) directly, in a fixed Python sequence — no LLM decides the order, so no tokens are spent deciding it. Don't collapse this distinction: never make `analyze`/`live` (or any new deterministic command) depend on `agent.py` or route through `root_agent` to do its job.
- New tools belong in `k8s_agent/tools/` as plain functions returning JSON-serializable dicts/strings (see `common.py` for the shared K8s-client → `kubectl` → offline-sample fallback chain). A tool is just a function; it does not imply an LLM is involved in calling it.

## Architecture

This is a **deterministic, offline-first log analyzer** with an optional single-shot LLM narrative layer — not an agentic/tool-calling LLM loop. The entire detection pipeline runs on regex pattern matching; an LLM call (if an API key is configured) is only used to add prose color to an already-complete report.

Pipeline, in `InvestigationEngine.investigate()` (`k8s_agent/engine.py`), always runs in this order:

1. **`parser.py`** (`LogParser`) — turns raw text into `LogEntry` records, trying format detectors in sequence per line: CRI-O/containerd (`timestamp stdout F ...`), JSON structured logs (zap/bunyan/winston-style, tries several key aliases like `message`/`msg`/`error`), `kubectl describe`-style K8s events (`Normal|Warning ...`), then falls back to a generic ISO-timestamp + log-level heuristic.
2. **`detectors.py`** (`RULES: List[DiagnosticRule]`) — a static catalog of regex rules, each tagged with an `IncidentCategory`, `Severity`, confidence score, and human explanation. This is the single source of truth for "what failure modes we recognize" (OOM, CrashLoopBackOff, probe failures, DNS, storage mount, RBAC, DB exhaustion, image pull, etc.). Adding a new failure signature means adding a `DiagnosticRule` here, not touching the engine.
3. **`engine.py`** (`InvestigationEngine`) — orchestrates the rest:
   - `_detect_anomalies`: matches every entry against every rule (first matching pattern wins per rule, per line).
   - `_extract_evidence`: dedupes by line number, pulls `context_lines` of surrounding raw lines around each trigger (configurable via `--context-lines`).
   - `_synthesize_causes`: aggregates matches into per-category scores (`confidence * severity_weight`), picks the highest-scoring category as the primary `RootCause`, the rest become `contributing_factors`. If nothing matched, falls back to an `UNKNOWN_ANOMALY` heuristic based on whether ERROR/FATAL lines exist at all.
   - `_generate_remediation`: a hardcoded per-category lookup table (`if cat == IncidentCategory.X: ...`) producing immediate actions, preventative actions, `kubectl` commands, and optional YAML manifest snippets. New categories need a branch here too.
   - Optional LLM step: if an `LLMReasoner` is passed in and has a key configured, calls it once to generate a prose post-mortem; failures here are caught and degrade gracefully (`llm_enhanced=False`, error message in `llm_insights`) rather than failing the investigation.
4. **`timeline.py`** (`TimelineBuilder`) — separately reconstructs a chronological narrative (STARTUP → DEGRADATION → anomaly events) from the same entries, merged and sorted by line number, independent of the root-cause scoring logic.
5. **`reporter.py`** (`ReportRenderer`) — renders the final `InvestigationReport` (a pydantic model, see `models.py`) to terminal (rich), Markdown, or JSON.

`cli.py` has two zero-token entrypoints, both calling the same tools in a fixed Python sequence (no LLM decides the order):
- `analyze <file|->`: file/stdin input → `InvestigationEngine` → `ReportRenderer`.
- `live <pod_name>`: `get_pod_logs` → `get_pod_events` → `get_deployment_history` → `InvestigationEngine` → `ReportRenderer`. Deployment history is reported alongside the RCA report, not fed into the regex engine (it isn't log-shaped text).

Both support `--fail-on-critical` (exit code 2) for CI/CD gating and default to `--no-llm` (see Zero-Token Rule above).

### ADK Agent & Modular Tool Layer (`k8s_agent/agent.py`, `k8s_agent/tools/`)

- Built with Google Agent Development Kit (`google-adk`). This is the token-consuming path — see Zero-Token Rule above.
- **`k8s_agent/tools/`**: Modular tools package conforming to ADK standards, each a plain function (no LLM involved in calling it):
  - `common.py`: Shared cluster authentication (`CoreV1Api`/`AppsV1Api`), `kubectl` runner, and offline mock-sample loader (`samples/` or `K8S_MOCK_LOGS_DIR`) — every tool falls back through K8s client → `kubectl` → offline sample in that order.
  - `pod_logs.py` (`get_pod_logs`): Fetches pod container logs (stdout/stderr).
  - `pod_events.py` (`get_pod_events`): Fetches Kubernetes lifecycle and warning events for a specific pod.
  - `deployment_history.py` (`get_deployment_history`): Resolves a pod/deployment name, walks ReplicaSet revisions to detect recent image/version changes and rollout status. Also exports `get_deployment_history_tool` (an ADK `FunctionTool` instance) for schema inspection.
  - `investigate.py` (`investigate_kubernetes_logs`): Analyzes raw log text or structured events using `InvestigationEngine` and returns a Markdown RCA report.
- **`agent.py`**: Defines `root_agent` using Gemini and wires `[get_pod_logs, get_pod_events, get_deployment_history, investigate_kubernetes_logs]`, with instructions to always fetch cluster data live rather than reading local files.
- **`agents-cli-manifest.yaml`**: Points `agent_directory: k8s_agent`. Run with `agents-cli run "prompt"` or `adk run k8s_agent`.

### LLM layer (`llm.py`)

- Entirely optional and off by default: `LLMReasoner.is_available()` gates on `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars (checked in that priority order), but even with a key set, `analyze`/`live` never invoke it unless the developer passes `--use-llm`. `--no-llm` is the hard override.
- Exactly one call per investigation, never a loop. Prompt is built from the primary root cause + top 10 evidence items + top 10 timeline events (`_build_prompt`), output capped at ~1000 tokens.
- If you change the model IDs here (e.g. `claude-3-5-sonnet-20241022`, `gemini-2.5-flash`, `gpt-4o-mini`), check all three provider methods (`_call_gemini`, `_call_anthropic`, `_call_openai`) — they're independent, not abstracted behind a shared client.

### Adding a new failure category

Touches four files in order: `models.py` (add to `IncidentCategory` enum) → `detectors.py` (add `DiagnosticRule` entries with patterns/confidence) → `engine.py` (`_determine_blast_radius` and `_generate_remediation` need a branch for the new category) → a corresponding sample log in `samples/` and test in `tests/test_detectors.py` / `tests/test_engine.py`.
