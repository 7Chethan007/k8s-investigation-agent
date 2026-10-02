"""Unit tests for the optional LLMReasoner integration."""

from unittest.mock import MagicMock, patch
from k8s_agent.llm import LLMReasoner
from k8s_agent.models import (
    EvidenceItem,
    IncidentCategory,
    RootCause,
    Severity,
    TimelineEvent,
)


def test_llm_availability():
    llm_none = LLMReasoner()
    assert llm_none.is_available() is False

    llm_gemini = LLMReasoner(gemini_api_key="test-key")
    assert llm_gemini.is_available() is True


@patch("requests.post")
def test_gemini_call(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "SRE Analysis: Memory leak occurred during batch ETL ingestion."}]
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    llm = LLMReasoner(gemini_api_key="fake-gemini-key")
    rc = RootCause(
        category=IncidentCategory.OOM_KILLED,
        severity=Severity.CRITICAL,
        confidence_score=0.98,
        title="Oom Killed",
        summary="Cgroup limit hit",
        blast_radius="Container terminated",
    )
    evidence = [
        EvidenceItem(
            line_number=10,
            trigger_line="exit code 137",
            rule_name="OOM_EXIT_CODE_137",
            explanation="OOM",
        )
    ]
    timeline = [
        TimelineEvent(
            line_number=10,
            phase="CRASH_EVENT",
            description="Killed by cgroup",
            severity=Severity.CRITICAL,
        )
    ]

    analysis = llm.enhance_analysis(rc, evidence, timeline)
    assert "SRE Analysis" in analysis
    assert mock_post.called


@patch("requests.post")
def test_openai_call(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "OpenAI SRE Post-Mortem Note"}}]
    }
    mock_post.return_value = mock_response

    llm = LLMReasoner(openai_api_key="fake-openai-key")
    rc = RootCause(
        category=IncidentCategory.CRASH_LOOP_BACKOFF,
        severity=Severity.CRITICAL,
        confidence_score=0.95,
        title="Crashloop",
        summary="Crashing",
        blast_radius="All pods down",
    )

    analysis = llm.enhance_analysis(rc, [], [])
    assert "OpenAI SRE Post-Mortem Note" in analysis
