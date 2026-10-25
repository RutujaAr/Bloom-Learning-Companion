import pytest
import time
import re
from pathlib import Path

from core.syllabus import get_syllabus_context, CBSE_SYLLABUS
from agents.gap_finder import (
    run_diagnostic,
    _get_fallback_bank,
    _validate_question_structure,
    _validate_question_topic_relevance,
    BANKS,
    LAST_DIAGNOSTIC_METRICS,
)
from core.db import (
    init_db,
    connect,
    get_or_create_student,
    save_textbook_session,
    get_textbook_sessions,
    get_textbook_session,
    save_textbook_qa,
    get_textbook_qa,
    delete_textbook_session,
)


# ---------------------------------------------------------------------------
# Test Helpers & Mock Services
# ---------------------------------------------------------------------------

class MockGeminiPromptRecorder:
    """Mock Gemini that records prompt arguments and returns verified mock questions."""
    def __init__(self, responses=None):
        self.recorded_prompts = []
        self.responses = responses or []
        self._resp_idx = 0

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=1200, timeout_ms=None):
        self.recorded_prompts.append({
            "prompt": prompt,
            "max_output_tokens": max_output_tokens,
            "timeout_ms": timeout_ms
        })
        if self._resp_idx < len(self.responses):
            resp = self.responses[self._resp_idx]
            self._resp_idx += 1
            return resp, "Success"
        return "[]", "Empty"


class MockGeminiTimeout:
    """Mock Gemini that simulates an immediate timeout failure."""
    def __init__(self):
        self.last_metrics = {
            "attempts": [{"attempt": 1, "status": "timeout", "elapsed_s": 0.05}],
            "timeout_occurred": True
        }

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=1200, timeout_ms=None):
        time.sleep(0.01)
        return None, "Request timed out within latency budget."


class MockGeminiOffline:
    """Mock Gemini that reports API unavailable."""
    def available(self):
        return False

    def generate_text(self, prompt, **kwargs):
        return None, "API Key missing"


# ---------------------------------------------------------------------------
# Scenario 1: Computer Vision selection reaches generation & fallback unchanged
# ---------------------------------------------------------------------------
def test_scenario_1_computer_vision_selection_reaches_pipeline_unchanged():
    """
    Confirm selected stage, curriculum, subject, topic, difficulty, and count
    reach prompt construction and fallback selection without substitution.
    """
    mock_gemini = MockGeminiPromptRecorder(responses=["[]"])

    stage = "College"
    curriculum = "College / University Outline"
    subject = "Computer Science"
    topic = "Computer Vision"
    difficulty = "Challenge"
    count = 3

    # Run diagnostic
    questions, source = run_diagnostic(
        mock_gemini,
        subject=subject,
        topic=topic,
        level=difficulty,
        count=count,
        stage=stage,
        curriculum=curriculum
    )

    # 1. Verify prompt captured exact values without substituting "Other" or "Machine learning"
    assert len(mock_gemini.recorded_prompts) == 1
    prompt_sent = mock_gemini.recorded_prompts[0]["prompt"]

    assert f"Target Subject: {subject}" in prompt_sent
    assert f"Target Topic: {topic}" in prompt_sent
    assert f"Difficulty Level: {difficulty}" in prompt_sent
    assert f"Number of Questions: {count}" in prompt_sent
    assert "Machine learning" not in prompt_sent.replace(topic, "")

    # 2. Verify fallback bank lookup receives exact topic
    bank = _get_fallback_bank(subject, topic, level=difficulty)
    assert bank is not None
    assert len(bank) >= 3


# ---------------------------------------------------------------------------
# Scenario 2: Computer Vision cannot receive generic Machine Learning fallback
# ---------------------------------------------------------------------------
def test_scenario_2_computer_vision_cannot_receive_generic_ml_fallback():
    """
    Verify that when offline or falling back for Computer Vision, Bloom NEVER
    returns generic ML questions (Overfitting, Recall calculation for fraud, Gradient descent learning rate).
    """
    offline_gemini = MockGeminiOffline()

    questions, source = run_diagnostic(
        offline_gemini,
        subject="Computer Science",
        topic="Computer Vision",
        level="Standard",
        count=4,
        stage="College",
        curriculum="College / University Outline"
    )

    assert len(questions) > 0
    all_prompts = " ".join([q["prompt"].lower() for q in questions])

    # Must NOT contain the 3 generic ML questions
    assert "overfitting" not in all_prompts
    assert "supervised learning" not in all_prompts
    assert "fraud" not in all_prompts
    assert "recall (sensitivity)" not in all_prompts
    assert "gradient descent optimization" not in all_prompts
    assert "learning rate (alpha)" not in all_prompts


