import pytest
import sqlite3
import os
import streamlit as st
from pathlib import Path
from core.db import (
    init_db, connect, get_or_create_student, save_attempt, get_attempts,
    get_dashboard_data, save_test_session, get_test_sessions,
    save_textbook_session, get_textbook_sessions, get_textbook_session,
    delete_textbook_session, save_textbook_qa, get_textbook_qa,
    save_important_concept, get_saved_concepts, get_saved_concept_count,
    delete_saved_concept, get_student_by_username, get_student_by_id,
    get_student_by_owner_id, create_user_account
)
from core.auth import (
    create_account, authenticate_user, hash_password, verify_password,
    login_session, logout_user, get_current_user
)


@pytest.fixture
def auth_db(tmp_path, monkeypatch):
    """Isolated database fixture for clean test runs."""
    test_db = str(tmp_path / "test_auth_bloom.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()
    yield test_db


def test_1_successful_new_account_registration(auth_db):
    """1. Successful new account registration with unique username, password hash, display name, and grade."""
    student = create_account(
        username="maya_patel",
        password="securePassword123",
        display_name="Maya Patel",
        grade="Class 12",
        email="maya@example.edu"
    )
    assert student is not None
    assert student["id"] > 0
    assert student["username"] == "maya_patel"
    assert student["name"] == "Maya Patel"
    assert student["grade"] == "Class 12"
    assert student["owner_id"].startswith("usr_")

    # Verify password was hashed with bcrypt (never plaintext)
    assert student["password_hash"] != "securePassword123"
    assert student["password_hash"].startswith("$2b$")
    assert verify_password("securePassword123", student["password_hash"]) is True


def test_2_registration_rejected_for_already_used_username(auth_db):
    """2. Registration rejected for an already-used username."""
    create_account(
        username="arav_k",
        password="passwordOne1",
        display_name="Arav Kumar",
        grade="College"
    )

    with pytest.raises(ValueError) as exc_info:
        create_account(
            username="arav_k",
            password="differentPassword2",
            display_name="Another Arav",
            grade="Class 10"
        )
    assert str(exc_info.value) == "This username is already taken. Please choose another."


def test_3_two_accounts_with_same_display_name_and_grade(auth_db):
    """3. Two accounts with the same display name and grade."""
    user1 = create_account(
        username="rohan_north",
        password="passRohan1",
        display_name="Rohan Sharma",
        grade="Class 10"
    )
    user2 = create_account(
        username="rohan_south",
        password="passRohan2",
        display_name="Rohan Sharma",
        grade="Class 10"
    )

    assert user1["id"] != user2["id"]
    assert user1["username"] != user2["username"]
    assert user1["owner_id"] != user2["owner_id"]
    assert user1["name"] == user2["name"] == "Rohan Sharma"
    assert user1["grade"] == user2["grade"] == "Class 10"


def test_4_successful_login_to_existing_account(auth_db):
    """4. Successful login to an existing account."""
    created = create_account(
        username="priya_chem",
        password="organicChem2026",
        display_name="Priya Nair",
        grade="College"
    )

    authenticated = authenticate_user("priya_chem", "organicChem2026")
    assert authenticated is not None
    assert authenticated["id"] == created["id"]
    assert authenticated["username"] == "priya_chem"
    assert authenticated["owner_id"] == created["owner_id"]


def test_5_repeated_login_returning_same_account_and_progress(auth_db):
    """5. Repeated login returning the same account and progress."""
    student = create_account(
        username="dev_anand",
        password="password1234",
        display_name="Dev Anand",
        grade="College"
    )
    sid = student["id"]

    # Record learning progress
    save_attempt(sid, "Physics", "Thermodynamics", "What is entropy?", "Degree of disorder", "Degree of disorder", 1)
    save_test_session(sid, "Physics", "Thermodynamics", 18, 20, 90, "conceptual", "Solid understanding")

    # Login #1
    login1 = authenticate_user("dev_anand", "password1234")
    assert login1["id"] == sid
    dash1 = get_dashboard_data(login1["id"])
    assert dash1["attempts"] == 1

    # Login #2
    login2 = authenticate_user("dev_anand", "password1234")
    assert login2["id"] == sid
    dash2 = get_dashboard_data(login2["id"])
    assert dash2["attempts"] == 1
    assert dash2["tests"] == 1


def test_6_incorrect_password_handling(auth_db):
    """6. Incorrect password handling without leaking information."""
    create_account(
        username="ananya_b",
        password="correctPassword1",
        display_name="Ananya",
        grade="Class 12"
    )

    # Wrong password returns None
    result_wrong = authenticate_user("ananya_b", "incorrectPassword")
    assert result_wrong is None

    # Non-existent user returns None
    result_missing = authenticate_user("unknown_user_999", "anyPassword")
    assert result_missing is None


def test_7_logout_and_subsequent_login(auth_db):
    """7. Logout and subsequent login."""
    student = create_account(
        username="kunal_m",
        password="kunalPass123",
        display_name="Kunal M",
        grade="College"
    )

    # Login session
    login_session(student)
    assert st.session_state.get("auth_user")["authenticated"] is True
    assert st.session_state.get("student_id") == student["id"]

    # Logout
    logout_user()
    assert "auth_user" not in st.session_state
    assert "student_id" not in st.session_state

    # Subsequent login restores session safely
    relogin = authenticate_user("kunal_m", "kunalPass123")
    assert relogin is not None
    login_session(relogin)
    assert st.session_state.get("auth_user")["authenticated"] is True
    assert st.session_state.get("student_id") == student["id"]


def test_8_preservation_of_existing_rutuja_records_during_migration(monkeypatch):
    """8. Preservation of existing Rutuja records during migration."""
    # Run test directly on the real workspace bloom.db
    real_db = str(Path(__file__).resolve().parent.parent / "bloom.db")
    monkeypatch.setenv("BLOOM_DB_PATH", real_db)
    import core.db
    core.db.DB_PATH = real_db
    init_db()

    rutuja_student = get_student_by_username("rutuja")
    assert rutuja_student is not None
    assert rutuja_student["id"] == 4
    assert rutuja_student["owner_id"] == "usr_rutuja_test"
    assert rutuja_student["name"] == "Rutuja"
    assert rutuja_student["grade"] == "College"
    assert rutuja_student["email"] == "rutuja@example.edu"

    # Authenticate Rutuja with her migrated password
    authed = authenticate_user("rutuja", "rutuja123")
    assert authed is not None
    assert authed["id"] == 4

    # Verify student 3 (Class 10) was preserved separately and not merged
    student3 = get_student_by_id(3)
    assert student3 is not None
    assert student3["grade"] == "Class 10"
    assert student3["owner_id"] == "legacy_3"
    assert student3["username"] == "rutuja_class10"


def test_9_isolation_of_dashboards_marks_attempts_documents_textbook_history(auth_db):
    """9. Isolation of dashboards, marks, attempts, documents, and textbook history between two users."""
    u1 = create_account("student_one", "passOne1", "Student One", "College")
    u2 = create_account("student_two", "passTwo2", "Student Two", "College")

    # User 1 actions
    save_attempt(u1["id"], "Biology", "Genetics", "Mendel laws?", "3 laws", "3 laws", 1)
    save_test_session(u1["id"], "Biology", "Genetics", 20, 20, 100, "", "")
    s1_id = save_textbook_session(u1["id"], "Genetics Chapter", "pdf", "genetics.pdf", "Genetics text content", "/path/to/genetics.pdf")
    save_textbook_qa(s1_id, u1["id"], "What is an allele?", "Alternative form of a gene", "ai")

    # User 2 actions
    save_attempt(u2["id"], "Chemistry", "Organic", "What is benzene?", "C6H6", "C6H6", 1)
    save_test_session(u2["id"], "Chemistry", "Organic", 15, 20, 75, "", "")
    s2_id = save_textbook_session(u2["id"], "Organic Chapter", "pdf", "organic.pdf", "Organic text content", "/path/to/organic.pdf")
    save_textbook_qa(s2_id, u2["id"], "What is resonance?", "Delocalized electron structure", "ai")

    # Verify User 1 sees ONLY User 1 data
    u1_attempts = get_attempts(u1["id"])
    assert len(u1_attempts) == 1
    assert u1_attempts[0]["topic"] == "Genetics"

    u1_tests = get_test_sessions(u1["id"])
    assert len(u1_tests) == 1
    assert u1_tests[0]["percentage"] == 100

    u1_sessions = get_textbook_sessions(u1["id"])
    assert len(u1_sessions) == 1
    assert u1_sessions[0]["title"] == "Genetics Chapter"

    u1_qa = get_textbook_qa(s1_id, u1["id"])
    assert len(u1_qa) == 1
    assert u1_qa[0]["question"] == "What is an allele?"

    # User 2 cannot access User 1's textbook session or QA
    cross_session = get_textbook_session(u2["id"], s1_id)
    assert cross_session is None

    cross_qa = get_textbook_qa(s1_id, u2["id"])
    assert len(cross_qa) == 0


def test_10_saving_first_through_fourth_important_concepts(auth_db):
    """10. Saving the first through fourth important concepts."""
    student = create_account("learner_concepts", "pass1234", "Concept Learner", "College")
    sid = student["id"]

    c1 = save_important_concept(sid, "Biology", "ATP Synthase", "How is ATP synthesized via chemiosmosis?", "Crucial exam topic")
    assert c1["id"] > 0
    assert get_saved_concept_count(sid) == 1

    c2 = save_important_concept(sid, "Biology", "Glycolysis", "What is the net ATP yield of glycolysis?", "2 ATP")
    assert get_saved_concept_count(sid) == 2

    c3 = save_important_concept(sid, "Chemistry", "Electronegativity", "Periodic trend of electronegativity", "Increases left to right")
    assert get_saved_concept_count(sid) == 3

    c4 = save_important_concept(sid, "Physics", "Lenz's Law", "Direction of induced EMF", "Opposes changing flux")
    assert get_saved_concept_count(sid) == 4

    saved = get_saved_concepts(sid)
    assert len(saved) == 4
    assert [c["concept_name"] for c in saved] == ["ATP Synthase", "Glycolysis", "Electronegativity", "Lenz's Law"]


def test_11_blocking_fifth_item_until_one_deleted(auth_db):
    """11. Blocking the fifth item until one of the four is deleted."""
    student = create_account("learner_max4", "pass1234", "Max Concept Learner", "College")
    sid = student["id"]

    # Save 4 items
    for i in range(1, 5):
        save_important_concept(sid, "Topic", f"Concept {i}", f"Question {i}", f"Note {i}")

    assert get_saved_concept_count(sid) == 4

    # Attempt 5th item
    with pytest.raises(ValueError) as exc_info:
        save_important_concept(sid, "Topic", "Concept 5", "Question 5", "Note 5")
    assert str(exc_info.value) == "You have saved four important concepts. Delete one to add a new concept."
    assert get_saved_concept_count(sid) == 4


def test_12_saving_replacement_after_deletion(auth_db):
    """12. Saving a replacement after deletion."""
    student = create_account("learner_replace", "pass1234", "Replace Learner", "College")
    sid = student["id"]

    concepts = []
    for i in range(1, 5):
        c = save_important_concept(sid, "Topic", f"Concept {i}", f"Question {i}", f"Note {i}")
        concepts.append(c)

    # Delete 1 concept
    deleted = delete_saved_concept(sid, concepts[0]["id"])
    assert deleted is True
    assert get_saved_concept_count(sid) == 3

    # Add replacement
    replacement = save_important_concept(sid, "Topic", "Concept 5 (Replacement)", "Replacement Question", "New Note")
    assert replacement["id"] > 0
    assert get_saved_concept_count(sid) == 4

    all_current = get_saved_concepts(sid)
    names = [c["concept_name"] for c in all_current]
    assert "Concept 1" not in names
    assert "Concept 5 (Replacement)" in names


def test_13_persistence_of_saved_concepts_and_textbook_history_after_restart(auth_db):
    """13. Persistence of saved concepts and textbook history after restart."""
    student = create_account("persist_user", "persistPass1", "Persist User", "College")
    sid = student["id"]

    s_id = save_textbook_session(sid, "Quantum Mechanics", "pasted", "Lecture Notes", "Wave function collapse text")
    save_textbook_qa(s_id, sid, "What is superposition?", "Linear combination of states", "ai")
    c = save_important_concept(sid, "Quantum Mechanics", "Superposition", "Define superposition mathematically", "Review matrix form")

    # Simulate app restart by establishing a fresh database connection
    conn = connect()
    row_session = conn.execute("SELECT * FROM textbook_sessions WHERE id=? AND student_id=?", (s_id, sid)).fetchone()
    assert row_session is not None
    assert row_session["title"] == "Quantum Mechanics"

    row_qa = conn.execute("SELECT * FROM textbook_qa WHERE session_id=? AND student_id=?", (s_id, sid)).fetchall()
    assert len(row_qa) == 1
    assert row_qa[0]["question"] == "What is superposition?"

    row_concept = conn.execute("SELECT * FROM saved_concepts WHERE id=? AND student_id=?", (c["id"], sid)).fetchone()
    assert row_concept is not None
    assert row_concept["concept_name"] == "Superposition"
    conn.close()


def test_14_preventing_cross_user_read_or_delete_of_concepts_or_sessions(auth_db):
    """14. Preventing one user from reading or deleting another user's saved concepts or sessions."""
    user_a = create_account("user_alpha", "alphaPass1", "Alpha", "College")
    user_b = create_account("user_beta", "betaPass1", "Beta", "College")

    # Alpha creates concept and textbook session
    concept_a = save_important_concept(user_a["id"], "AI", "Transformers", "Self-attention mechanism formula", "")
    session_a = save_textbook_session(user_a["id"], "Deep Learning", "pdf", "dl.pdf", "Deep learning text")

    # Beta attempts to delete Alpha's concept -> must fail and return False
    del_concept_fail = delete_saved_concept(user_b["id"], concept_a["id"])
    assert del_concept_fail is False
    assert get_saved_concept_count(user_a["id"]) == 1

    # Beta attempts to delete Alpha's session -> must fail and return (False, None)
    del_session_fail, _ = delete_textbook_session(session_a, user_b["id"])
    assert del_session_fail is False
    assert len(get_textbook_sessions(user_a["id"])) == 1

    # Beta cannot query Alpha's session
    assert get_textbook_session(user_b["id"], session_a) is None


def test_15_friendly_error_handling_without_exposing_traceback(auth_db):
    """15. Friendly error handling without exposing tracebacks in the user interface."""
    # Username required
    with pytest.raises(ValueError) as e1:
        create_account("", "pass123", "Name", "College")
    assert "Username is required" in str(e1.value)

    # Password required
    with pytest.raises(ValueError) as e2:
        create_account("valid_user", "", "Name", "College")
    assert "Password is required" in str(e2.value)

    # Duplicate username gives friendly message
    create_account("unique_handle", "pass1234", "Name", "College")
    with pytest.raises(ValueError) as e3:
        create_account("unique_handle", "pass1234", "Name", "College")
    assert str(e3.value) == "This username is already taken. Please choose another."

    # Invalid login returns None safely (UI shows "Invalid username or password. Please try again.")
    assert authenticate_user("unique_handle", "wrongPass") is None
    assert authenticate_user("nonexistent_handle", "anyPass") is None
