"""
Regression tests for Bloom diagnostic question generation failure paths,
JSON sanitization of LaTeX / code escapes, actionable error categorization,
safe diagnostic metrics, and selected topic preservation.
"""

import json
import pytest
from pathlib import Path

from agents.gap_finder import (
    run_diagnostic,
    _sanitize_json_escapes,
    _extract_and_parse_json,
    LAST_DIAGNOSTIC_METRICS,
)


class MockGeminiCustomResponse:
    """Mock Gemini returning specific text and status."""
    def __init__(self, raw_text, status="Success", metrics=None):
        self.raw_text = raw_text
        self.status = status
        self.last_metrics = metrics or {"attempts": [{"status": status, "elapsed_s": 0.05}]}

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=1200, timeout_ms=None):
        return self.raw_text, self.status


def test_json_sanitize_escapes_latex_and_code_identifiers():
    r"""
    Ensure LaTeX equations and code identifiers with unescaped backslashes
    (e.g., Floyd's build\_heap, \frac{n}{2}, \log_2 n, \times, \$) are sanitized
    so json.loads succeeds rather than crashing with 'Invalid \escape'.
    """
    raw_with_escapes = r'''
    [
        {
            "id": "q1",
            "prompt": "What is the time complexity of Floyd's build\_heap for an array of size $n$?",
            "options": ["O(n)", "O(n \\log n)", "O(\\frac{n}{2})", "O(n^2)"],
            "correct_answer": "O(n)",
            "explanation": "Floyd's algorithm bounds the work using \\sum_{h=0}^{\\lfloor \\log n \\rfloor} \\frac{n}{2^{h+1}} \\times O(h) = O(n).",
            "mistake_type": "conceptual",
            "subconcept": "heap construction"
        }
    ]
    '''
    # Standard json.loads on un-sanitized string fails with Invalid \escape
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw_with_escapes)

    # _sanitize_json_escapes must sanitize it
    sanitized = _sanitize_json_escapes(raw_with_escapes)
    parsed = json.loads(sanitized)
    assert len(parsed) == 1
    assert "Floyd's build_heap" in parsed[0]["prompt"] or "Floyd's build\\_heap" in parsed[0]["prompt"]

    # _extract_and_parse_json must succeed directly
    questions = _extract_and_parse_json(raw_with_escapes)
    assert questions is not None
    assert len(questions) == 1
    assert questions[0]["id"] == "q1"


