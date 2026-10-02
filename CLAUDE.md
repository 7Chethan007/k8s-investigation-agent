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

# Run the CLI against a sample log
k8s-investigate analyze samples/oom_killed.log
k8s-investigate analyze samples/oom_killed.log --format json
kubectl logs deployment/payment-service -n prod --previous | k8s-investigate analyze -
```

There is no lint/format config in this repo (no ruff/black/flake8 config present) and no CI workflow — `pytest` is the only gate.

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

`cli.py` is the click entrypoint (`k8s-investigate analyze ...`) wiring stdin/file input → `InvestigationEngine` → `ReportRenderer`, plus `--fail-on-critical` (exit code 2) for CI/CD gating.

### LLM layer (`llm.py`)

- Entirely optional: `LLMReasoner.is_available()` gates on `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars (checked in that priority order), disabled via `--no-llm`.
- Exactly one call per investigation, never a loop. Prompt is built from the primary root cause + top 10 evidence items + top 10 timeline events (`_build_prompt`), output capped at ~1000 tokens.
- If you change the model IDs here (e.g. `claude-3-5-sonnet-20241022`, `gemini-2.5-flash`, `gpt-4o-mini`), check all three provider methods (`_call_gemini`, `_call_anthropic`, `_call_openai`) — they're independent, not abstracted behind a shared client.

### Adding a new failure category

Touches four files in order: `models.py` (add to `IncidentCategory` enum) → `detectors.py` (add `DiagnosticRule` entries with patterns/confidence) → `engine.py` (`_determine_blast_radius` and `_generate_remediation` need a branch for the new category) → a corresponding sample log in `samples/` and test in `tests/test_detectors.py` / `tests/test_engine.py`.
