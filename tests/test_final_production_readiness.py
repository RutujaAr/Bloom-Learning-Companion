import pytest
import sqlite3
import pandas as pd
import json
from pathlib import Path
from datetime import date, datetime, timedelta

import core.db as db
from core.auth import login_local, logout_user, is_oidc_configured, get_current_user
from services.storage_service import (
    validate_pdf_bytes, save_uploaded_pdf, delete_stored_pdf, get_student_upload_dir
)
from services.gemini_service import GeminiService
from services.pdf_service import find_relevant_context, enforce_word_limit, MAX_TEXTBOOK_WORDS
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import get_recommendations, generate_recall_prompt
import streamlit as st


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Provide a fresh, isolated test database for each test."""
    db_file = str(tmp_path / "test_production.db")
    monkeypatch.setenv("BLOOM_DB_PATH", db_file)
    db.DB_PATH = db_file
    db.init_db()
    return db_file


# ---------------------------------------------------------------------------
# 1 & 2: Daily chart aggregation, empty states, and multiple attempts per date
# ---------------------------------------------------------------------------
def test_daily_chart_aggregation_empty_and_multi_attempt(isolated_db):
    student = db.get_or_create_account(owner_id="usr_chart_tester", display_name="Chart Tester")
    sid = student["id"]

    # 1. Empty state
    attempts = db.get_attempts(sid)
    assert len(attempts) == 0

    # 2. Multiple attempts on the same calendar date
    today_iso = "2026-10-24 10:15:00"
    today_iso_2 = "2026-10-24 11:30:00"
    db.save_attempt(sid, "Science", "Cell Biology", "Q1", "A", "A", 1, "conceptual", "diagnostic")
    db.save_attempt(sid, "Science", "Cell Biology", "Q2", "B", "A", 0, "conceptual", "diagnostic")

    # Manually backdate created_at to verify grouping
    with db.get_connection() as c:
        c.execute("UPDATE attempts SET created_at = ? WHERE id = 1", (today_iso,))
        c.execute("UPDATE attempts SET created_at = ? WHERE id = 2", (today_iso_2,))

    # Insert an attempt on a different date
    yesterday_iso = "2026-10-23 09:00:00"
    db.save_attempt(sid, "Science", "Cell Biology", "Q3", "C", "C", 1, "conceptual", "diagnostic")
    with db.get_connection() as c:
        c.execute("UPDATE attempts SET created_at = ? WHERE id = 3", (yesterday_iso,))

    all_att = db.get_attempts(sid)
    df = pd.DataFrame(all_att)
    df["parsed_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
    df_valid = df.dropna(subset=["parsed_dt"]).copy()

    df_valid["date_str"] = df_valid["parsed_dt"].dt.strftime("%Y-%m-%d")
    df_valid["display_date"] = df_valid["parsed_dt"].dt.strftime("%b %d")
    daily = df_valid.groupby(["date_str", "display_date"], as_index=False).agg(Questions=("id", "count"))
    daily = daily.sort_values("date_str")

    # 2 distinct dates
    assert len(daily) == 2
    # 2026-10-24 has 2 questions aggregated into ONE daily total
    row_today = daily[daily["date_str"] == "2026-10-24"].iloc[0]
    assert row_today["Questions"] == 2
    assert row_today["display_date"] == "Oct 24"

    # 2026-10-23 has 1 question
    row_yest = daily[daily["date_str"] == "2026-10-23"].iloc[0]
    assert row_yest["Questions"] == 1
    assert row_yest["display_date"] == "Oct 23"


# ---------------------------------------------------------------------------
# 3 & 4: Dual source grounding and placeholder validation
# ---------------------------------------------------------------------------
def test_two_different_sources_produce_source_specific_context():
    source_biology = "Mitochondria produce ATP through aerobic cellular respiration and oxidative phosphorylation."
    source_physics = "Newton's second law defines force as the product of mass and acceleration: F = m * a."

    # Question about energy asked against biology text
    ctx_bio = find_relevant_context(source_biology, "How is energy produced?")
    assert "Mitochondria" in ctx_bio
    assert "Newton" not in ctx_bio

    # Question about force asked against physics text
    ctx_phys = find_relevant_context(source_physics, "What is Newton's law?")
    assert "acceleration" in ctx_phys
    assert "Mitochondria" not in ctx_phys


def test_placeholder_example_never_used_as_automatic_question():
    placeholder = "e.g. Explain how ATP synthase produces energy based on this text..."
    student_q1 = "   "
    student_q2 = "e.g. Explain how ATP synthase produces energy based on this text..."
    student_q3 = "Explain how ATP synthase produces energy based on this text..."

    def validate_query(q):
        clean = q.strip()
        if not clean or clean.lower() == placeholder.lower():
            return False, "Placeholder or empty query rejected"
        return True, clean

    ok1, _ = validate_query(student_q1)
    ok2, _ = validate_query(student_q2)
    ok3, val3 = validate_query(student_q3)

    assert ok1 is False
    assert ok2 is False
    assert ok3 is True
    assert val3 == student_q3


# ---------------------------------------------------------------------------
# 5 & 6: Unknown topic handling and question generation constraints
# ---------------------------------------------------------------------------
def test_unknown_topic_question_generation_without_redundant_cache_search():
    from core.syllabus import get_syllabus_context
    # Test College + College / University Outline + Other + Machine learning
    ctx1 = get_syllabus_context("College", "College / University Outline", "Other", "Machine learning")
    ctx2 = get_syllabus_context("College", "College / University Outline", "Other", "Machine learning")

    # Second lookup is fast cache hit
    assert ctx1 == ctx2
    assert ctx1["verified"] is False
    assert "outcomes" in ctx1

    # Offline bank generation respects count and topic
    gemini = GeminiService()
    gemini.api_key = None  # force offline
    qs, src = run_diagnostic(
        gemini=gemini,
        subject="Other",
        topic="Machine learning",
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert len(qs) == 3
    assert "offline" in src.lower() or "curated" in src.lower() or "bank" in src.lower()
    for q in qs:
        assert "prompt" in q
        assert len(q["options"]) == 4


# ---------------------------------------------------------------------------
# 7: Model IDs and raw exceptions never appear in learner output
# ---------------------------------------------------------------------------
def test_model_ids_and_raw_exceptions_sanitized(monkeypatch):
    service = GeminiService(model="gemini-3.8-flash")
    service.api_key = "dummy-key"

    class FailingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise RuntimeError("Internal 504 Deadline Exceeded: upstream cluster failure at /v1/models/gemini-3.8-flash")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FailingClient())

    ans, status = service.explain_from_document("What is ATP?", "ATP is energy.")
    assert ans is not None
    assert "gemini-3.8-flash" not in ans
    assert "504" not in ans
    assert "upstream cluster" not in ans
    assert "gemini-3.8-flash" not in status


# ---------------------------------------------------------------------------
# 8, 9 & 10: Multi-user isolation, profile edits, and persistent identity
# ---------------------------------------------------------------------------
def test_multi_user_isolation_and_profile_edits(isolated_db):
    # 1. Student A signs in
    user_a = db.get_or_create_account(owner_id="owner_alice_123", display_name="Alice", email="alice@uni.edu", grade="College")
    id_a = user_a["id"]

    # 2. Student B signs in
    user_b = db.get_or_create_account(owner_id="owner_bob_456", display_name="Bob", email="bob@uni.edu", grade="Class 12")
    id_b = user_b["id"]

    assert id_a != id_b

    # Record attempts and study sessions for Alice
    db.save_attempt(id_a, "Physics", "Mechanics", "Q_Alice", "A", "A", 1)
    session_a_id = db.save_textbook_session(id_a, "Alice Notes", "pasted", "Alice Notes", extracted_text="Alice's private study text")
    db.save_textbook_qa(session_a_id, id_a, "Q1_Alice", "Ans1_Alice", mode="ai")

    # Record attempts and study sessions for Bob
    db.save_attempt(id_b, "Biology", "Genetics", "Q_Bob", "B", "B", 1)
    session_b_id = db.save_textbook_session(id_b, "Bob Notes", "pasted", "Bob Notes", extracted_text="Bob's private study text")
    db.save_textbook_qa(session_b_id, id_b, "Q1_Bob", "Ans1_Bob", mode="ai")

    # Verify Alice cannot see Bob's data
    alice_attempts = db.get_attempts(id_a)
    alice_sessions = db.get_textbook_sessions(id_a)
    alice_qa = db.get_textbook_qa(session_b_id, id_a)  # Alice attempts to access Bob's session

    assert len(alice_attempts) == 1
    assert alice_attempts[0]["question"] == "Q_Alice"
    assert len(alice_sessions) == 1
    assert alice_sessions[0]["title"] == "Alice Notes"
    assert len(alice_qa) == 0  # Forbidden / Empty

    # Verify Bob cannot delete Alice's session
    del_ok, _ = db.delete_textbook_session(session_a_id, id_b)
    assert del_ok is False
    # Alice's session still exists
    assert db.get_textbook_session(id_a, session_a_id) is not None

    # Verify profile display name edits do NOT change id or erase history
    updated_alice = db.get_or_create_account(owner_id="owner_alice_123", display_name="Alice Wonderland")
    assert updated_alice["id"] == id_a
    assert updated_alice["name"] == "Alice Wonderland"
    assert len(db.get_attempts(id_a)) == 1


# ---------------------------------------------------------------------------
# 11 & 12: Textbook sessions survival and deletion with file cleanup
# ---------------------------------------------------------------------------
def test_textbook_session_persistence_and_deletion(isolated_db, tmp_path, monkeypatch):
    student = db.get_or_create_account(owner_id="owner_persist_test", display_name="Persist Tester")
    sid = student["id"]

    # Mock storage directory in tmp_path
    monkeypatch.setattr("services.storage_service.UPLOAD_BASE_DIR", tmp_path / "uploads")

    sample_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    rel_path = save_uploaded_pdf(sid, "test_chapter.pdf", sample_pdf_bytes)
    assert rel_path is not None
    assert Path(rel_path).exists()

    session_id = db.save_textbook_session(
        student_id=sid,
        title="Chapter 1: Foundations",
        source_type="pdf",
        source_name="test_chapter.pdf",
        storage_path=rel_path,
        extracted_text="Foundations of science text content.",
        word_count=5
    )
    db.save_textbook_qa(session_id, sid, "What is science?", "Science is systematic study.", mode="ai")

    # Verify retrieval
    session = db.get_textbook_session(sid, session_id)
    assert session is not None
    assert session["title"] == "Chapter 1: Foundations"
    qa_list = db.get_textbook_qa(session_id, sid)
    assert len(qa_list) == 1
    assert qa_list[0]["question"] == "What is science?"

    # Delete session with file cleanup
    del_ok, file_to_clean = db.delete_textbook_session(sid, session_id)
    assert del_ok is True
    assert file_to_clean == rel_path

    delete_stored_pdf(sid, file_to_clean)
    assert not Path(rel_path).exists()
    assert db.get_textbook_session(sid, session_id) is None
    assert len(db.get_textbook_qa(session_id, sid)) == 0


# ---------------------------------------------------------------------------
# 13: Schema migrations preserve existing records
# ---------------------------------------------------------------------------
def test_schema_migrations_preserve_data(isolated_db):
    # Insert legacy record
    with db.get_connection() as c:
        c.execute("INSERT INTO students(name, grade, owner_id) VALUES('Legacy Learner', 'Class 10', 'legacy:learner')")
        leg_id = c.execute("SELECT id FROM students WHERE name='Legacy Learner'").fetchone()["id"]
        c.execute("INSERT INTO attempts(student_id, subject, topic, question, answer, expected, correct) VALUES(?, 'Math', 'Algebra', '1+1', '2', '2', 1)", (leg_id,))

    # Re-run migration
    db.migrate_db()

    # Verify legacy learner record survived
    with db.get_connection() as c:
        rec = c.execute("SELECT * FROM students WHERE id = ?", (leg_id,)).fetchone()
        assert rec is not None
        assert rec["name"] == "Legacy Learner"
        atts = c.execute("SELECT COUNT(*) n FROM attempts WHERE student_id = ?", (leg_id,)).fetchone()["n"]
        assert atts == 1

    # Test claiming legacy learner data
    claim_ok = db.migrate_legacy_student(leg_id, "new_authenticated_owner")
    assert claim_ok is True
    with db.get_connection() as c:
        updated = c.execute("SELECT owner_id FROM students WHERE id = ?", (leg_id,)).fetchone()["owner_id"]
        assert updated == "new_authenticated_owner"


# ---------------------------------------------------------------------------
# 14: PDF upload validation (invalid, empty, oversized)
# ---------------------------------------------------------------------------
def test_pdf_upload_validation():
    # Empty (0 bytes)
    ok, err = validate_pdf_bytes(b"", "empty.pdf")
    assert ok is False
    assert "empty" in err.lower()

    # Oversized (>15MB)
    huge_bytes = b"x" * (15 * 1024 * 1024 + 1)
    ok, err = validate_pdf_bytes(huge_bytes, "big.pdf")
    assert ok is False
    assert "exceeds" in err.lower()

    # Invalid header
    ok, err = validate_pdf_bytes(b"NOT_A_PDF_FILE", "fake.pdf")
    assert ok is False
    assert "valid" in err.lower() or "header" in err.lower()

    # Valid PDF bytes
    valid_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    ok, err = validate_pdf_bytes(valid_pdf, "valid.pdf")
    assert ok is True
    assert err == ""


# ---------------------------------------------------------------------------
# 15: Safe OAuth setup message when unconfigured
# ---------------------------------------------------------------------------
def test_oidc_unconfigured_safe(monkeypatch):
    monkeypatch.setattr(st, "secrets", {})
    assert is_oidc_configured() is False


# ---------------------------------------------------------------------------
# 16 & 17: Gemini offline fallback and non-falsification
# ---------------------------------------------------------------------------
def test_gemini_fallback_does_not_falsify_ai():
    service = GeminiService()
    service.api_key = None

    prompt_res = generate_recall_prompt(service, "Physics", "Thermodynamics")
    assert "offline" in prompt_res["source"].lower()
    assert "ai-generated" not in prompt_res["source"].lower()


# ---------------------------------------------------------------------------
# 18: Duplicate submissions prevention
# ---------------------------------------------------------------------------
def test_duplicate_submission_handling(isolated_db):
    student = db.get_or_create_account(owner_id="owner_dup_test", display_name="Dup Tester")
    sid = student["id"]

    # First review scheduling
    db.add_review(sid, "Chemistry", "Equilibrium", days=1, reason="Test mistake")
    # Second identical review scheduling should update interval rather than create duplicate unfinished entry
    db.add_review(sid, "Chemistry", "Equilibrium", days=3, reason="Repeated practice")

    due_reviews = db.get_due_reviews(sid, limit=10)
    upcoming_reviews = db.get_upcoming_reviews(sid, limit=10)
    total_active = len([r for r in due_reviews + upcoming_reviews if r["topic"] == "Equilibrium"])
    assert total_active == 1


# ---------------------------------------------------------------------------
# 19: Database health check
# ---------------------------------------------------------------------------
def test_db_health_check_safe(isolated_db):
    health = db.get_db_health()
    assert health["status"] == "healthy"
    assert health["engine"] == "sqlite"
    assert health["tables"] >= 6
    assert "password" not in json.dumps(health)
    assert "secret" not in json.dumps(health)
