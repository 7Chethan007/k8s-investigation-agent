"""CLI entrypoint for Kubernetes Investigation Agent."""

import sys
from pathlib import Path
import click
from rich.console import Console
from k8s_agent.engine import InvestigationEngine
from k8s_agent.llm import LLMReasoner
from k8s_agent.models import Severity
from k8s_agent.reporter import ReportRenderer


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Kubernetes Log Investigation Agent - Automated Root-Cause Analysis with Evidence."""
    pass


@main.command(name="analyze")
@click.argument("log_source", required=False, default="-")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["terminal", "markdown", "json"], case_sensitive=False),
    default="terminal",
    help="Output format for investigation results.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(writable=True, path_type=Path),
    help="Optional file destination to save report.",
)
@click.option(
    "--context-lines",
    "-c",
    type=int,
    default=3,
    help="Number of context lines surrounding evidence triggers (default: 3).",
)
@click.option(
    "--use-llm/--no-llm",
    default=True,
    help="Enable/disable optional LLM post-mortem synthesis if API key is present.",
)
@click.option(
    "--fail-on-critical",
    is_flag=True,
    help="Exit with return code 2 if CRITICAL root cause is detected (ideal for CI/CD gates).",
)
def analyze(
    log_source: str,
    output_format: str,
    output: Path,
    context_lines: int,
    use_llm: bool,
    fail_on_critical: bool,
):
    """Analyzes Kubernetes logs from a file or stdin pipe.

    Examples:

      k8s-investigate analyze /path/to/pod.log

      kubectl logs my-pod -n prod | k8s-investigate analyze -

      k8s-investigate analyze pod.log --format markdown -o report.md
    """
    console = Console()

    error_console = Console(stderr=True)

    # 1. Read input logs
    source_label = log_source
    if log_source == "-":
        if sys.stdin.isatty():
            console.print("[yellow]Reading from stdin... (press Ctrl+D to end input)[/yellow]")
        raw_text = sys.stdin.read()
        source_label = "stdin"
    else:
        path = Path(log_source)
        if not path.is_file():
            error_console.print(f"[red]Error:[/red] Log file '{log_source}' not found.")
            sys.exit(1)
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        source_label = path.name

    if not raw_text.strip():
        error_console.print("[red]Error:[/red] Provided log input is empty.")
        sys.exit(1)

    # 2. Setup investigator
    engine = InvestigationEngine(context_lines=context_lines)
    llm = LLMReasoner() if use_llm else None

    # 3. Run investigation
    report = engine.investigate(
        log_content=raw_text,
        source_name=source_label,
        llm_reasoner=llm,
    )

    # 4. Format & output results
    if output_format == "json":
        result_text = ReportRenderer.render_json(report)
        if output:
            output.write_text(result_text, encoding="utf-8")
            console.print(f"[green]JSON report saved to {output}[/green]")
        else:
            click.echo(result_text)
    elif output_format == "markdown":
        result_text = ReportRenderer.render_markdown(report)
        if output:
            output.write_text(result_text, encoding="utf-8")
            console.print(f"[green]Markdown report saved to {output}[/green]")
        else:
            click.echo(result_text)
    else:  # terminal
        if output:
            result_text = ReportRenderer.render_markdown(report)
            output.write_text(result_text, encoding="utf-8")
            console.print(f"[green]Report saved to {output}[/green]")
        ReportRenderer.render_terminal(report, console)

    # 5. Check fail-on-critical exit code
    if fail_on_critical and report.root_cause.severity == Severity.CRITICAL:
        sys.exit(2)


if __name__ == "__main__":
    main()
