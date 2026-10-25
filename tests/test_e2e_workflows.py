import pytest
import pandas as pd
from datetime import date
from core.db import (
    init_db, get_or_create_student, save_attempt, get_attempts,
    get_dashboard_data, add_review, get_due_reviews, mark_review_done,
    get_review_streak, update_mastery, get_all_mastery,
    save_test_session, get_test_sessions
)
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import complete_review, get_recommendations
from core.learning import build_practice_set, calculate_score

@pytest.fixture(autouse=True)
def setup_isolated_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_e2e.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db

# -------------------------------------------------------------
# 1. OVERVIEW & GREETING WORKFLOW
# -------------------------------------------------------------
def test_overview_first_time_and_returning():
    # First time student
    s_id = get_or_create_student("Alex", "Class 10")
    dash = get_dashboard_data(s_id)
    assert dash["attempts"] == 0
    assert dash["tests"] == 0
    assert dash["topics"] == 0
    assert dash["accuracy"] == 0
    assert dash["due"] == 0

    # Add activity
    save_attempt(s_id, "Mathematics", "Trigonometry", "sin(90)?", "1", "1", True, "recall", "diagnostic")
    dash_after = get_dashboard_data(s_id)
    assert dash_after["attempts"] == 1
    assert dash_after["topics"] == 1
    assert dash_after["accuracy"] == 100

# -------------------------------------------------------------
# 2. GAPFINDER FULL WORKFLOW
# -------------------------------------------------------------
def test_gapfinder_full_cycle():
    s_id = get_or_create_student("Beta", "Class 12")

    # 1. Generate diagnostic (offline fallback or mock)
    questions, source = run_diagnostic(None, "Science", "Cell Respiration", "Standard", 4)
    assert len(questions) == 4

    # 2. Simulate student answering (3 correct, 1 incorrect)
    results = []
    for i, q in enumerate(questions):
        is_corr = (i != 0) # Q0 is wrong
        ans = q["answer"] if is_corr else "Wrong answer"
        results.append({
            "question": q,
            "answer": ans,
            "correct": is_corr
        })
        save_attempt(
            s_id,
            "Science",
            "Cell Respiration",
            q["prompt"],
            ans,
            q["answer"],
            is_corr,
            q.get("mistake_type", "conceptual"),
            mode="diagnostic"
        )

    # 3. Score calculation
    score = calculate_score(results)
    assert score == 75

    # 4. Mistake pattern analysis
    analysis = analyze_test(None, results, "Science", "Cell Respiration")
    assert len(analysis["mistakes"]) > 0
    top_err = analysis["mistakes"][0]

    # 5. Update mastery and schedule review
    update_mastery(s_id, "Science", "Cell Respiration", top_err["type"], top_err["count"], score)
    add_review(s_id, "Science", "Cell Respiration", days=3, reason="Diagnostic 75%")

    # Verify state in DB
    mastery = get_all_mastery(s_id)
    assert len(mastery) == 1
    assert mastery[0]["error_count"] == 1

    due = get_due_reviews(s_id, limit=10)
    # The review is scheduled for 3 days in the future, so not due today
    assert len(due) == 0

    # 6. Targeted practice generation
    practice = build_practice_set("Science", "Cell Respiration", analysis, gemini=None)
    assert len(practice) == 3
    assert all("prompt" in p and "options" in p for p in practice)

# -------------------------------------------------------------
# 3. MARKS ANALYSIS FULL WORKFLOW & DELTA COMPARISON
# -------------------------------------------------------------
def test_marks_analysis_and_progression_comparison():
    s_id = get_or_create_student("Charlie", "Class 10")

    # First test: 12/20 (60%)
    t1_analysis = analyze_test(None, [], "Mathematics", "Quadratics", manual_types=["Calculation / careless error"], score=60)
    save_test_session(s_id, "Mathematics", "Quadratics", 12.0, 20.0, 60, "Calculation / careless error", "Sign slip")
    update_mastery(s_id, "Mathematics", "Quadratics", "calculation", 1, 60)

    # Second test on same topic: 18/20 (90%)
    t2_analysis = analyze_test(None, [], "Mathematics", "Quadratics", manual_types=["Calculation / careless error"], score=90)
    save_test_session(s_id, "Mathematics", "Quadratics", 18.0, 20.0, 90, "Calculation / careless error", "Much better")
    update_mastery(s_id, "Mathematics", "Quadratics", "calculation", 1, 90)

    # Verify history and progression
    history = get_test_sessions(s_id, "Mathematics", "Quadratics", order="ASC")
    assert len(history) == 2
    delta = history[1]["percentage"] - history[0]["percentage"]
    assert delta == 30 # +30 percentage point improvement

