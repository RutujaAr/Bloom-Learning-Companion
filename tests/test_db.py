import pytest
import sqlite3
import os
from pathlib import Path
from core.db import (
    init_db, get_or_create_student, save_attempt, get_attempts,
    get_dashboard_data, add_review, get_due_reviews, mark_review_done,
    get_review_streak, update_mastery, get_all_mastery,
    save_test_session, get_test_sessions
)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_bloom.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db

def test_student_grade_preservation():
    s1 = get_or_create_student("Alice", "Class 10")
    s2 = get_or_create_student("Alice", "Class 12")
    # Same student ID should be returned when grade is updated
    assert s1 == s2

def test_attempt_and_dashboard():
    sid = get_or_create_student("Bob", "Class 10")
    save_attempt(sid, "Math", "Algebra", "2+2?", "4", "4", True, "conceptual", "diagnostic")
    save_attempt(sid, "Math", "Algebra", "3*3?", "6", "9", False, "calculation", "diagnostic")

    attempts = get_attempts(sid)
    assert len(attempts) == 2

    dash = get_dashboard_data(sid)
    assert dash["attempts"] == 2
    assert dash["accuracy"] == 50
    assert dash["topics"] == 1

def test_reviews_and_streak():
    sid = get_or_create_student("Charlie", "College")
    rid = add_review(sid, "Physics", "Mechanics", days=0, reason="Initial review")
    assert rid is not None

    due = get_due_reviews(sid)
    assert len(due) == 1
    assert due[0]["topic"] == "Mechanics"

    streak_before = get_review_streak(sid, "Physics", "Mechanics")
    assert streak_before == 0

    mark_review_done(sid, rid)
    streak_after = get_review_streak(sid, "Physics", "Mechanics")
    assert streak_after == 1

def test_mastery_tracking():
    sid = get_or_create_student("Dana", "Research")
    update_mastery(sid, "Chemistry", "Bonding", "conceptual", error_count=1, score=60)
    update_mastery(sid, "Chemistry", "Bonding", "conceptual", error_count=2, score=75)

    mastery = get_all_mastery(sid)
    assert len(mastery) == 1
    assert mastery[0]["error_count"] == 3
    assert mastery[0]["latest_score"] == 75

def test_test_sessions():
    sid = get_or_create_student("Eve", "Class 12")
    save_test_session(sid, "Math", "Calculus", 15, 20, 75, "calculation", "Minor arithmetic error")
    save_test_session(sid, "Math", "Calculus", 18, 20, 90, "conceptual", "Better concept grasp")

    sessions = get_test_sessions(sid, "Math", "Calculus")
    assert len(sessions) == 2
    assert sessions[0]["percentage"] == 75
    assert sessions[1]["percentage"] == 90
