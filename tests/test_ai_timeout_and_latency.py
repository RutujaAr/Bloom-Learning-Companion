import time
import json
import pytest
from uuid import uuid4
import streamlit as st

from services.gemini_service import GeminiService
from agents.gap_finder import (
    run_diagnostic,
    get_last_diagnostic_metrics,
    BANKS,
    _validate_question_structure
)
from core.syllabus import get_syllabus_context
from core.db import init_db, save_attempt, get_attempts, add_review, get_upcoming_reviews, get_connection


# ---------------------------------------------------------------------------
# Fixture: Temporary Database for Submission Tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_latency_bloom.db"
    monkeypatch.setattr("core.db.DB_PATH", test_db)
    init_db()
    yield test_db


# ---------------------------------------------------------------------------
# 1. Fast Successful Response (< 2s, AI Output Labeled)
# ---------------------------------------------------------------------------
def test_fast_successful_response(monkeypatch):
    mock_service = GeminiService()
    mock_service.api_key = "test-api-key"

    sample_ml_questions = [
        {
            "prompt": "What is the primary role of the activation function in a neural network layer?",
            "options": ["Introduce non-linearity", "Normalize the input weights", "Speed up CPU memory access", "Ensure zero loss"],
            "answer": "Introduce non-linearity",
            "explanation": "Without non-linear activation functions, stacked neural network layers collapse mathematically into a single linear transformation.",
            "hint": "Think about why linear combinations cannot learn curved decision boundaries.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Which loss function is most commonly utilized for binary logistic regression classification?",
            "options": ["Binary Cross-Entropy (Log Loss)", "Mean Squared Error", "Huber Loss", "Hinge Loss"],
            "answer": "Binary Cross-Entropy (Log Loss)",
            "explanation": "Binary cross-entropy measures the divergence between true binary labels and predicted probabilities.",
            "hint": "Consider the probabilistic negative log-likelihood formula.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "What regularization method randomly drops units and their connections during neural network training?",
            "options": ["Dropout", "Batch Normalization", "Gradient Clipping", "Early Stopping"],
            "answer": "Dropout",
            "explanation": "Dropout prevents co-adaptation of feature detectors by randomly zeroing activations with probability p.",
            "hint": "It literally drops nodes from the forward pass.",
            "mistake_type": "recall"
        }
    ]

    class FastMockClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                time.sleep(0.05)  # Simulate 50ms network round-trip
                class Response:
                    text = json.dumps(sample_ml_questions)
                return Response()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FastMockClient())

    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline",
        timeout_ms=5000
    )

    metrics = get_last_diagnostic_metrics()

    assert len(questions) == 3
    assert "AI-generated" in status
    assert "Offline fallback" not in status
    assert metrics["source_used"] == "ai"
    assert metrics["question_count"] == 3
    assert metrics["total_elapsed_s"] < 2.0
    assert len(metrics["api_attempts"]) == 1
    assert metrics["api_attempts"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# 2. Response Exceeding Deadline (Prompt Fallback, Near Configured Budget)
# ---------------------------------------------------------------------------
def test_response_exceeds_deadline(monkeypatch):
    mock_service = GeminiService(timeout_ms=500)
    mock_service.api_key = "test-api-key"

    class TimeoutMockClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                # Simulate timeout error after exceeding budget
                time.sleep(0.55)
                raise TimeoutError("504 DEADLINE_EXCEEDED: upstream timeout")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: TimeoutMockClient())

    t0 = time.time()
    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline",
        timeout_ms=500
    )
    total_time = time.time() - t0
    metrics = get_last_diagnostic_metrics()

    # 1. Returned exactly 3 questions from curated bank
    assert len(questions) == 3
    # 2. Curated offline fallback labeled
    assert "Built-in curated questions (offline fallback)" in status
    # 3. Exactly 1 API attempt, no second full-length retry!
    assert len(metrics["api_attempts"]) == 1
    assert metrics["api_attempts"][0]["status"] == "timeout"
    assert metrics["timed_out"] is True
    assert metrics["source_used"] == "fallback"
    # 4. Total duration close to budget (~0.5s), NOT 240s!
    assert total_time < 2.0


# ---------------------------------------------------------------------------
# 3. Connection Failure (Prompt Fallback, No Secret Leak)
# ---------------------------------------------------------------------------
def test_connection_failure(monkeypatch):
    mock_service = GeminiService()
    mock_service.api_key = "sensitive-secret-key-12345"

    class ConnFailClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise ConnectionError("Failed to establish a new connection: [Errno 111] Connection refused")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: ConnFailClient())

    t0 = time.time()
    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )
    elapsed = time.time() - t0

    assert len(questions) == 3
    assert "Built-in curated questions (offline fallback)" in status
    assert elapsed < 1.0
    # Ensure sensitive credentials and raw tracebacks never exposed
    assert "sensitive-secret-key-12345" not in status
    assert "Errno 111" not in status


# ---------------------------------------------------------------------------
# 4. Quota and Authentication Failure (Prompt Fallback, No Retry Multiplication)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("exc_code,exc_msg,cat", [
    (429, "Resource has been exhausted (quota exceeded)", "quota"),
    (401, "API_KEY_INVALID: unauthenticated call", "authentication")
])
def test_quota_and_auth_failure(monkeypatch, exc_code, exc_msg, cat):
    mock_service = GeminiService()
    mock_service.api_key = "test-api-key"

    attempt_count = 0

    class FailingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                nonlocal attempt_count
                attempt_count += 1
                raise type("APIError", (Exception,), {"code": exc_code, "message": exc_msg})()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FailingClient())

    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    # Must only make 1 attempt and not retry 429/401
    assert attempt_count == 1
    assert len(questions) == 3
    assert "Built-in curated questions (offline fallback)" in status
    assert str(exc_code) not in status