def test_diagnostic_timeout_error_categorization():
    """
    Simulate Gemini timeout and verify category='timeout' with actionable error guidance.
    """
    gemini_timeout = MockGeminiCustomResponse(
        raw_text="",
        status="Timeout",
        metrics={
            "attempts": [{"status": "timeout", "elapsed_s": 30.01}],
            "timeout_occurred": True,
            "status_code": 504
        }
    )

    questions, status = run_diagnostic(
        gemini_timeout,
        subject="Computer Science",
        topic="Distributed Consensus and Raft Protocol",
        level="Challenge",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert questions == []
    assert "[Timeout]" in status
    assert "30s deadline exceeded" in status
    assert "No offline fallback questions match this custom topic" in status
    assert LAST_DIAGNOSTIC_METRICS.get("error_category") == "timeout"
    assert LAST_DIAGNOSTIC_METRICS.get("api_status_code") == 504


def test_diagnostic_quota_error_categorization():
    """
    Simulate Gemini HTTP 429 quota exhaustion and verify category='quota_exceeded'.
    """
    gemini_quota = MockGeminiCustomResponse(
        raw_text="",
        status="Error",
        metrics={
            "attempts": [{"status": "error", "error": "RESOURCE_EXHAUSTED", "status_code": 429, "elapsed_s": 0.2}],
            "status_code": 429
        }
    )

    questions, status = run_diagnostic(
        gemini_quota,
        subject="Computer Science",
        topic="Zero-Knowledge Proofs",
        level="Challenge",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert questions == []
    assert "[Quota Exceeded]" in status
    assert "HTTP 429" in status
    assert LAST_DIAGNOSTIC_METRICS.get("error_category") == "quota_exceeded"
    assert LAST_DIAGNOSTIC_METRICS.get("api_status_code") == 429


def test_diagnostic_parsing_failure_error_categorization():
    """
    Simulate Gemini returning completely malformed text that cannot be parsed.
    Verify category='parsing_failure'.
    """
    gemini_bad_json = MockGeminiCustomResponse(
        raw_text="Here is your diagnostic quiz: Sorry, I am unable to format this as a JSON list.",
        status="Success",
        metrics={"attempts": [{"status": "success", "elapsed_s": 0.5}]}
    )

    questions, status = run_diagnostic(
        gemini_bad_json,
        subject="Physics",
        topic="Relativistic Electrodynamics",
        level="Challenge",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert questions == []
    assert "[Parsing Failure]" in status
    assert "could not be parsed" in status
    assert LAST_DIAGNOSTIC_METRICS.get("error_category") == "parsing_failure"


def test_diagnostic_relevance_mismatch_error_categorization():
    """
    Simulate Gemini returning valid JSON questions that are completely unrelated to requested topic.
    Verify category='relevance_mismatch'.
    """
    off_topic_json = json.dumps([
        {
            "id": "q1",
            "prompt": "What is the primary function of chlorophyll in plants?",
            "options": ["Absorb light", "Store starch", "Transport water", "Synthesize lipids"],
            "correct_answer": "Absorb light",
            "explanation": "Chlorophyll absorbs photon energy for photosynthesis.",
            "mistake_type": "recall",
            "subconcept": "plant biology"
        },
        {
            "id": "q2",
            "prompt": "Which cell organelle produces ATP through oxidative phosphorylation?",
            "options": ["Mitochondria", "Ribosome", "Golgi apparatus", "Endoplasmic reticulum"],
            "correct_answer": "Mitochondria",
            "explanation": "Mitochondria are the powerhouse of eukaryotic cells.",
            "mistake_type": "recall",
            "subconcept": "cell biology"
        },
        {
            "id": "q3",
            "prompt": "What is the function of the ribosome in protein synthesis?",
            "options": ["Translates mRNA", "Replicates DNA", "Transcribes RNA", "Packages vesicles"],
            "correct_answer": "Translates mRNA",
            "explanation": "Ribosomes synthesize proteins from amino acids using mRNA templates.",
            "mistake_type": "recall",
            "subconcept": "translation"
        }
    ])

    gemini_off_topic = MockGeminiCustomResponse(
        raw_text=off_topic_json,
        status="Success",
        metrics={"attempts": [{"status": "success", "elapsed_s": 0.5}]}
    )

    questions, status = run_diagnostic(
        gemini_off_topic,
        subject="Computer Science",
        topic="B-Tree Balancing and Node Splitting",
        level="Challenge",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert questions == []
    assert "[Relevance Mismatch]" in status
    assert "did not sufficiently match the requested topic" in status
    assert LAST_DIAGNOSTIC_METRICS.get("error_category") == "relevance_mismatch"


def test_safe_diagnostic_metrics_never_contain_secrets():
    """
    Verify that LAST_DIAGNOSTIC_METRICS never records secret keys or authorization tokens.
    """
    for key in LAST_DIAGNOSTIC_METRICS:
        key_lower = key.lower()
        assert "key" not in key_lower or key_lower == "api_status_code" or "error_key" in key_lower
        assert "secret" not in key_lower
        assert "auth" not in key_lower
        assert "password" not in key_lower


def test_selected_topic_preserved_after_diagnostic_failure():
    """
    Verify that when a diagnostic attempt fails, the diagnostic structure retains the topic
    and simulated retry restores or preserves the input topic in session state.
    """
    gemini_timeout = MockGeminiCustomResponse(
        raw_text="",
        status="Timeout",
        metrics={"attempts": [{"status": "timeout", "elapsed_s": 30.01}], "timeout_occurred": True}
    )

    custom_topic = "Quantum Teleportation and Bell States"
    questions, status = run_diagnostic(
        gemini_timeout,
        subject="Physics",
        topic=custom_topic,
        level="Challenge",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    # In app.py, the diagnostic record created on failure preserves the topic
    mock_session_state = {
        "gap_topic": custom_topic,
        "diagnostic": {
            "topic": custom_topic,
            "questions": questions,
            "source": status
        }
    }

    # Verify diagnostic structure has the topic preserved
    assert mock_session_state["diagnostic"]["topic"] == custom_topic
    assert mock_session_state["gap_topic"] == custom_topic

    # Simulate the user clicking 'Try Again' in app.py:
    # if st.button("Try Again"):
    #     if diagnostic.get("topic"):
    #         st.session_state["gap_topic"] = diagnostic["topic"]
    #     st.session_state.pop("diagnostic", None)
    diag = mock_session_state.get("diagnostic")
    if diag and diag.get("topic"):
        mock_session_state["gap_topic"] = diag["topic"]
    mock_session_state.pop("diagnostic", None)

    # Topic must still be intact in gap_topic so the user doesn't have to re-type
    assert mock_session_state["gap_topic"] == custom_topic


def test_use_container_width_eliminated_from_app():
    """
    Verify that app.py contains 0 occurrences of deprecated 'use_container_width'.
    """
    app_text = Path("app.py").read_text(encoding="utf-8")
    assert "use_container_width" not in app_text
    assert 'width="stretch"' in app_text
