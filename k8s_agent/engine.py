"""Core investigation engine for automated Kubernetes incident analysis."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from k8s_agent.detectors import AnomalyMatch, DiagnosticRule, RULES
from k8s_agent.models import (
    EvidenceItem,
    IncidentCategory,
    InvestigationReport,
    LogEntry,
    Remediation,
    RootCause,
    Severity,
    TimelineEvent,
)
from k8s_agent.parser import LogParser
from k8s_agent.timeline import TimelineBuilder


class InvestigationEngine:
    """Orchestrates parsing, anomaly detection, evidence isolation, and report generation."""

    def __init__(self, context_lines: int = 3):
        self.parser = LogParser()
        self.timeline_builder = TimelineBuilder()
        self.context_lines = context_lines

    def investigate(
        self,
        log_content: str,
        source_name: str = "kubernetes-logs",
        llm_reasoner=None,
    ) -> InvestigationReport:
        """Executes the complete investigation pipeline on the provided log content."""
        entries = self.parser.parse_text(log_content)
        raw_lines = [e.raw_content for e in entries]

        # 1. Detect anomalies across log entries
        matches = self._detect_anomalies(entries)

        # 2. Extract verbatim evidence with context window
        evidence_items = self._extract_evidence(matches, raw_lines, entries)

        # 3. Formulate timeline events
        timeline_anomalies = [
            TimelineEvent(
                timestamp=entries[m.line_number - 1].timestamp,
                line_number=m.line_number,
                phase="CRASH_EVENT" if m.rule.severity == Severity.CRITICAL else "FAILURE",
                description=f"[{m.rule.name}] {m.rule.explanation}",
                severity=m.rule.severity,
            )
            for m in matches
        ]
        timeline = self.timeline_builder.build_timeline(entries, timeline_anomalies)

        # 4. Synthesize Root Cause and Contributing Factors
        primary_cause, contributing_factors = self._synthesize_causes(matches, entries)

        # 5. Generate Prescriptive Remediation
        remediation = self._generate_remediation(primary_cause, contributing_factors)

        # 6. Optional LLM reasoning enhancement
        llm_insights = None
        llm_enhanced = False
        if llm_reasoner and llm_reasoner.is_available():
            try:
                llm_insights = llm_reasoner.enhance_analysis(
                    primary_cause=primary_cause,
                    evidence=evidence_items,
                    timeline=timeline,
                )
                llm_enhanced = True
            except Exception as e:
                llm_insights = f"LLM enhancement failed: {str(e)}"

        return InvestigationReport(
            investigation_id=f"k8s-inv-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            target_source=source_name,
            total_lines_analyzed=len(entries),
            anomalies_detected_count=len(matches),
            root_cause=primary_cause,
            contributing_factors=contributing_factors,
            evidence=evidence_items,
            timeline=timeline,
            remediation=remediation,
            llm_enhanced=llm_enhanced,
            llm_insights=llm_insights,
        )

    def _detect_anomalies(self, entries: List[LogEntry]) -> List[AnomalyMatch]:
        """Scans parsed entries against all diagnostic rules."""
        matches: List[AnomalyMatch] = []
        for entry in entries:
            # Check raw_content and message
            for rule in RULES:
                for pattern in rule.patterns:
                    m = pattern.search(entry.raw_content) or pattern.search(entry.message)
                    if m:
                        matches.append(
                            AnomalyMatch(
                                rule=rule,
                                line_number=entry.line_number,
                                matched_text=m.group(0),
                                pattern_string=pattern.pattern,
                            )
                        )
                        break  # Match rule once per line
        return matches

    def _extract_evidence(
        self, matches: List[AnomalyMatch], raw_lines: List[str], entries: List[LogEntry]
    ) -> List[EvidenceItem]:
        """Extracts unique verbatim evidence items with surrounding context."""
        evidence: List[EvidenceItem] = []
        seen_lines = set()

        for match in matches:
            line_idx = match.line_number - 1
            if match.line_number in seen_lines:
                continue
            seen_lines.add(match.line_number)

            # Extract window before
            start_before = max(0, line_idx - self.context_lines)
            context_before = raw_lines[start_before:line_idx]

            # Extract window after
            end_after = min(len(raw_lines), line_idx + 1 + self.context_lines)
            context_after = raw_lines[line_idx + 1 : end_after]

            trigger_line = raw_lines[line_idx]
            timestamp = entries[line_idx].timestamp

            evidence.append(
                EvidenceItem(
                    line_number=match.line_number,
                    timestamp=timestamp,
                    trigger_line=trigger_line,
                    context_before=context_before,
                    context_after=context_after,
                    rule_name=match.rule.name,
                    explanation=match.rule.explanation,
                )
            )

        return evidence

    def _synthesize_causes(
        self, matches: List[AnomalyMatch], entries: List[LogEntry]
    ) -> Tuple[RootCause, List[RootCause]]:
        """Synthesizes primary root cause and contributing factors from anomaly matches."""
        if not matches:
            # No recognized patterns matched; perform fallback heuristic
            has_errors = any(e.level in ("ERROR", "FATAL") for e in entries)
            return (
                RootCause(
                    category=IncidentCategory.UNKNOWN_ANOMALY,
                    severity=Severity.MEDIUM if has_errors else Severity.LOW,
                    confidence_score=0.30 if has_errors else 0.10,
                    title="No Definite Known Failure Pattern Matched",
                    summary=(
                        "Logs contained general activity or unstructured error statements "
                        "without triggering signature Kubernetes failure rules."
                    ),
                    blast_radius="Undetermined / Localized",
                ),
                [],
            )

        # Score categories by rule confidence & severity weight
        category_scores: Dict[IncidentCategory, float] = {}
        category_rules: Dict[IncidentCategory, List[DiagnosticRule]] = {}

        severity_weights = {
            Severity.CRITICAL: 1.5,
            Severity.HIGH: 1.2,
            Severity.MEDIUM: 1.0,
            Severity.LOW: 0.8,
            Severity.INFO: 0.5,
        }

        for match in matches:
            cat = match.rule.category
            weight = severity_weights.get(match.rule.severity, 1.0)
            score = match.rule.confidence * weight
            category_scores[cat] = category_scores.get(cat, 0.0) + score
            category_rules.setdefault(cat, []).append(match.rule)

        # Sort categories by aggregate score descending
        sorted_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        primary_cat, _ = sorted_categories[0]
        primary_rule = category_rules[primary_cat][0]

        primary_cause = RootCause(
            category=primary_cat,
            severity=primary_rule.severity,
            confidence_score=min(1.0, primary_rule.confidence),
            title=self._format_title(primary_cat),
            summary=primary_rule.explanation,
            blast_radius=self._determine_blast_radius(primary_cat, primary_rule.severity),
        )

        contributing: List[RootCause] = []
        for cat, _ in sorted_categories[1:]:
            rule = category_rules[cat][0]
            contributing.append(
                RootCause(
                    category=cat,
                    severity=rule.severity,
                    confidence_score=min(1.0, rule.confidence),
                    title=self._format_title(cat),
                    summary=rule.explanation,
                    blast_radius=self._determine_blast_radius(cat, rule.severity),
                )
            )

        return primary_cause, contributing

    def _format_title(self, category: IncidentCategory) -> str:
        return category.value.replace("_", " ").title()

    def _determine_blast_radius(self, category: IncidentCategory, severity: Severity) -> str:
        if category == IncidentCategory.OOM_KILLED:
            return "Container terminated immediately by kernel; Pod restarts repeatedly causing request timeouts."
        if category == IncidentCategory.CRASH_LOOP_BACKOFF:
            return "Pod enters exponential restart backoff; zero healthy replicas serving traffic."
        if category == IncidentCategory.LIVENESS_PROBE_FAILURE:
            return "Pod restarts cyclically; intermittent service degradation and connection dropping."
        if category == IncidentCategory.READINESS_PROBE_FAILURE:
            return "Pod pulled out of Service Endpoints; ingress / frontend routes 503 to end-users."
        if category == IncidentCategory.DNS_RESOLUTION_FAILURE:
            return "Outbound downstream and in-cluster RPC requests fail; cascading dependent service errors."
        if category == IncidentCategory.DATABASE_EXHAUSTION:
            return "Application-wide API stalls; all concurrent worker threads blocked awaiting DB connection."
        if category == IncidentCategory.IMAGE_PULL_FAILURE:
            return "Deployment rollout blocked; new version cannot start, stale or 0 pods available."
        if category == IncidentCategory.RBAC_PERMISSION_DENIED:
            return "Controller / Operator fails to reconcile state; cluster automation blocked."
        if category == IncidentCategory.STORAGE_MOUNT_FAILURE:
            return "Pod stuck in ContainerCreating state indefinitely; storage dependent workload halted."
        return "Localized container degradation."

    def _generate_remediation(
        self, primary: RootCause, contributing: List[RootCause]
    ) -> Remediation:
        """Constructs actionable remediation procedures and commands."""
        cat = primary.category

        if cat == IncidentCategory.OOM_KILLED:
            return Remediation(
                immediate_actions=[
                    "Check the memory usage profile of the previous terminated container: `kubectl describe pod <pod-name> | grep -A 5 'Last State'`.",
                    "Temporarily increase container memory limit to allow application to boot.",
                    "Inspect application heap dump or memory profiler logs to identify memory leaks.",
                ],
                preventative_actions=[
                    "Adjust memory limits and requests in deployment specification based on P99 utilization.",
                    "For JVM workloads, set `-XX:MaxRAMPercentage=75.0` and `-XX:+ExitOnOutOfMemoryError`.",
                    "Enable Vertical Pod Autoscaler (VPA) in recommendation mode to rightsize memory.",
                ],
                remediation_commands=[
                    "kubectl describe pod <pod-name>",
                    "kubectl top pod <pod-name> --containers",
                    "kubectl patch deployment <deployment-name> -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"<container>\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"},\"requests\":{\"memory\":\"1Gi\"}}}]}}}}'",
                ],
                manifest_snippet="""resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