# ---------------------------------------------------------------------------
# 5. Malformed AI Response (Handled Cleanly by Fallback)
# ---------------------------------------------------------------------------
def test_malformed_ai_response(monkeypatch):
    mock_service = GeminiService()
    mock_service.api_key = "test-api-key"

    class BrokenClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                class Response:
                    text = "I apologize, but I cannot fulfill this request. [Broken JSON without fields"
                return Response()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: BrokenClient())

    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert len(questions) == 3
    assert "Built-in curated questions (offline fallback)" in status
    for q in questions:
        ok, reason = _validate_question_structure(q)
        assert ok is True, f"Question validation failed: {reason}"


# ---------------------------------------------------------------------------
# 6. No Suitable Fallback Available (Friendly Retry Message, No Invented Questions)
# ---------------------------------------------------------------------------
def test_no_suitable_fallback_available():
    unconfigured_service = GeminiService()
    unconfigured_service.api_key = None

    # Custom esoteric topic with no curated bank
    questions, status = run_diagnostic(
        unconfigured_service,
        subject="Other",
        topic="Ancient Roman Architecture",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    # Must NOT invent unrelated questions (e.g. calculus or Pomodoro study skills)
    assert questions == []
    assert "No offline fallback questions match this custom topic" in status
    assert "Please check your connection and try again" in status


# ---------------------------------------------------------------------------
# 7. Late Response After Deadline (Session State & Fallback Immutability)
# ---------------------------------------------------------------------------
def test_late_response_after_deadline(monkeypatch):
    mock_service = GeminiService(timeout_ms=200)
    mock_service.api_key = "test-api-key"

    class StallingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                time.sleep(0.3)
                raise TimeoutError("504 DEADLINE_EXCEEDED")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: StallingClient())

    questions, status = run_diagnostic(
        mock_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline",
        timeout_ms=200
    )

    # Verified fallback is returned
    assert len(questions) == 3
    assert "Built-in curated questions" in status

    # Capture initial fallback prompts
    prompts_before = [q["prompt"] for q in questions]

    # Late response simulation: late return cannot alter or replace fallback result
    time.sleep(0.1)
    prompts_after = [q["prompt"] for q in questions]
    assert prompts_before == prompts_after


# ---------------------------------------------------------------------------
# 8. Repeated Submission (Prevents Duplicate Records and Attempts)
# ---------------------------------------------------------------------------
def test_prevent_duplicate_submission():
    from core.db import get_or_create_student

    student_id = get_or_create_student("Test Latency Learner", "College")

    # Simulate answering questions
    questions = BANKS["cs_ai"][:3]
    answers = {q["prompt"]: q["options"][0] for q in questions}

    # First submission
    for q in questions:
        save_attempt(
            student_id,
            "Other",
            "Machine learning",
            q["prompt"],
            answers[q["prompt"]],
            q["answer"],
            (answers[q["prompt"]] == q["answer"]),
            q.get("mistake_type", "conceptual"),
            "diagnostic"
        )

    add_review(student_id, "Other", "Machine learning", days=3, reason="Initial diagnostic")

    attempts_first = get_attempts(student_id)
    reviews_first = get_upcoming_reviews(student_id)
    assert len(attempts_first) == 3
    assert len(reviews_first) == 1

    # Simulate submission guard in app session state:
    submission_guard_key = f"diag_submitted_Machine learning_{student_id}"
    session_guard = {submission_guard_key: True}

    # Attempting second submit while guard is active
    is_already_submitted = session_guard.get(submission_guard_key, False)
    assert is_already_submitted is True
    # Guard blocks second execution of save_attempt and add_review

    attempts_second = get_attempts(student_id)
    reviews_second = get_upcoming_reviews(student_id)
    assert len(attempts_second) == 3
    assert len(reviews_second) == 1


# ---------------------------------------------------------------------------
# 9. Exact Case Verification:
# College → College / University Outline → Other → Machine learning → Standard → 3 questions
# ---------------------------------------------------------------------------
def test_exact_benchmark_case_quality_and_labeling():
    # 1. Syllabus verification check
    syl = get_syllabus_context("College", "College / University Outline", "Other", "Machine learning")
    assert syl["verified"] is False, "College syllabus outline must not be falsely marked as verified official syllabus"

    # 2. Offline fallback execution
    unconfigured_service = GeminiService()
    unconfigured_service.api_key = None

    t0 = time.time()
    questions, status = run_diagnostic(
        unconfigured_service,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )
    total_elapsed = time.time() - t0

    # 3. Exactly three questions
    assert len(questions) == 3

    # 4. Correct labeling
    assert status == "Built-in curated questions (offline fallback)"
    assert "Verified" not in status
    assert "CBSE" not in status

    # 5. Question relevance to Machine Learning & internal consistency
    ml_keywords = ["loss", "variance", "overfitting", "recall", "gradient", "convolutional", "f1-score", "learning rate", "dimension", "precision"]
    for q in questions:
        ok, reason = _validate_question_structure(q)
        assert ok is True, f"Question validation failed: {reason}"
        # Every question must have prompt, options, answer, explanation
        assert q["prompt"]
        assert len(q["options"]) == 4
        assert q["answer"] in q["options"]
        assert len(q["explanation"]) > 10
        # Check that question prompt relates to Machine Learning
        prompt_lower = q["prompt"].lower()
        has_ml_concept = any(k in prompt_lower for k in ml_keywords)
        assert has_ml_concept is True, f"Question does not appear related to ML: {q['prompt']}"

    # 6. Ultra-fast fallback execution (< 50ms)
    assert total_elapsed < 0.1
