"""Log parser supporting standard Kubernetes, CRI-O/containerd, JSON, and raw application logs."""

import json
import re
from typing import List, Optional, Tuple
from k8s_agent.models import LogEntry

# Regex patterns for common timestamp formats
ISO_TIMESTAMP_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

# CRI format: 2026-10-02T16:12:30.123456789Z stdout F ...
CRI_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+(stdout|stderr)\s+([FP])\s+(.*)$"
)

# Standard log level keywords
LOG_LEVEL_PATTERN = re.compile(
    r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|PANIC|SEVERE)\b",
    re.IGNORECASE,
)

# Kubernetes Event pattern: e.g. Warning  Unhealthy  1m  kubelet  Liveness probe failed...
K8S_EVENT_PATTERN = re.compile(
    r"^(Normal|Warning)\s+([A-Za-z0-9_]+)\s+([0-9a-z]+)\s+([A-Za-z0-9_\-\.]+)\s+(.*)$"
)


class LogParser:
    """Parses Kubernetes log streams into structured LogEntry records."""

    def parse_text(self, text: str) -> List[LogEntry]:
        """Parses a multi-line log string into a list of LogEntry objects."""
        lines = text.splitlines()
        entries: List[LogEntry] = []

        for idx, line in enumerate(lines, start=1):
            entry = self.parse_line(line, idx)
            entries.append(entry)

        return entries

    def parse_line(self, line: str, line_number: int) -> LogEntry:
        """Parses a single line into a LogEntry object."""
        raw_content = line
        stripped = line.strip()

        # 1. Try parsing CRI containerd/CRI-O log format
        cri_match = CRI_LOG_PATTERN.match(stripped)
        if cri_match:
            ts, stream, _flag, payload = cri_match.groups()
            level = self._extract_log_level(payload)
            return LogEntry(
                line_number=line_number,
                timestamp=ts,
                stream=stream,
                level=level,
                raw_content=raw_content,
                message=payload,
            )

        # 2. Try parsing JSON structured log
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    ts = (
                        data.get("timestamp")
                        or data.get("time")
                        or data.get("ts")
                        or data.get("@timestamp")
                    )
                    level = (
                        data.get("level")
                        or data.get("severity")
                        or data.get("log_level")
                    )
                    msg = (
                        data.get("message")
                        or data.get("msg")
                        or data.get("error")
                        or str(data)
                    )
                    stream = data.get("stream")
                    component = (
                        data.get("component")
                        or data.get("logger")
                        or data.get("caller")
                    )
                    return LogEntry(
                        line_number=line_number,
                        timestamp=str(ts) if ts else None,
                        stream=str(stream) if stream else None,
                        level=str(level).upper() if level else None,
                        component=str(component) if component else None,
                        raw_content=raw_content,
                        message=str(msg),
                        is_json=True,
                        structured_data=data,
                    )
            except Exception:
                pass  # Fall through to standard parsing

        # 3. Try parsing Kubernetes event output (e.g. from kubectl describe)
        k8s_match = K8S_EVENT_PATTERN.match(stripped)
        if k8s_match:
            ev_type, reason, _age, component, msg = k8s_match.groups()
            level = "WARN" if ev_type == "Warning" else "INFO"
            return LogEntry(
                line_number=line_number,
                level=level,
                component=component,
                raw_content=raw_content,
                message=f"[{reason}] {msg}",
            )

        # 4. Standard log with possible leading ISO timestamp
        ts_match = ISO_TIMESTAMP_PATTERN.match(stripped)
        timestamp = None
        message = stripped

        if ts_match:
            timestamp = ts_match.group(1)
            message = stripped[ts_match.end() :].strip()

        level = self._extract_log_level(message)

        return LogEntry(
            line_number=line_number,
            timestamp=timestamp,
            level=level,
            raw_content=raw_content,
            message=message if message else raw_content,
        )

    def _extract_log_level(self, text: str) -> Optional[str]:
        """Extracts the log level keyword from text if present."""
        match = LOG_LEVEL_PATTERN.search(text)
        if match:
            level_str = match.group(1).upper()
            if level_str in ("WARNING", "WARN"):
                return "WARN"
            if level_str in ("FATAL", "CRITICAL", "PANIC", "SEVERE"):
                return "FATAL"
            return level_str
        return None