# -------------------------------------------------------------
# 4. RECALL & REVISION INTERVAL ADVANCEMENT
# -------------------------------------------------------------
def test_recall_spaced_interval_advancement_and_mastery():
    s_id = get_or_create_student("Dana", "College")

    # Initial review due today
    rid = add_review(s_id, "Physics", "Thermodynamics", days=0, reason="Initial review")
    due = get_due_reviews(s_id)
    assert len(due) == 1

    # Cycle 1: mark reviewed (next interval)
    res1 = complete_review(s_id, rid, "Physics", "Thermodynamics", mastered=False)
    assert res1["status"] == "scheduled"
    assert res1["days"] == 3 # Streak 1 -> 3 days

    streak = get_review_streak(s_id, "Physics", "Thermodynamics")
    assert streak == 1

    # Cycle 2: mark reviewed again
    rid2 = add_review(s_id, "Physics", "Thermodynamics", days=0, reason="Cycle 2")
    res2 = complete_review(s_id, rid2, "Physics", "Thermodynamics", mastered=False)
    assert res2["days"] == 7 # Streak 2 -> 7 days

    # Cycle 3: mark mastered
    rid3 = add_review(s_id, "Physics", "Thermodynamics", days=0, reason="Cycle 3")
    res3 = complete_review(s_id, rid3, "Physics", "Thermodynamics", mastered=True)
    assert res3["status"] == "mastered"
    assert res3["days"] == 0

# -------------------------------------------------------------
# 5. CROSS-PAGE SYNCHRONIZATION
# -------------------------------------------------------------
def test_cross_page_data_synchronization():
    s_id = get_or_create_student("Evan", "Class 12")

    # Add a test session in Marks Analysis
    save_test_session(s_id, "Chemistry", "Organic", 16.0, 20.0, 80, "Misread the question", "Reaction condition")
    update_mastery(s_id, "Chemistry", "Organic", "misread", 2, 80)

    # 1. Verify it shows on Overview dashboard
    dash = get_dashboard_data(s_id)
    assert dash["tests"] == 1
    assert dash["topics"] == 1
    assert dash["accuracy"] == 80

    # 2. Verify it shows in Recall recommendations
    recs = get_recommendations(s_id)
    assert len(recs) == 1
    assert recs[0]["topic"] == "Organic"
    assert "2 recorded mistake(s)" in recs[0]["reason"]

    # 3. Verify it shows in My Progress tests query
    tests = get_test_sessions(s_id, order="DESC")
    assert len(tests) == 1
    assert tests[0]["topic"] == "Organic"

# -------------------------------------------------------------
# 6. IDENTITY & GRADE UPDATE RETENTION
# -------------------------------------------------------------
def test_student_grade_change_retains_data():
    # Student starts in Class 10
    sid_10 = get_or_create_student("Fiona", "Class 10")
    save_attempt(sid_10, "History", "Revolutions", "Q1", "A", "A", True, "recall", "diagnostic")
    save_test_session(sid_10, "History", "Revolutions", 18.0, 20.0, 90, "", "")

    # Student changes stage in UI to Class 12
    sid_12 = get_or_create_student("Fiona", "Class 12")
    assert sid_10 == sid_12

    # Verify attempts and tests are NOT lost
    attempts = get_attempts(sid_12)
    assert len(attempts) == 1
    tests = get_test_sessions(sid_12)
    assert len(tests) == 1
