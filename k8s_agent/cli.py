"""CLI entrypoint for Kubernetes Investigation Agent."""

import sys
from pathlib import Path
import click
from rich.console import Console
from k8s_agent.engine import InvestigationEngine
from k8s_agent.llm import LLMReasoner
from k8s_agent.models import Severity
from k8s_agent.reporter import ReportRenderer
from k8s_agent.tools import get_deployment_history, get_pod_events, get_pod_logs


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
    default=False,
    help=(
        "Opt into optional LLM post-mortem synthesis if an API key is present (off by default: "
        "this command is zero-token unless explicitly enabled). --no-llm always hard-disables it."
    ),
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


@main.command(name="live")
@click.argument("pod_name")
@click.option("--namespace", "-n", default="default", help="Kubernetes namespace (default: 'default').")
@click.option("--container", default=None, help="Specific container name for multi-container pods.")
@click.option("--tail-lines", type=int, default=500, help="Number of most recent log lines to fetch (default: 500).")
@click.option("--previous", is_flag=True, help="Fetch logs for the previous (crashed/restarted) container instance.")
@click.option("--skip-events", is_flag=True, help="Skip fetching pod lifecycle/warning events.")
@click.option("--skip-deployment-history", is_flag=True, help="Skip fetching deployment rollout history.")
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
    default=False,
    help=(
        "Opt into optional LLM post-mortem synthesis if an API key is present (off by default: "
        "this command is zero-token unless explicitly enabled). --no-llm always hard-disables it."
    ),
)
@click.option(
    "--fail-on-critical",
    is_flag=True,
    help="Exit with return code 2 if CRITICAL root cause is detected (ideal for CI/CD gates).",
)
def live(
    pod_name: str,
    namespace: str,
    container: str,
    tail_lines: int,
    previous: bool,
    skip_events: bool,
    skip_deployment_history: bool,
    output_format: str,
    output: Path,
    context_lines: int,
    use_llm: bool,
    fail_on_critical: bool,
):
    """Investigates a live Kubernetes pod directly from the cluster: no LLM, no agent loop.

    Fetches logs, events, and deployment history via a fixed deterministic sequence
    (the same tools the ADK agent uses), then runs the regex-based root-cause engine.
    By default this makes zero LLM calls; pass --use-llm to opt into the narrative layer.

    Example:

      k8s-investigate live payment-service-7f8d9 -n prod
    """
    console = Console()
    error_console = Console(stderr=True)

    # 1. Fetch live container logs
    logs_result = get_pod_logs(
        pod_name=pod_name,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
        previous=previous,
    )
    if logs_result["status"] != "success":
        error_console.print(f"[red]Error fetching logs:[/red] {logs_result.get('error')}")
        sys.exit(1)

    combined_text = logs_result["logs"]

    # 2. Fetch pod lifecycle/warning events
    if not skip_events:
        events_result = get_pod_events(pod_name=pod_name, namespace=namespace)
        if events_result["status"] == "success":
            combined_text += "\n" + events_result["raw_events_text"]
        else:
            error_console.print(f"[yellow]Warning: could not fetch pod events:[/yellow] {events_result.get('error')}")

    # 3. Fetch deployment rollout history (reported alongside, not fed into the regex engine)
    deployment_summary = None
    if not skip_deployment_history:
        deployment_result = get_deployment_history(name=pod_name, namespace=namespace)
        if deployment_result["status"] == "success":
            deployment_summary = deployment_result["summary"]
        else:
            error_console.print(
                f"[yellow]Warning: could not fetch deployment history:[/yellow] {deployment_result.get('error')}"
            )

    # 4. Run deterministic root-cause analysis
    engine = InvestigationEngine(context_lines=context_lines)
    llm = LLMReasoner() if use_llm else None
    report = engine.investigate(
        log_content=combined_text,
        source_name=f"{namespace}/{pod_name}",
        llm_reasoner=llm,
    )

    # 5. Format & output results
    if output_format == "json":
        result_text = ReportRenderer.render_json(report)
        if output:
            output.write_text(result_text, encoding="utf-8")
            console.print(f"[green]JSON report saved to {output}[/green]")
        else:
            click.echo(result_text)
    else:
        result_text = ReportRenderer.render_markdown(report)
        if deployment_summary:
            result_text += f"\n## Deployment History\n\n{deployment_summary}\n"
        if output:
            output.write_text(result_text, encoding="utf-8")
            console.print(f"[green]Report saved to {output}[/green]")
        if output_format == "terminal":
            ReportRenderer.render_terminal(report, console)
            if deployment_summary:
                console.print(f"\n[bold]Deployment History:[/bold] {deployment_summary}")
        elif not output:
            click.echo(result_text)

    # 6. Check fail-on-critical exit code
    if fail_on_critical and report.root_cause.severity == Severity.CRITICAL:
        sys.exit(2)


if __name__ == "__main__":
    main()
