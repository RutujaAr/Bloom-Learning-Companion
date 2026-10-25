import pytest
from datetime import date, timedelta
from core.db import (
    init_db, get_or_create_student, add_review, get_due_reviews,
    get_upcoming_reviews, get_completed_reviews, save_recall_session,
    get_recall_sessions, get_previous_questions, save_attempt,
    get_dashboard_data, save_test_session
)
from core.syllabus import get_supported_curricula, get_syllabus_context
from agents.gap_finder import run_diagnostic, normalize_question_prompt
from agents.recall_loop import generate_recall_prompt, complete_recall_session

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_func_improvements.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db

# ---------------------------------------------------------------------------
# 1. Syllabus Alignment Tests
# ---------------------------------------------------------------------------
def test_syllabus_cbse_verified_alignment():
    # Class 10 Real Numbers
    ctx = get_syllabus_context("Class 10", "CBSE (Verified 2024-25)", "Mathematics", "Real Numbers")
    assert ctx["verified"] is True
    assert "cbseacademic.nic.in" in ctx["source"]
    assert "Number Systems" in ctx["unit"]
    assert "Fundamental Theorem of Arithmetic" in ctx["outcomes"]

    # Class 10 Electricity
    ctx_sci = get_syllabus_context("Class 10", "CBSE (Verified 2024-25)", "Science", "Electricity")
    assert ctx_sci["verified"] is True
    assert "Effects of Current" in ctx_sci["unit"]

def test_syllabus_unverified_transparent_disclaimer():
    # Custom/unverified topic
    ctx = get_syllabus_context("College", "Other / General", "Computer Science", "Distributed Consensus")
    assert ctx["verified"] is False
    assert "No verified board syllabus cache found" in ctx["disclaimer"]
    assert "Distributed Consensus" in ctx["unit"]

def test_supported_curricula_list():
    curricula = get_supported_curricula()
    assert len(curricula) >= 4
    assert any("CBSE" in c for c in curricula)
    assert any("ICSE" in c for c in curricula)

# ---------------------------------------------------------------------------
# 2. Question Normalization & Anti-Repetition Tests
# ---------------------------------------------------------------------------
def test_normalize_question_prompt():
    t1 = "  If 2x = 14, what is x?  "
    t2 = "if 2x = 14 what is x"
    assert normalize_question_prompt(t1) == normalize_question_prompt(t2)

def test_gap_finder_anti_repetition_fallback():
    # Pass first question as already seen in previous_questions
    bank_q = "A student solves the quadratic equation 2x² - 8x + 6 = 0 using the quadratic formula. What is the value of the discriminant (b² - 4ac)?"
    questions, status = run_diagnostic(
        gemini=None,
        subject="Mathematics",
        topic="Quadratic Equations",
        level="Standard",
        count=4,
        previous_questions=[bank_q]
    )
    assert len(questions) == 4
    # The first question prompt must not be in the generated batch
    prompts = [q["prompt"] for q in questions]
    assert bank_q not in prompts

def test_gap_finder_question_count_flexibility():
    for requested in [3, 5, 7]:
        questions, _ = run_diagnostic(
            gemini=None,
            subject="Mathematics",
            topic="Algebra",
            level="Standard",
            count=requested
        )
        assert len(questions) == requested

# ---------------------------------------------------------------------------
# 3. Active Recall & Review Separation Tests
# ---------------------------------------------------------------------------
def test_review_separation_due_vs_upcoming_vs_completed():
    sid = get_or_create_student("RecallTester", "Class 10")

    # 1. Add a review due today (days=0)
    rev_today_id = add_review(sid, "Physics", "Light", days=0, reason="Due today test")

    # 2. Add an upcoming review (days=3)
    rev_future_id = add_review(sid, "Chemistry", "Periodic Table", days=3, reason="Future test")

    due = get_due_reviews(sid)
    upcoming = get_upcoming_reviews(sid)
    completed = get_completed_reviews(sid)

    assert len(due) == 1
    assert due[0]["id"] == rev_today_id
    assert len(upcoming) == 1
    assert upcoming[0]["id"] == rev_future_id
    assert len(completed) == 0

    # 3. Complete the due review
    chal = generate_recall_prompt(None, "Physics", "Light")
    res = complete_recall_session(
        student_id=sid,
        review_id=rev_today_id,
        subject="Physics",
        topic="Light",
        prompt=chal["challenge"],
        response="Light travels in straight lines and reflects according to angle i = angle r",
        self_eval="🌟 Mastered"
    )
    assert res["status"] == "mastered"

    # Now verify categories update
    due_after = get_due_reviews(sid)
    completed_after = get_completed_reviews(sid)
    assert len(due_after) == 0
    assert len(completed_after) == 1
    assert completed_after[0]["id"] == rev_today_id

    # Check recall session logged
    sessions = get_recall_sessions(sid)
    assert len(sessions) == 1
    assert sessions[0]["topic"] == "Light"
    assert "straight lines" in sessions[0]["response"]

def test_active_recall_struggled_reschedules_for_tomorrow():
    sid = get_or_create_student("StruggleTester", "Class 12")
    rev_id = add_review(sid, "Mathematics", "Calculus", days=0, reason="Calculus test")

    res = complete_recall_session(
        student_id=sid,
        review_id=rev_id,
        subject="Mathematics",
        topic="Calculus",
        prompt="Explain chain rule",
        response="Forgot the inner derivative",
        self_eval="⚠️ Struggled"
    )
    assert res["status"] == "scheduled"
    assert res["days"] == 1  # Reset to 1 day for urgent repetition

# ---------------------------------------------------------------------------
# 4. Progress Metrics & Topic Deduplication Tests
# ---------------------------------------------------------------------------
def test_dashboard_deduplication_and_metrics():
    sid = get_or_create_student("MetricTester", "Class 10")

    # Save diagnostic attempts on same topic
    save_attempt(sid, "Math", "Algebra", "q1", "a", "a", True, "conceptual", mode="diagnostic")
    save_attempt(sid, "Math", "Algebra", "q2", "b", "c", False, "calculation", mode="diagnostic")
    # Save practice attempt on same topic
    save_attempt(sid, "Math", "algebra", "q3", "d", "d", True, "conceptual", mode="practice")
    # Save test session on same topic
    save_test_session(sid, "Math", "ALGEBRA", scored=18, total=20, percentage=90)

    data = get_dashboard_data(sid)
    # Distinct topic count must be 1 (case-insensitive deduplication)
    assert data["topics"] == 1
    assert data["attempts"] == 3
    assert data["diagnostic_sessions"] == 1
    assert data["practice_questions"] == 1
    assert data["tests"] == 1
