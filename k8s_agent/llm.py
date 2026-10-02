"""Optional LLM enhancement layer supporting Gemini, Anthropic, or OpenAI when keys are configured."""

import os
from typing import List, Optional
import requests
from k8s_agent.models import EvidenceItem, RootCause, TimelineEvent


class LLMReasoner:
    """Optional LLM integration to augment deterministic findings with AI synthesis."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")

    def is_available(self) -> bool:
        """Returns True if any supported LLM provider has an API key configured."""
        return bool(self.gemini_key or self.anthropic_key or self.openai_key)

    def enhance_analysis(
        self,
        primary_cause: RootCause,
        evidence: List[EvidenceItem],
        timeline: List[TimelineEvent],
    ) -> str:
        """Invokes the active LLM to generate an executive SRE post-mortem synthesis."""
        if self.gemini_key:
            return self._call_gemini(primary_cause, evidence, timeline)
        if self.anthropic_key:
            return self._call_anthropic(primary_cause, evidence, timeline)
        if self.openai_key:
            return self._call_openai(primary_cause, evidence, timeline)
        return "No LLM provider configured."

    def _build_prompt(
        self,
        primary_cause: RootCause,
        evidence: List[EvidenceItem],
        timeline: List[TimelineEvent],
    ) -> str:
        evidence_summary = "\n".join(
            [
                f"- Line {e.line_number} [{e.rule_name}]: {e.trigger_line.strip()}"
                for e in evidence[:10]
            ]
        )
        timeline_summary = "\n".join(
            [
                f"- Phase {t.phase} (Line {t.line_number}): {t.description}"
                for t in timeline[:10]
            ]
        )

        return f"""You are a Principal Kubernetes Site Reliability Engineer (SRE).
Analyze the following Kubernetes incident data collected deterministically from pod/cluster logs:

PRIMARY ROOT CAUSE IDENTIFIED:
- Category: {primary_cause.category.value}
- Severity: {primary_cause.severity.value}
- Confidence: {primary_cause.confidence_score * 100:.0f}%
- Summary: {primary_cause.summary}
- Blast Radius: {primary_cause.blast_radius}

INCIDENT TIMELINE:
{timeline_summary}

VERBATIM LOG EVIDENCE:
{evidence_summary}

Provide a concise, executive post-mortem narrative covering:
1. Incident Progression & Cascading Effects (How it unfolded)
2. Risk Assessment (Why this happens in production clusters)
3. Advanced SRE Best Practices for permanent mitigation
Keep your response professional, precise, and directly relevant to the evidence provided.
"""

    def _call_gemini(
        self,
        primary_cause: RootCause,
        evidence: List[EvidenceItem],
        timeline: List[TimelineEvent],
    ) -> str:
        prompt = self._build_prompt(primary_cause, evidence, timeline)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000},
        }
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            data = res.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                return f"Unexpected Gemini response structure: {res.text}"
        return f"Gemini API Error (HTTP {res.status_code}): {res.text}"

    def _call_anthropic(
        self,
        primary_cause: RootCause,
        evidence: List[EvidenceItem],
        timeline: List[TimelineEvent],
    ) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.anthropic_key)
            prompt = self._build_prompt(primary_cause, evidence, timeline)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            return f"Anthropic API Error: {str(e)}"

    def _call_openai(
        self,
        primary_cause: RootCause,
        evidence: List[EvidenceItem],
        timeline: List[TimelineEvent],
    ) -> str:
        prompt = self._build_prompt(primary_cause, evidence, timeline)
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1000,
        }
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=20,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
        return f"OpenAI API Error (HTTP {res.status_code}): {res.text}"