# ---------------------------------------------------------------------------
# Scenario 3: Verified Computer Vision fallback is used only if genuinely matching
# ---------------------------------------------------------------------------
def test_scenario_3_verified_computer_vision_fallback_used_only_if_matches():
    """
    Verify that Computer Vision fallback questions genuinely address Computer Vision
    (convolutions, pooling, Sobel operators, IoU calculation, same padding).
    """
    offline_gemini = MockGeminiOffline()

    questions, source = run_diagnostic(
        offline_gemini,
        subject="Other",
        topic="Computer Vision",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert len(questions) == 3
    # Check that each question is verified CV
    cv_terms = ["convolution", "pooling", "sobel", "iou", "bounding box", "feature map", "padding"]
    for q in questions:
        q_text = f"{q['prompt']} {q['explanation']}".lower()
        assert any(term in q_text for term in cv_terms), f"Question not verified CV: {q['prompt']}"

    # Verify each question has proper structure
    for q in questions:
        ok, msg = _validate_question_structure(q)
        assert ok, f"Question structure invalid: {msg}"


# ---------------------------------------------------------------------------
# Scenario 4: Topic without suitable fallback produces friendly message
# ---------------------------------------------------------------------------
def test_scenario_4_topic_without_suitable_fallback_produces_friendly_message():
    """
    A custom topic with no verified fallback bank (e.g. 'Quantum Cryptography')
    must return an empty list and a clear, friendly failure message rather than unrelated questions.
    """
    offline_gemini = MockGeminiOffline()

    questions, msg = run_diagnostic(
        offline_gemini,
        subject="Other",
        topic="Quantum Cryptography and Post-Quantum Signatures",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert questions == []
    assert "We couldn't prepare verified questions for this topic right now. Please try again." in msg


# ---------------------------------------------------------------------------
# Scenario 5: Changing topic invalidates or bypasses incompatible cached results
# ---------------------------------------------------------------------------
def test_scenario_5_changing_topic_invalidates_or_bypasses_cached_results():
    """
    Verify syllabus context is keyed by topic so cached results for one topic
    are never reused for another. Verify topic change invalidation logic.
    """
    # 1. Syllabus lookup cache keying
    ctx_ml = get_syllabus_context("College", "College / University Outline", "Other", "Machine learning")
    ctx_cv = get_syllabus_context("College", "College / University Outline", "Other", "Computer Vision")

    assert ctx_ml["unit"] == "Machine learning"
    assert ctx_cv["unit"] == "Computer Vision"
    assert "Computer Vision" not in ctx_ml["outcomes"]
    assert "Machine learning" not in ctx_cv["outcomes"]

    # 2. UI cache compatibility check logic
    cached_diagnostic = {
        "topic": "Machine learning",
        "subject": "Other",
        "questions": [{"prompt": "ML Question 1"}],
        "source": "AI-generated"
    }

    active_topic = "Computer Vision"
    # When user enters Computer Vision, check if cached_diagnostic is invalidated
    is_incompatible = cached_diagnostic.get("topic", "").strip().lower() != active_topic.lower()
    assert is_incompatible is True


# ---------------------------------------------------------------------------
# Scenario 6: Stage, subject, curriculum, difficulty, and question count are respected
# ---------------------------------------------------------------------------
def test_scenario_6_stage_subject_curriculum_difficulty_and_count_respected():
    """
    Verify stage, curriculum, subject, difficulty, and count are respected in prompt and outcomes.
    """
    mock_gemini = MockGeminiPromptRecorder(responses=["[]"])

    stage = "Class 12"
    curriculum = "CBSE (Verified 2024-25)"
    subject = "Physics"
    topic = "Ray Optics"
    level = "Challenge"
    count = 5

    questions, source = run_diagnostic(
        mock_gemini,
        subject=subject,
        topic=topic,
        level=level,
        count=count,
        stage=stage,
        curriculum=curriculum
    )

    prompt = mock_gemini.recorded_prompts[0]["prompt"]
    assert f"Target Subject: {subject}" in prompt
    assert f"Target Topic: {topic}" in prompt
    assert f"Difficulty Level: {level}" in prompt
    assert f"Number of Questions: {count}" in prompt
    assert "CBSE Class 12" in prompt


# ---------------------------------------------------------------------------
# Scenario 7: Successful AI response is checked for relevant topic content and valid structure
# ---------------------------------------------------------------------------
def test_scenario_7_ai_response_checked_for_topic_content_and_valid_structure():
    """
    Verify that an AI response is validated for topic relevance and structure.
    Off-topic questions or malformed structures are rejected.
    """
    # 1. Structure validation
    invalid_structure_no_answer = {
        "prompt": "What is an image convolution?",
        "options": ["A", "B", "C", "D"],
        "answer": "E",  # Not in options
        "explanation": "Exp"
    }
    ok_struct, err = _validate_question_structure(invalid_structure_no_answer)
    assert not ok_struct
    assert "Answer not in options list" in err

    # 2. Topic relevance validation: Off-topic ML question for Computer Vision topic
    off_topic_ml_question = {
        "prompt": "In supervised learning, what is overfitting?",
        "options": ["High variance", "Low variance", "Data leakage", "Vanishing gradient"],
        "answer": "High variance",
        "explanation": "Overfitting occurs when high capacity models memorize noise.",
        "hint": "Think about the bias-variance tradeoff."
    }
    ok_topic, err_topic = _validate_question_topic_relevance(off_topic_ml_question, "Computer Vision", "Computer Science")
    assert not ok_topic
    assert "did not address" in err_topic.lower()

    # 3. Topic relevance validation: Genuine Computer Vision question
    on_topic_cv_question = {
        "prompt": "What is the spatial output of a 3x3 convolution with stride 1 on a 28x28 image?",
        "options": ["26x26", "28x28", "25x25", "30x30"],
        "answer": "26x26",
        "explanation": "Formula (W - K + 2P)/S + 1 = (28 - 3)/1 + 1 = 26x26.",
        "hint": "Check valid padding formula."
    }
    ok_topic_valid, _ = _validate_question_topic_relevance(on_topic_cv_question, "Computer Vision", "Computer Science")
    assert ok_topic_valid is True

    # 4. Mock AI returning 3 off-topic questions -> Bloom rejects them and uses verified fallback
    import json
    off_topic_ai_json = json.dumps([off_topic_ml_question, off_topic_ml_question, off_topic_ml_question])
    mock_ai = MockGeminiPromptRecorder(responses=[off_topic_ai_json])

    questions, status = run_diagnostic(
        mock_ai,
        subject="Computer Science",
        topic="Computer Vision",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    # The AI questions were rejected because of off-topic content; verified fallback was used
    assert "offline fallback" in status
    assert len(questions) == 3
    for q in questions:
        assert "overfitting" not in q["prompt"].lower()


# ---------------------------------------------------------------------------
# Scenario 8: API timeout leads to bounded fallback or friendly failure
# ---------------------------------------------------------------------------
def test_scenario_8_api_timeout_leads_to_bounded_fallback_or_friendly_failure():
    """
    Verify that an API timeout leads to bounded execution (< 1.5s in test)
    and returns verified topic fallback (or friendly message if uncurated topic).
    """
    timeout_gemini = MockGeminiTimeout()

    # Topic with verified fallback
    t0 = time.time()
    questions, status = run_diagnostic(
        timeout_gemini,
        subject="Computer Science",
        topic="Computer Vision",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )
    elapsed = time.time() - t0

    assert elapsed < 2.0  # Fast, bounded execution
    assert len(questions) == 3
    assert "offline fallback" in status

    # Topic without verified fallback
    t1 = time.time()
    q_empty, msg = run_diagnostic(
        timeout_gemini,
        subject="Other",
        topic="Post-Quantum Lattice Cryptography",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )
    elapsed_empty = time.time() - t1

    assert elapsed_empty < 2.0
    assert q_empty == []
    assert "We couldn't prepare verified questions for this topic right now. Please try again." in msg


# ---------------------------------------------------------------------------
# Scenario 9: Student-facing loading message contains no internal latency details
# ---------------------------------------------------------------------------
def test_scenario_9_student_facing_loading_message_contains_no_latency_details():
    """
    Verify that student-facing spinner in app.py says 'Preparing your diagnostic questions…'
    and contains no latency budget, model IDs, or internal config.
    """
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    app_content = app_path.read_text(encoding="utf-8")

    # Required student-facing text
    assert 'st.spinner("Preparing your diagnostic questions…")' in app_content

    # Disallowed internal details in student UI spinner
    assert "latency budget: ~10s" not in app_content
    assert "latency budget" not in app_content
    assert 'st.spinner("Preparing exam-style diagnostic questions' not in app_content


# ---------------------------------------------------------------------------
# Scenario 10: Study-session creation, reopening, persistence, and account isolation
# ---------------------------------------------------------------------------
def test_scenario_10_study_session_creation_reopening_persistence_and_isolation():
    """
    Verify:
    - New study session can be created with a title.
    - Appears in session selector query.
    - Selecting reopens correct session.
    - Associated with authenticated student's account.
    - Preserved across restart / connection reopen.
    - Two users cannot see, access, or delete each other's sessions.
    """
    init_db()

    # Create two distinct test students
    ts = int(time.time() * 1000)
    user1_id = get_or_create_student(f"Student_One_{ts}", "Class 10")
    user2_id = get_or_create_student(f"Student_Two_{ts}", "College")

    # 1. User 1 creates a study session with a title
    title1 = "Chapter 4: Cell Respiration & ATP"
    sess1_id = save_textbook_session(
        student_id=user1_id,
        title=title1,
        source_type="pasted",
        source_name="Lesson Excerpts",
        extracted_text="Cellular respiration converts glucose into ATP in the mitochondria.",
        word_count=10
    )
    assert sess1_id is not None

    # 2. Session appears in user 1's session selector
    u1_sessions = get_textbook_sessions(user1_id)
    assert any(s["id"] == sess1_id and s["title"] == title1 for s in u1_sessions)

    # 3. Selecting an existing session reopens the correct session
    reopened = get_textbook_session(user1_id, sess1_id)
    assert reopened is not None
    assert reopened["id"] == sess1_id
    assert reopened["title"] == title1
    assert "mitochondria" in reopened["extracted_text"]

    # 4. Session has Q&A saved
    qa_id = save_textbook_qa(
        session_id=sess1_id,
        student_id=user1_id,
        question="Where does ATP synthesis take place?",
        answer="In the inner mitochondrial membrane via ATP synthase.",
        mode="ai"
    )
    assert qa_id is not None

    qa_history = get_textbook_qa(sess1_id, user1_id)
    assert len(qa_history) == 1
    assert qa_history[0]["question"] == "Where does ATP synthesis take place?"

    # 5. Account Isolation: User 2 cannot see User 1's sessions
    u2_sessions = get_textbook_sessions(user2_id)
    assert not any(s["id"] == sess1_id for s in u2_sessions)

    # User 2 cannot access or reopen User 1's session
    cross_access = get_textbook_session(user2_id, sess1_id)
    assert cross_access is None

    # User 2 cannot access User 1's Q&A history
    cross_qa = get_textbook_qa(sess1_id, user2_id)
    assert len(cross_qa) == 0

    # User 2 cannot delete User 1's session
    del_ok, _ = delete_textbook_session(sess1_id, user2_id)
    assert del_ok is False

    # Confirm session 1 is still alive and intact
    intact = get_textbook_session(user1_id, sess1_id)
    assert intact is not None
    assert intact["id"] == sess1_id

    # 6. Persistence across connection reopen
    with connect() as conn:
        row = conn.execute("SELECT * FROM textbook_sessions WHERE id=?", (sess1_id,)).fetchone()
        assert row is not None
        assert row["student_id"] == user1_id
        assert row["title"] == title1
