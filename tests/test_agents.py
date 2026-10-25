import pytest
from core.db import init_db, get_or_create_student
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import complete_review, get_recommendations

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_agents.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db

def test_gap_finder_fallback():
    # Pass None for gemini to test deterministic curated fallback
    questions, status = run_diagnostic(None, "Science", "Cell Biology", "Standard", 4)
    assert len(questions) == 4
    assert all("prompt" in q and "options" in q and "answer" in q for q in questions)
    assert "Built-in" in status

def test_paper_pattern_diagnostic_analysis():
    results = [
        {"question": {"mistake_type": "conceptual"}, "correct": False},
        {"question": {"mistake_type": "conceptual"}, "correct": False},
        {"question": {"mistake_type": "calculation"}, "correct": False},
        {"question": {"mistake_type": "conceptual"}, "correct": True},
    ]
    analysis = analyze_test(None, results, "Math", "Algebra")
    assert "mistakes" in analysis
    assert len(analysis["mistakes"]) == 2
    # Conceptual should be top mistake with count 2
    assert analysis["mistakes"][0]["type"] == "conceptual"
    assert analysis["mistakes"][0]["count"] == 2

def test_paper_pattern_score_fallback():
    analysis = analyze_test(None, [], "Math", "Algebra", manual_types=[], score=65)
    assert len(analysis["mistakes"]) > 0
    assert "65%" in analysis["summary"]

def test_recall_loop_spaced_progression():
    sid = get_or_create_student("Frank", "Class 10")
    # Complete review with follow-up
    res1 = complete_review(sid, 1, "Math", "Algebra", mastered=False)
    assert res1["status"] == "scheduled"
    assert res1["days"] >= 1

    # Complete review as mastered
    res2 = complete_review(sid, 2, "Math", "Algebra", mastered=True)
    assert res2["status"] == "mastered"
    assert res2["days"] == 0