""",
            )

        if cat == IncidentCategory.CRASH_LOOP_BACKOFF or cat == IncidentCategory.APPLICATION_PANIC:
            return Remediation(
                immediate_actions=[
                    "Inspect the crash traceback from the previous failed container execution.",
                    "Validate required environment variables, config files, and database connectivity.",
                    "Run an ephemeral debug container or shell into the image locally to inspect entrypoint.",
                ],
                preventative_actions=[
                    "Add robust panic recovery / top-level error handling in application startup code.",
                    "Implement pre-flight initialization checks with explicit logging before starting listeners.",
                    "Ensure health probes do not trigger prematurely before initialization completes.",
                ],
                remediation_commands=[
                    "kubectl logs <pod-name> --previous",
                    "kubectl describe pod <pod-name>",
                    "kubectl rollout undo deployment/<deployment-name>",
                ],
            )

        if cat in (IncidentCategory.LIVENESS_PROBE_FAILURE, IncidentCategory.READINESS_PROBE_FAILURE):
            return Remediation(
                immediate_actions=[
                    "Verify the probe health endpoint independently: test if `/healthz` returns 200 via `kubectl exec`.",
                    "Increase `initialDelaySeconds` and `timeoutSeconds` to prevent premature probe kills.",
                    "Check if the application is under high CPU throttling delaying probe response.",
                ],
                preventative_actions=[
                    "Decouple probe health check from heavy external downstream dependencies (e.g. DB, cache).",
                    "Utilize `startupProbe` for applications with long or variable startup durations.",
                    "Tune `periodSeconds` and `failureThreshold` according to realistic application latency.",
                ],
                remediation_commands=[
                    "kubectl describe pod <pod-name> | grep -A 10 'Liveness'",
                    "kubectl patch deployment <deployment-name> -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"<container>\",\"livenessProbe\":{\"initialDelaySeconds\":30,\"timeoutSeconds\":5,\"failureThreshold\":3}}]}}}}'",
                ],
                manifest_snippet="""startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 30
  periodSeconds: 10
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  initialDelaySeconds: 10
  timeoutSeconds: 3
  periodSeconds: 10
  failureThreshold: 3
