import pytest
import sqlite3
from datetime import date, timedelta
from core.db import (
    init_db, get_or_create_student, save_attempt, get_attempts,
    add_review, get_due_reviews, get_upcoming_reviews, get_completed_reviews,
    save_recall_session, get_recall_sessions, get_dashboard_data,
    save_test_session, get_previous_questions
)
from services.pdf_service import (
    MAX_TEXTBOOK_WORDS, count_words, enforce_word_limit,
    extract_pdf_text, search_text_by_keywords, find_relevant_context
)
from agents.gap_finder import run_diagnostic, normalize_question_prompt, BANKS, _validate_question_structure
from agents.recall_loop import generate_recall_prompt, complete_recall_session
from services.gemini_service import GeminiService

@pytest.fixture(autouse=True)
def setup_isolated_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "final_integration.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db

# ---------------------------------------------------------------------------
# 1. Textbook Helper: Limits, Truncation & Non-AI Keyword Search
# ---------------------------------------------------------------------------
def test_textbook_word_count_and_truncation():
    sample_text = "This is a test lesson about thermodynamics and energy conservation."
    assert count_words(sample_text) == 10
    assert count_words("") == 0
    assert count_words(None) == 0

    # Short text within limit
    accepted, total, is_truncated = enforce_word_limit(sample_text, max_words=50)
    assert accepted == sample_text
    assert total == 10
    assert is_truncated is False

    # Text exceeding word limit
    long_text = " ".join([f"word{i}" for i in range(100)])
    accepted_long, total_long, is_truncated_long = enforce_word_limit(long_text, max_words=25)
    assert total_long == 100
    assert is_truncated_long is True
    assert count_words(accepted_long) == 25
    assert accepted_long == " ".join([f"word{i}" for i in range(25)])

def test_textbook_non_ai_keyword_search():
    sample_text = """Photosynthesis occurs in the chloroplasts of plant cells. Chlorophyll absorbs blue and red light from the sun.

Cellular respiration occurs in the mitochondria to produce ATP energy from glucose molecules.

The Krebs cycle and oxidative phosphorylation take place within the inner mitochondrial matrix."""

    # Search for photosynthesis
    res1 = search_text_by_keywords(sample_text, "How does photosynthesis absorb light?")
    assert len(res1) > 0
    assert "chloroplasts" in res1[0]["excerpt"]
    assert any("photosynthesis" in m or "light" in m for m in res1[0]["matches"])

    # Search for ATP
    res2 = search_text_by_keywords(sample_text, "What produces ATP energy?")
    assert len(res2) > 0
    assert "mitochondria" in res2[0]["excerpt"]

    # Search for unrelated keywords
    res3 = search_text_by_keywords(sample_text, "quantum mechanics wave function collapse")
    assert len(res3) == 0

def test_empty_and_corrupt_pdf_extraction():
    # Empty bytes
    txt, msg = extract_pdf_text(b"")
    assert txt == ""
    assert "Empty file" in msg

    # Random corrupt bytes
    txt_corrupt, msg_corrupt = extract_pdf_text(b"Not a valid PDF byte sequence at all")
    assert txt_corrupt == ""
    assert "could not be read" in msg_corrupt

# ---------------------------------------------------------------------------
# 2. Question Banks & Schema Integrity
# ---------------------------------------------------------------------------
def test_all_bank_questions_have_valid_structure_and_answers():
    for subject, questions in BANKS.items():
        assert len(questions) >= 4, f"Bank for {subject} must contain at least 4 curated questions"
        for q in questions:
            ok, err = _validate_question_structure(q)
            assert ok, f"Question validation failed for {subject}: {err} on prompt '{q.get('prompt')}'"
            assert len(q["options"]) == 4, f"Options must be 4 choices for prompt: {q['prompt']}"
            assert q["answer"] in q["options"], f"Answer must exactly match one option for: {q['prompt']}"
            assert q.get("explanation"), f"Must have explanation for: {q['prompt']}"
            assert q.get("hint"), f"Must have hint for: {q['prompt']}"
            assert q.get("mistake_type") in ["conceptual", "calculation", "misread", "recall", "incomplete"]

