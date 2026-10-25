import pytest
import sqlite3
from core.db import (
    init_db, connect, save_attempt, get_attempts, get_dashboard_data,
    save_textbook_session, get_textbook_sessions, get_textbook_session,
    save_textbook_qa, get_textbook_qa, delete_textbook_session,
    save_important_concept, get_saved_concepts, get_saved_concept_count,
    delete_saved_concept, get_student_by_username, get_student_by_id
)
from core.auth import (
    create_account, authenticate_user, login_session, logout_user
)


def test_complete_e2e_user_flow(tmp_path, monkeypatch):
    """
    Complete end-to-end user flow test:
    create account → logout → login → open textbook history → save four concepts →
    attempt a fifth → delete one → add a replacement → verify persistence →
    sign in as a second user with the same display name → verify data isolation.
    """
    test_db = str(tmp_path / "test_flow.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    init_db()

    # 1. Create Account
    u1 = create_account(
        username="rutuja_patil",
        password="CollegePassword#2026",
        display_name="Rutuja",
        grade="College",
        email="rutuja@example.edu"
    )
    assert u1 is not None
    assert u1["username"] == "rutuja_patil"
    assert u1["name"] == "Rutuja"
    assert u1["grade"] == "College"
    u1_id = u1["id"]

    # 2. Logout
    login_session(u1)
    logout_user()

    # 3. Login
    u1_login = authenticate_user("rutuja_patil", "CollegePassword#2026")
    assert u1_login is not None
    assert u1_login["id"] == u1_id
    assert u1_login["name"] == "Rutuja"
    login_session(u1_login)

    # 4. Open Textbook History
    sess_id = save_textbook_session(
        student_id=u1_id,
        title="Chapter 3: Thermodynamics & Heat Engines",
        source_type="pdf",
        source_name="physics_ch3.pdf",
        extracted_text="Entropy is a measure of molecular disorder and irreversible energy dissipation...",
        file_path="/uploads/student_1/physics_ch3.pdf",
        total_words=2400,
        accepted_words=2400,
        is_truncated=0
    )
    save_textbook_qa(
        session_id=sess_id,
        student_id=u1_id,
        question="How does the second law of thermodynamics define spontaneous processes?",
        answer="The total entropy of an isolated system always increases over time.",
        source_type="ai",
        relevant_excerpt="Entropy is a measure of molecular disorder..."
    )

    history = get_textbook_sessions(u1_id)
    assert len(history) == 1
    assert history[0]["title"] == "Chapter 3: Thermodynamics & Heat Engines"
    qa_list = get_textbook_qa(sess_id, u1_id)
    assert len(qa_list) == 1
    assert "entropy" in qa_list[0]["answer"].lower()

    # 5. Save Four Concepts
    c1 = save_important_concept(
        student_id=u1_id,
        topic="Physics / Thermo",
        concept_name="Second Law of Thermodynamics",
        question="Why does entropy never decrease in an isolated system?",
        notes="Revisit Carnot efficiency proof"
    )
    c2 = save_important_concept(
        student_id=u1_id,
        topic="Physics / Thermo",
        concept_name="Carnot Efficiency",
        question="What is the maximum theoretical efficiency of a heat engine?",
        notes="eta = 1 - (Tc / Th)"
    )
    c3 = save_important_concept(
        student_id=u1_id,
        topic="Physics / Thermo",
        concept_name="Clausius Inequality",
        question="State the mathematical form of Clausius inequality.",
        notes="Integral of dQ/T <= 0"
    )
    c4 = save_important_concept(
        student_id=u1_id,
        topic="Physics / Thermo",
        concept_name="Gibbs Free Energy",
        question="How does Gibbs free energy determine spontaneity at constant T and P?",
        notes="Delta G = Delta H - T * Delta S"
    )
    assert get_saved_concept_count(u1_id) == 4
    concepts_saved = get_saved_concepts(u1_id)
    assert len(concepts_saved) == 4

    # 6. Attempt a Fifth Concept -> blocked with exact message
    with pytest.raises(ValueError) as exc_info:
        save_important_concept(
            student_id=u1_id,
            topic="Physics / Thermo",
            concept_name="Helmholtz Energy",
            question="What is Helmholtz free energy?",
            notes="Delta A = Delta U - T * Delta S"
        )
    assert str(exc_info.value) == "You have saved four important concepts. Delete one to add a new concept."
    assert get_saved_concept_count(u1_id) == 4

    # 7. Delete One Concept
    del_ok = delete_saved_concept(u1_id, c1["id"])
    assert del_ok is True
    assert get_saved_concept_count(u1_id) == 3

    # Verify original textbook session and Q&A were NOT deleted
    assert len(get_textbook_sessions(u1_id)) == 1
    assert len(get_textbook_qa(sess_id, u1_id)) == 1

    # 8. Add a Replacement Concept
    c_repl = save_important_concept(
        student_id=u1_id,
        topic="Physics / Thermo",
        concept_name="Third Law of Thermodynamics",
        question="What happens to entropy as temperature approaches absolute zero?",
        notes="Approaches a constant minimum"
    )
    assert c_repl["id"] > 0
    assert get_saved_concept_count(u1_id) == 4
    updated_names = [c["concept_name"] for c in get_saved_concepts(u1_id)]
    assert "Second Law of Thermodynamics" not in updated_names
    assert "Third Law of Thermodynamics" in updated_names

    # 9. Verify Persistence Across Restart
    conn = connect()
    persisted_concepts = conn.execute("SELECT COUNT(*) FROM saved_concepts WHERE student_id=?", (u1_id,)).fetchone()[0]
    assert persisted_concepts == 4
    persisted_sessions = conn.execute("SELECT COUNT(*) FROM textbook_sessions WHERE student_id=?", (u1_id,)).fetchone()[0]
    assert persisted_sessions == 1
    conn.close()

    # 10. Sign in as a Second User with the SAME Display Name and Grade
    logout_user()
    u2 = create_account(
        username="rutuja_sharma",  # Unique username
        password="DifferentPassword#2026",
        display_name="Rutuja",      # SAME DISPLAY NAME!
        grade="College",            # SAME GRADE!
        email="rutuja.sharma@example.edu"
    )
    assert u2["id"] != u1_id
    assert u2["username"] == "rutuja_sharma"
    assert u2["name"] == "Rutuja"
    assert u2["grade"] == "College"
    u2_id = u2["id"]

    # 11. Verify Data Isolation
    # User 2 dashboard metrics are zero
    u2_dash = get_dashboard_data(u2_id)
    assert u2_dash["attempts"] == 0
    assert u2_dash["tests"] == 0

    # User 2 has zero textbook sessions
    assert len(get_textbook_sessions(u2_id)) == 0
    assert get_textbook_session(u2_id, sess_id) is None
    assert len(get_textbook_qa(sess_id, u2_id)) == 0

    # User 2 has zero saved concepts
    assert get_saved_concept_count(u2_id) == 0
    assert len(get_saved_concepts(u2_id)) == 0

    # User 2 CANNOT delete User 1's concepts
    cannot_delete = delete_saved_concept(u2_id, c2["id"])
    assert cannot_delete is False
    assert get_saved_concept_count(u1_id) == 4

    # User 2 CANNOT delete User 1's textbook session
    cannot_delete_sess, _ = delete_textbook_session(sess_id, u2_id)
    assert cannot_delete_sess is False
    assert len(get_textbook_sessions(u1_id)) == 1

    # Log back into User 1 and verify all progress and concepts remain intact
    u1_reauth = authenticate_user("rutuja_patil", "CollegePassword#2026")
    assert u1_reauth["id"] == u1_id
    assert get_saved_concept_count(u1_id) == 4
    assert len(get_textbook_sessions(u1_id)) == 1
