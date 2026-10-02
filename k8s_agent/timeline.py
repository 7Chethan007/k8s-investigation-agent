"""Incident timeline builder and lifecycle event correlator."""

import re
from typing import List, Optional
from k8s_agent.models import LogEntry, Severity, TimelineEvent

STARTUP_PATTERNS = [
    re.compile(r"starting|booting|initializing|listening on|server started", re.IGNORECASE),
    re.compile(r"pulling image|successfully pulled image", re.IGNORECASE),
]

DEGRADATION_PATTERNS = [
    re.compile(r"slow query|timeout|high latency|retrying|connection pool high", re.IGNORECASE),
    re.compile(r"warn|warning|elevated error rate", re.IGNORECASE),
]


class TimelineBuilder:
    """Constructs a chronological incident timeline from parsed log entries."""

    def build_timeline(
        self, entries: List[LogEntry], anomalies: List[TimelineEvent]
    ) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        seen_lines = set()

        # 1. Identify startup events
        for entry in entries[:15]:  # Look at initial window
            for pat in STARTUP_PATTERNS:
                if pat.search(entry.message):
                    events.append(
                        TimelineEvent(
                            timestamp=entry.timestamp,
                            line_number=entry.line_number,
                            phase="STARTUP",
                            description=self._truncate(entry.message, 100),
                            severity=Severity.INFO,
                        )
                    )
                    seen_lines.add(entry.line_number)
                    break

        # 2. Identify degradation events (warnings / retries before the crash)
        for entry in entries:
            if entry.line_number in seen_lines:
                continue
            if entry.level in ("WARN", "WARNING"):
                for pat in DEGRADATION_PATTERNS:
                    if pat.search(entry.message):
                        events.append(
                            TimelineEvent(
                                timestamp=entry.timestamp,
                                line_number=entry.line_number,
                                phase="DEGRADATION",
                                description=self._truncate(entry.message, 100),
                                severity=Severity.MEDIUM,
                            )
                        )
                        seen_lines.add(entry.line_number)
                        break

        # 3. Incorporate detected anomaly events
        for anom in anomalies:
            if anom.line_number not in seen_lines:
                events.append(anom)
                seen_lines.add(anom.line_number)

        # Sort chronologically by line number
        events.sort(key=lambda x: x.line_number)
        return events

    def _truncate(self, text: str, max_len: int) -> str:
        text = text.strip()
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."
