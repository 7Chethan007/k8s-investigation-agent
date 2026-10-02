"""Unit tests for the CLI interface."""

import json
from pathlib import Path
from click.testing import CliRunner
from k8s_agent.cli import main


def test_cli_analyze_file():
    runner = CliRunner()
    sample_path = str(Path(__file__).parent.parent / "samples" / "oom_killed.log")

    result = runner.invoke(main, ["analyze", sample_path, "--format", "json"])
    assert result.exit_code == 0

    parsed = json.loads(result.output)
    assert parsed["root_cause"]["category"] == "OOM_KILLED"
    assert len(parsed["evidence"]) > 0


def test_cli_analyze_stdin():
    runner = CliRunner()
    stdin_data = "2026-10-02T12:00:00Z Warning  Unhealthy  10s  kubelet  Liveness probe failed: HTTP probe failed with statuscode: 500\n"

    result = runner.invoke(main, ["analyze", "-", "--format", "markdown"], input=stdin_data)
    assert result.exit_code == 0
    assert "Root Cause Analysis" in result.output
    assert "LIVENESS_PROBE_FAILURE" in result.output


def test_cli_fail_on_critical_flag():
    runner = CliRunner()
    sample_path = str(Path(__file__).parent.parent / "samples" / "oom_killed.log")

    # Should exit with code 2 because OOM_KILLED is CRITICAL
    result = runner.invoke(main, ["analyze", sample_path, "--fail-on-critical"])
    assert result.exit_code == 2


def test_cli_empty_input():
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", "-"], input="   \n")
    assert result.exit_code == 1
    assert "empty" in result.output.lower()


def test_cli_save_output_to_file(tmp_path):
    runner = CliRunner()
    sample_path = str(Path(__file__).parent.parent / "samples" / "oom_killed.log")
    out_file = tmp_path / "report.md"

    result = runner.invoke(main, ["analyze", sample_path, "--format", "markdown", "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Root Cause Analysis" in content
    assert "OOM_KILLED" in content


def test_cli_save_json_to_file(tmp_path):
    runner = CliRunner()
    sample_path = str(Path(__file__).parent.parent / "samples" / "oom_killed.log")
    out_file = tmp_path / "report.json"

    result = runner.invoke(main, ["analyze", sample_path, "--format", "json", "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.is_file()
    parsed = json.loads(out_file.read_text(encoding="utf-8"))
    assert parsed["root_cause"]["category"] == "OOM_KILLED"