# ---------------------------------------------------------------------------
# 3. Question Deduplication & Changing Counts
# ---------------------------------------------------------------------------
def test_question_deduplication_when_changing_count():
    sid = get_or_create_student("CountTester", "Class 10")

    # Learner completes initial 3 questions
    qs1, _ = run_diagnostic(None, "Mathematics", "Algebra", "Standard", count=3)
    assert len(qs1) == 3

    # Save attempts for batch 1
    for q in qs1:
        save_attempt(sid, "Mathematics", "Algebra", q["prompt"], q["answer"], q["answer"], True, "conceptual", mode="diagnostic")

    # Fetch previous questions
    prev = get_previous_questions(sid, "Algebra")
    assert len(prev) == 3

    # Now learner changes question count to 4 for the same topic
    qs2, _ = run_diagnostic(None, "Mathematics", "Algebra", "Standard", count=4, previous_questions=prev)
    assert len(qs2) == 4

    # Ensure none of the newly served questions duplicate the previous 3
    prompts_batch1 = {normalize_question_prompt(q["prompt"]) for q in qs1}
    prompts_batch2 = [normalize_question_prompt(q["prompt"]) for q in qs2]

    # At least the fresh questions must avoid the previous batch
    overlap = [p for p in prompts_batch2 if p in prompts_batch1]
    assert len(overlap) == 0, f"Expected 0 overlapping questions, found: {overlap}"

# ---------------------------------------------------------------------------
# 4. Spaced Repetition Lifecycle & Review Categorisation
# ---------------------------------------------------------------------------
def test_spaced_repetition_lifecycle_and_due_filtering():
    sid = get_or_create_student("SpacedStudent", "Class 10")
    today_str = date.today().isoformat()
    future_str = (date.today() + timedelta(days=3)).isoformat()

    # Create due review and future review
    due_id = add_review(sid, "Science", "Optics", days=0, reason="Needs review")
    future_id = add_review(sid, "Math", "Trigonometry", days=3, reason="Scheduled spaced review")

    due_list = get_due_reviews(sid)
    upcoming_list = get_upcoming_reviews(sid)
    completed_list = get_completed_reviews(sid)

    assert len(due_list) == 1
    assert due_list[0]["id"] == due_id
    assert len(upcoming_list) == 1
    assert upcoming_list[0]["id"] == future_id
    assert len(completed_list) == 0

    # Execute active recall with Moderate/Recalled outcome
    res = complete_recall_session(
        student_id=sid,
        review_id=due_id,
        subject="Science",
        topic="Optics",
        prompt="Explain Snell's law",
        response="n1 sin(theta1) = n2 sin(theta2)",
        self_eval="👍 Recalled"
    )
    assert res["status"] == "scheduled"
    assert res["days"] >= 1

    # After recall: due must be 0, completed must be 1, upcoming must now be 2
    assert len(get_due_reviews(sid)) == 0
    assert len(get_completed_reviews(sid)) == 1
    assert len(get_upcoming_reviews(sid)) == 2

    # Verify session log entry
    sessions = get_recall_sessions(sid)
    assert len(sessions) == 1
    assert sessions[0]["topic"] == "Optics"
    assert "Snell" in sessions[0]["prompt"]

# ---------------------------------------------------------------------------
# 5. Persistence Across App Restarts & Cross-Page State
# ---------------------------------------------------------------------------
def test_persistence_across_simulated_restart(tmp_path):
    restart_db = str(tmp_path / "restart_test.db")
    import core.db
    core.db.DB_PATH = restart_db
    init_db()

    # Session 1: Create student and learning history
    s_id = get_or_create_student("PersistentLearner", "Class 12")
    save_attempt(s_id, "Physics", "Thermodynamics", "What is dQ?", "dU + dW", "dU + dW", True, "conceptual", mode="diagnostic")
    save_attempt(s_id, "Physics", "Thermodynamics", "Efficiency formula", "1 - Tc/Th", "1 - Tc/Th", True, "recall", mode="practice")
    save_test_session(s_id, "Physics", "Thermodynamics", scored=18.0, total=20.0, percentage=90)
    add_review(s_id, "Physics", "Thermodynamics", days=0, reason="Diagnostic 100%")
    save_recall_session(s_id, None, "Physics", "Thermodynamics", "State 1st Law", "Energy is conserved", "🌟 Mastered")

    # Simulate app exit & restart by re-initializing DB and querying afresh
    init_db()
    dash = get_dashboard_data(s_id)
    assert dash["attempts"] == 2
    assert dash["practice_questions"] == 1
    assert dash["diagnostic_sessions"] == 1
    assert dash["tests"] == 1
    assert dash["topics"] == 1  # Deduplicated across diagnostic, practice, and test
    assert dash["accuracy"] == 100
    assert len(get_due_reviews(s_id)) == 1
    assert len(get_recall_sessions(s_id)) == 1
