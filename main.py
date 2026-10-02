#!/usr/bin/env python3
"""Convenient root entrypoint for Kubernetes Investigation Agent."""

import sys
from pathlib import Path
from k8s_agent.cli import main
from k8s_agent.engine import InvestigationEngine
from k8s_agent.reporter import ReportRenderer
from rich.console import Console

if __name__ == "__main__":
    # If called with a simple file argument (e.g. `python main.py error.txt` or `python main.py`)
    # without subcommands, run direct investigation for maximum simplicity:
    if len(sys.argv) > 1 and sys.argv[1] not in ("analyze", "--help", "-h", "--version"):
        log_file = Path(sys.argv[1])
        if not log_file.is_file():
            print(f"Error: File '{sys.argv[1]}' not found.", file=sys.stderr)
            sys.exit(1)
        
        content = log_file.read_text(encoding="utf-8", errors="replace")
        engine = InvestigationEngine()
        report = engine.investigate(content, source_name=log_file.name)
        ReportRenderer.render_terminal(report, Console())
    elif len(sys.argv) == 1:
        # Default fallback: check if standard sample exists
        default_file = Path("samples/crashloop_db_exhaustion.log")
        if default_file.is_file():
            content = default_file.read_text(encoding="utf-8", errors="replace")
            engine = InvestigationEngine()
            report = engine.investigate(content, source_name=default_file.name)
            ReportRenderer.render_terminal(report, Console())
        else:
            main()
    else:
        main()