""",
            )

        if cat == IncidentCategory.DNS_RESOLUTION_FAILURE:
            return Remediation(
                immediate_actions=[
                    "Verify CoreDNS pods are running healthy in kube-system namespace.",
                    "Confirm target service FQDN format: `<service-name>.<namespace>.svc.cluster.local`.",
                    "Check if CoreDNS is being CPU throttled or dropping DNS requests.",
                ],
                preventative_actions=[
                    "Deploy NodeLocal DNSCache daemonset to handle high DNS query volumes.",
                    "Tune `dnsConfig` `ndots` option to reduce search path amplification.",
                    "Enable connection pooling and runtime DNS caching.",
                ],
                remediation_commands=[
                    "kubectl get pods -n kube-system -l k8s-app=kube-dns",
                    "kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100",
                    "kubectl run dns-test -it --rm --image=busybox:1.28 -- nslookup kubernetes.default",
                ],
            )

        if cat == IncidentCategory.IMAGE_PULL_FAILURE:
            return Remediation(
                immediate_actions=[
                    "Verify the image repository name, tag, and registry URL in deployment spec.",
                    "Check if imagePullSecrets are attached to the Pod or default ServiceAccount.",
                    "Manually test pulling the image from a worker node or container registry.",
                ],
                preventative_actions=[
                    "Use immutable digest hashes or semantic release tags instead of mutable `:latest`.",
                    "Set up automated service account token or robot account rotation for private registries.",
                ],
                remediation_commands=[
                    "kubectl describe pod <pod-name> | grep -A 5 'Events'",
                    "kubectl get secret <image-pull-secret-name> -o yaml",
                ],
            )

        if cat == IncidentCategory.DATABASE_EXHAUSTION:
            return Remediation(
                immediate_actions=[
                    "Check active client connections on the database server.",
                    "Restart leaking pod instances to release idle locked connections.",
                    "Temporarily increase database server `max_connections` if resource limits allow.",
                ],
                preventative_actions=[
                    "Deploy a connection pooler (e.g. PgBouncer, ProxySQL, AWS RDS Proxy) between pods and database.",
                    "Configure strict client-side connection pool maximums (`maxPoolSize`) per pod replica.",
                    "Implement connection timeout and leak detection in the database client library.",
                ],
                remediation_commands=[
                    "kubectl get pods -l app=<db-client-app>",
                    "kubectl rollout restart deployment/<deployment-name>",
                ],
            )

        if cat == IncidentCategory.RBAC_PERMISSION_DENIED:
            return Remediation(
                immediate_actions=[
                    "Check permissions of the ServiceAccount attached to the Pod using `kubectl auth can-i`.",
                    "Inspect the required API group, resource, and verb mentioned in the rejection log.",
                ],
                preventative_actions=[
                    "Apply least-privilege Role / ClusterRole and bind to the specific ServiceAccount.",
                    "Avoid mounting default service account tokens (`automountServiceAccountToken: false`) unless necessary.",
                ],
                remediation_commands=[
                    "kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<namespace>:<serviceaccount>",
                    "kubectl describe rolebinding -n <namespace>",
                ],
            )

        # Default fallback remediation
        return Remediation(
            immediate_actions=[
                "Inspect previous container logs: `kubectl logs <pod-name> --previous`.",
                "Describe the pod events: `kubectl describe pod <pod-name>`.",
            ],
            preventative_actions=[
                "Add structured JSON logging with error context to capture upstream diagnostics.",
                "Review cluster monitoring metrics in Grafana or Cloud Monitoring.",
            ],
            remediation_commands=[
                "kubectl describe pod <pod-name>",
                "kubectl logs <pod-name> --tail=200",
            ],
        )
