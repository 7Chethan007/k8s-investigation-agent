"""Data models for Kubernetes Investigation Agent."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class IncidentCategory(str, Enum):
    OOM_KILLED = "OOM_KILLED"
    CRASH_LOOP_BACKOFF = "CRASH_LOOP_BACKOFF"
    LIVENESS_PROBE_FAILURE = "LIVENESS_PROBE_FAILURE"
    READINESS_PROBE_FAILURE = "READINESS_PROBE_FAILURE"
    STARTUP_PROBE_FAILURE = "STARTUP_PROBE_FAILURE"
    IMAGE_PULL_FAILURE = "IMAGE_PULL_FAILURE"
    DNS_RESOLUTION_FAILURE = "DNS_RESOLUTION_FAILURE"
    NETWORK_CONNECTIVITY_FAILURE = "NETWORK_CONNECTIVITY_FAILURE"
    STORAGE_MOUNT_FAILURE = "STORAGE_MOUNT_FAILURE"
    RBAC_PERMISSION_DENIED = "RBAC_PERMISSION_DENIED"
    DATABASE_EXHAUSTION = "DATABASE_EXHAUSTION"
    APPLICATION_PANIC = "APPLICATION_PANIC"
    CONFIG_SECRET_MISSING = "CONFIG_SECRET_MISSING"
    UNKNOWN_ANOMALY = "UNKNOWN_ANOMALY"


class LogEntry(BaseModel):
    """Represents a single parsed line from Kubernetes logs."""
    line_number: int
    timestamp: Optional[str] = None
    stream: Optional[str] = None  # stdout, stderr, etc.
    level: Optional[str] = None   # INFO, WARN, ERROR, FATAL, PANIC
    component: Optional[str] = None
    raw_content: str
    message: str
    is_json: bool = False
    structured_data: Dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    """Verbatim supporting evidence extracted from logs with line numbers and surrounding context."""
    line_number: int
    timestamp: Optional[str] = None
    trigger_line: str
    context_before: List[str] = Field(default_factory=list)
    context_after: List[str] = Field(default_factory=list)
    rule_name: str
    explanation: str


class TimelineEvent(BaseModel):
    """Key event along the timeline leading to the incident."""
    timestamp: Optional[str] = None
    line_number: int
    phase: str  # e.g., STARTUP, DEGRADATION, FAILURE, RESTART
    description: str
    severity: Severity = Severity.INFO


class RootCause(BaseModel):
    """Detailed root cause analysis."""
    category: IncidentCategory
    severity: Severity
    confidence_score: float = Field(ge=0.0, le=1.0)
    title: str
    summary: str
    blast_radius: str


class Remediation(BaseModel):
    """Prescriptive, actionable remediation instructions."""
    immediate_actions: List[str] = Field(default_factory=list)
    preventative_actions: List[str] = Field(default_factory=list)
    remediation_commands: List[str] = Field(default_factory=list)
    manifest_snippet: Optional[str] = None


class InvestigationReport(BaseModel):
    """Complete post-investigation report with supporting evidence."""
    investigation_id: str
    timestamp: str
    target_source: str
    total_lines_analyzed: int
    anomalies_detected_count: int
    root_cause: RootCause
    contributing_factors: List[RootCause] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    remediation: Remediation
    llm_enhanced: bool = False
    llm_insights: Optional[str] = None
