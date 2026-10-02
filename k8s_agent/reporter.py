"""Report formatting and rendering for Kubernetes investigation results."""

import json
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from k8s_agent.models import InvestigationReport, Severity


class ReportRenderer:
    """Renders investigation reports in Markdown, JSON, and rich Terminal formats."""

    @staticmethod
    def render_json(report: InvestigationReport) -> str:
        """Serializes report into structured JSON."""
        return report.model_dump_json(indent=2)

    @staticmethod
    def render_markdown(report: InvestigationReport) -> str:
        """Formats the investigation report as standard Markdown."""
        lines = []

        # Title & Metadata
        lines.append(f"# Kubernetes Incident Investigation Report")
        lines.append(f"**Investigation ID**: `{report.investigation_id}` | **Date**: `{report.timestamp}`")
        lines.append(f"- **Target Source**: `{report.target_source}`")
        lines.append(f"- **Lines Analyzed**: {report.total_lines_analyzed:,}")
        lines.append(f"- **Anomalies Detected**: {report.anomalies_detected_count}")
        lines.append("")

        # Root Cause Analysis
        rc = report.root_cause
        sev_emoji = {
            Severity.CRITICAL: "🔴 CRITICAL",
            Severity.HIGH: "🟠 HIGH",
            Severity.MEDIUM: "🟡 MEDIUM",
            Severity.LOW: "🔵 LOW",
            Severity.INFO: "⚪ INFO",
        }.get(rc.severity, str(rc.severity))

        lines.append("## Root Cause Analysis")
        lines.append(f"- **Category**: `{rc.category.value}`")
        lines.append(f"- **Severity**: {sev_emoji}")
        lines.append(f"- **Confidence Score**: `{rc.confidence_score * 100:.1f}%`")
        lines.append(f"- **Blast Radius**: {rc.blast_radius}")
        lines.append("")
        lines.append(f"**Summary**: {rc.summary}")
        lines.append("")

        # Contributing Factors
        if report.contributing_factors:
            lines.append("### Contributing Factors")
            for factor in report.contributing_factors:
                lines.append(
                    f"- **`{factor.category.value}`** ({factor.severity.value}, "
                    f"confidence: {factor.confidence_score*100:.0f}%): {factor.summary}"
                )
            lines.append("")

        # Supporting Evidence
        lines.append("## Supporting Evidence")
        if not report.evidence:
            lines.append("_No specific log signatures matched known failure patterns._")
        else:
            for idx, ev in enumerate(report.evidence, start=1):
                ts_str = f" @ `{ev.timestamp}`" if ev.timestamp else ""
                lines.append(f"### Evidence #{idx}: Line {ev.line_number}{ts_str} - `{ev.rule_name}`")
                lines.append(f"_{ev.explanation}_")
                lines.append("")
                lines.append("```log")
                for ctx in ev.context_before:
                    lines.append(f"  {ctx}")
                lines.append(f"> {ev.trigger_line}  <-- [TRIGGER]")
                for ctx in ev.context_after:
                    lines.append(f"  {ctx}")
                lines.append("```")
                lines.append("")

        # Incident Timeline
        if report.timeline:
            lines.append("## Incident Timeline")
            lines.append("| Phase | Line | Timestamp | Event Description |")
            lines.append("|---|---|---|---|")
            for t in report.timeline:
                ts = t.timestamp or "N/A"
                lines.append(f"| **{t.phase}** | `{t.line_number}` | `{ts}` | {t.description} |")
            lines.append("")

        # Actionable Remediation
        rem = report.remediation
        lines.append("## Actionable Remediation")
        if rem.immediate_actions:
            lines.append("### Immediate Actions")
            for act in rem.immediate_actions:
                lines.append(f"1. {act}")
            lines.append("")

        if rem.preventative_actions:
            lines.append("### Preventative Architecture & Long-Term Fixes")
            for prev in rem.preventative_actions:
                lines.append(f"- {prev}")
            lines.append("")

        if rem.remediation_commands:
            lines.append("### Diagnostic & Remediation Commands")
            lines.append("```bash")
            for cmd in rem.remediation_commands:
                lines.append(cmd)
            lines.append("```")
            lines.append("")

        if rem.manifest_snippet:
            lines.append("### Recommended Manifest Patch")
            lines.append("```yaml")
            lines.append(rem.manifest_snippet.strip())
            lines.append("```")
            lines.append("")

        # LLM Insights if available
        if report.llm_enhanced and report.llm_insights:
            lines.append("## LLM Post-Mortem Synthesis")
            lines.append(report.llm_insights)
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def render_terminal(cls, report: InvestigationReport, console: Optional[Console] = None):
        """Prints a styled terminal view using Rich."""
        if console is None:
            console = Console()

        md_content = cls.render_markdown(report)
        console.print(Markdown(md_content))
