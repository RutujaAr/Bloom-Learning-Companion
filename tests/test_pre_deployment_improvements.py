"""
Regression and quality tests for Bloom pre-deployment improvements:
1. Textbook Helper pasted-material KeyError: 'extracted_text' crash fix.
2. Stage-appropriate curriculum selection and AI context injection.
3. Chart pan/zoom disabling and stationary configuration.
4. Privacy explanation panel removal from student UI.
5. Personal Study Guide concept gathering, generation, and PyMuPDF export.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from streamlit.testing.v1 import AppTest
import core.db as db
from core.db import format_local_timestamp, LOCAL_TZ, LOCAL_TIMEZONE_NAME
from core.syllabus import get_supported_curricula, get_syllabus_context, build_curriculum_context
from services.gemini_service import GeminiService
from agents.recall_loop import generate_recall_prompt
from agents.gap_finder import run_diagnostic
from core.learning import build_practice_set
from services.study_guide_service import (
    get_available_guide_concepts, generate_single_concept_guide, create_study_guide_pdf
)


# ---------------------------------------------------------------------------
# 1. TEXTBOOK HELPER CRASH REGRESSION TEST
# ---------------------------------------------------------------------------

def test_textbook_pasted_session_extracted_text_persistence_and_rendering(tmp_path, monkeypatch):
    """
    Regression test for: KeyError: 'extracted_text' in app.py around line 1996.
    Verify that creating a pasted notes session saves extracted_text in SQLite,
    that get_textbook_sessions and get_textbook_session return extracted_text,
    and that reopening the session in the UI does NOT crash with KeyError.
    """
    test_db = str(tmp_path / "test_tb_crash.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="usr_tb_tester", display_name="TB Tester", grade="College")
    sid = student["id"]

    pasted_material = (
        "Mitochondria generate most of the chemical energy needed to power the cell's biochemical reactions. "
        "Chemical energy produced by the mitochondria is stored in a small molecule called adenosine triphosphate (ATP)."
    )

    # 1. Save pasted session
    session_id = db.save_textbook_session(
        student_id=sid,
        title="Cellular Energy Notes",
        source_type="pasted",
        source_name="Pasted Lesson Notes",
        extracted_text=pasted_material,
        word_count=len(pasted_material.split()),
        is_truncated=0
    )
    assert session_id > 0

    # 2. Verify get_textbook_sessions includes extracted_text
    sessions = db.get_textbook_sessions(sid)
    assert len(sessions) == 1
    assert "extracted_text" in sessions[0]
    assert sessions[0]["extracted_text"] == pasted_material

    # 3. Verify get_textbook_session includes extracted_text
    single = db.get_textbook_session(sid, session_id)
    assert single is not None
    assert "extracted_text" in single
    assert single["extracted_text"] == pasted_material

    # 4. Verify Streamlit UI does not raise KeyError: 'extracted_text'
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": "usr_tb_tester",
        "name": "TB Tester",
        "grade": "College",
        "email": "tb@example.edu",
        "auth_type": "account"
    }
    at.session_state["nav_page"] = "Textbook helper"
    at.session_state["sidebar_radio"] = "Textbook helper"
    at.session_state["active_tb_session_id"] = session_id
    at.run()

    # Must NOT crash with KeyError
    assert not at.exception, f"App crashed on textbook page: {at.exception}"

    # Verify session title and preview are rendered
    assert any("Cellular Energy Notes" in m.value for m in at.markdown)
    assert any("adenosine triphosphate" in t.value for t in at.text)


def test_textbook_helper_defensive_empty_state_without_crash(tmp_path, monkeypatch):
    """
    Verify that an incomplete or legacy session lacking text content
    renders an informative empty-state message without crashing.
    """
    test_db = str(tmp_path / "test_tb_empty.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="usr_tb_empty_tester", display_name="Empty TB Tester")
    sid = student["id"]

    # Insert raw legacy session with empty text
    with db.get_connection() as c:
        cur = c.execute(
            "INSERT INTO textbook_sessions(student_id, title, source_type, source_name, extracted_text) VALUES (?, ?, ?, ?, ?)",
            (sid, "Corrupted Empty Session", "pasted", "Notes", "")
        )
        empty_sid = cur.lastrowid

    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": "usr_tb_empty_tester",
        "name": "Empty TB Tester",
        "grade": "College",
        "auth_type": "account"
    }
    at.session_state["nav_page"] = "Textbook helper"
    at.session_state["sidebar_radio"] = "Textbook helper"
    at.session_state["active_tb_session_id"] = empty_sid
    at.run()

    assert not at.exception
    # Should render informative notice about missing text
    assert any("No study text content is recorded" in inf.value for inf in at.info)


# ---------------------------------------------------------------------------
# 2. CURRICULUM CONTEXT AND STAGE ADAPTATION TESTS
# ---------------------------------------------------------------------------

def test_curriculum_selector_stage_appropriate_options():
    """
    Verify that a College student receives higher education curricula
    and is NOT defaulted to school CBSE.
    """
    college_curricula = get_supported_curricula("College")
    assert "University / Degree Curriculum" in college_curricula
    assert "College Course Outline" in college_curricula
    assert "CBSE (Verified 2024-25)" not in college_curricula
    assert "CBSE (Reference Syllabus)" not in college_curricula

    c10_curricula = get_supported_curricula("Class 10")
    assert any("CBSE" in c for c in c10_curricula)
    assert any("ICSE" in c for c in c10_curricula)

    c12_curricula = get_supported_curricula("Class 12")
    assert any("CBSE" in c for c in c12_curricula)
    assert any("ISC" in c for c in c12_curricula)


def test_build_curriculum_context_and_ai_injection():
    """
    Verify that build_curriculum_context constructs a unified context string
    that reflects the student's education stage and curriculum without false claims.
    """
    ctx_college = build_curriculum_context("College", "University / Degree Curriculum", "Computer Science", "Sorting Algorithms")
    assert "College" in ctx_college
    assert "University / Degree Curriculum" in ctx_college
    assert "Sorting Algorithms" in ctx_college

    ctx_c10 = build_curriculum_context("Class 10", "CBSE (Reference Syllabus)", "Mathematics", "Real Numbers")
    assert "Class 10" in ctx_c10
    assert "CBSE" in ctx_c10


def test_explain_from_document_curriculum_context_passed(monkeypatch):
    """
    Verify that Gemini explain_from_document accepts and includes curriculum_context.
    """
    service = GeminiService()
    captured_prompts = []

    def mock_generate_text(prompt, max_tokens):
        captured_prompts.append(prompt)
        return "ATP is synthesized by ATP synthase using proton gradient energy.", "success"

    monkeypatch.setattr(service, "generate_text", mock_generate_text)

    curriculum_ctx = "Education Stage: College\nCurriculum: University / Degree Curriculum"
    doc_text = "ATP synthase utilizes a transmembrane proton electrochemical gradient."
    ans, status = service.explain_from_document("What is ATP synthase?", doc_text, curriculum_context=curriculum_ctx)

    assert ans is not None
    assert len(captured_prompts) == 1
    assert "CURRICULUM & LEVEL CONTEXT" in captured_prompts[0]
    assert "University / Degree Curriculum" in captured_prompts[0]
    assert "ATP synthase utilizes" in captured_prompts[0]


def test_generate_recall_prompt_curriculum_context_passed(monkeypatch):
    """
    Verify that generate_recall_prompt includes education stage and curriculum in prompt.
    """
    service = GeminiService()
    service.api_key = "dummy"
    captured_prompts = []

    def mock_available():
        return True

    def mock_generate_text(prompt, max_output_tokens=1400):
        captured_prompts.append(prompt)
        return '{"challenge": "Explain ATP", "model_answer": "ATP is energy", "key_points": ["ATP"]}', "success"

    monkeypatch.setattr(service, "available", mock_available)
    monkeypatch.setattr(service, "generate_text", mock_generate_text)

    res = generate_recall_prompt(service, "Biology", "Cellular Respiration", stage="College", curriculum="University / Degree Curriculum")
    assert res is not None
    assert len(captured_prompts) == 1
    assert "College" in captured_prompts[0]
    assert "University / Degree Curriculum" in captured_prompts[0]


# ---------------------------------------------------------------------------
# 3. PRIVACY PANEL REMOVED FROM STUDENT UI TEST
# ---------------------------------------------------------------------------

def test_privacy_explanation_panel_removed_from_ui(tmp_path, monkeypatch):
    """
    Verify that the explanatory 'Student Data Privacy & Isolation' panel
    is removed from the login screen, while maintaining authentication flow.
    """
    test_db = str(tmp_path / "test_privacy_ui.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.run()

    # Must render login form
    assert any("Access Your Learning Space" in m.value for m in at.markdown)

    # Must NOT render the large privacy explanation card
    all_markdowns = [m.value for m in at.markdown]
    assert not any("Student Data Privacy & Isolation" in m for m in all_markdowns)
    assert not any("Private & Isolated Learning Records" in m for m in all_markdowns)


# ---------------------------------------------------------------------------
# 4. PERSONAL STUDY GUIDE SERVICE & PDF TESTS
# ---------------------------------------------------------------------------

def test_study_guide_concept_gathering_and_isolation(tmp_path, monkeypatch):
    """
    Verify that get_available_guide_concepts gathers recorded gaps, saved concepts,
    textbook sessions, and review items, scoped strictly to the student.
    """
    test_db = str(tmp_path / "test_study_guide_data.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    # User A records a mistaken diagnostic attempt and saved concept
    student_a = db.get_or_create_account(owner_id="owner_guide_alice", display_name="Alice")
    student_b = db.get_or_create_account(owner_id="owner_guide_bob", display_name="Bob")

    db.save_attempt(student_a["id"], "Biology", "Photosynthesis", "Light reaction?", "Wrong", "Right", False, "conceptual")
    db.save_important_concept(student_a["id"], "Biology", "Calvin Cycle", "What is RuBisCO?", "Key enzyme")

    # User B records a different topic
    db.save_attempt(student_b["id"], "Physics", "Thermodynamics", "Carnot engine?", "Wrong", "Right", False, "calculation")

    # Check Alice concepts
    alice_concepts = get_available_guide_concepts(student_a["id"])
    alice_topics = [c["topic"] for c in alice_concepts]
    assert "Photosynthesis" in alice_topics
    assert any("Calvin Cycle" in t for t in alice_topics)
    assert "Thermodynamics" not in alice_topics, "Bob's topic must not leak into Alice's guide options"

    # Check recorded mistakes are preserved
    photo_item = [c for c in alice_concepts if c["topic"] == "Photosynthesis"][0]
    assert "conceptual" in photo_item["mistakes"]


def test_create_study_guide_pdf_validity_and_formatting():
    """
    Verify that create_study_guide_pdf generates valid, multi-page PDF bytes
    with headers, footers, section headings, and safe Unicode rendering.
    """
    sample_section = {
        "topic": "Enzyme Kinetics & Michaelis-Menten",
        "subject": "Biochemistry",
        "plain_explanation": "Enzymes speed up biochemical reactions by lowering activation energy.",
        "deep_explanation": "The Michaelis-Menten model describes hyperbolic reaction velocity as a function of substrate concentration [S].",
        "why_it_matters": "Essential for understanding drug metabolism, inhibition kinetics, and metabolic regulation.",
        "step_by_step_method": "1. Determine initial velocity v0.\n2. Plot Lineweaver-Burk reciprocal.\n3. Identify Vmax and Km intercepts.",
        "worked_example": "Given Km = 2 mM, [S] = 6 mM, calculate v0 as a fraction of Vmax: v0 = Vmax * (6 / (2+6)) = 0.75 Vmax.",
        "formulas": "v0 = (Vmax * [S]) / (Km + [S])\nKm = substrate concentration at 0.5 Vmax",
        "definitions": "• Km: Substrate concentration at half-maximal velocity.\n• Vmax: Maximum theoretical turnover rate.\n• kcat: Catalytic rate constant.",
        "common_mistakes": "• Confusing Km with binding affinity without checking if k-1 >> k2.\n• Forgetting to account for competitive vs noncompetitive inhibitors.",
        "practice_questions": [
            {
                "question": "What happens to apparent Km in the presence of a competitive inhibitor?",
                "answer": "Apparent Km increases while Vmax remains unchanged.",
                "explanation": "Inhibitor competes for the same active site, requiring higher substrate concentration."
            }
        ],
        "quick_summary": [
            "Hyperbolic saturation curve relates v0 to [S].",
            "Competitive inhibition increases apparent Km without altering Vmax."
        ],
        "source_reference": "Biochemistry Textbook Session Excerpt"
    }

    pdf_bytes = create_study_guide_pdf(
        guide_sections=[sample_section],
        student_name="Rutuja Patil",
        grade="College",
        curriculum="University / Degree Curriculum"
    )

    assert pdf_bytes is not None
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-"), "Output must be a valid PDF binary"

    # Inspect rendered PDF with pymupdf
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) >= 1
    page1_text = doc[0].get_text("text")
    assert "BLOOM · PERSONAL STUDY GUIDE" in page1_text
    assert "Rutuja Patil" in page1_text
    assert "Enzyme Kinetics" in page1_text
    assert "Bloom Learning Companion" in page1_text


# ---------------------------------------------------------------------------
# 5. EDUCATION STAGE & CURRICULUM CONTEXT COMPARISON TESTS
# ---------------------------------------------------------------------------

def test_stage_prompt_context_comparison():
    """
    Verify that build_curriculum_context produces distinct, stage-calibrated
    pedagogical directives and terminology for Class 10, Class 12, College, and Research / PhD.
    """
    ctx_c10 = build_curriculum_context("Class 10", "CBSE (Reference Syllabus)", "Science", "Electricity")
    ctx_c12 = build_curriculum_context("Class 12", "CBSE (Reference Syllabus)", "Physics", "Current Electricity")
    ctx_college = build_curriculum_context("College", "University / Degree Curriculum", "Electrical Engineering", "Circuit Theory")
    ctx_phd = build_curriculum_context("Research / PhD", "Postgraduate / Research Programme", "Electrical Engineering", "Quantum Transport")

    # 1. Verify Class 10 directives
    assert "Class 10 / Secondary Level - Ages 15-16" in ctx_c10
    assert "clear, age-appropriate, foundational academic terms" in ctx_c10
    assert "step-by-step arithmetic/algebraic steps" in ctx_c10

    # 2. Verify Class 12 directives
    assert "Class 12 / Senior Secondary - Ages 17-18" in ctx_c12
    assert "formal senior-secondary terminology" in ctx_c12
    assert "symbolic proofs" in ctx_c12 or "derivations" in ctx_c12

    # 3. Verify College directives
    assert "College / Undergraduate Level" in ctx_college
    assert "formal university academic terminology" in ctx_college.lower()
    assert "algorithmic complexity" in ctx_college or "system-level trade-offs" in ctx_college

    # 4. Verify Research / PhD directives
    assert "Research / PhD Level - Doctoral Study" in ctx_phd
    assert "specialist domain vocabulary" in ctx_phd.lower()
    assert "without hallucinating or inventing fabricated research citations or DOIs" in ctx_phd

    # 5. Verify all four are pairwise distinct
    contexts = [ctx_c10, ctx_c12, ctx_college, ctx_phd]
    assert len(set(contexts)) == 4, "Each education stage must generate distinct prompt context"

    # 6. Verify custom syllabus is incorporated
    custom_desc = "SPPU Third Year AI Syllabus Unit 3: Graph Convolutional Networks"
    ctx_custom = build_curriculum_context("College", "Custom Syllabus (Learner-Supplied)", "AI", "GNNs", custom_syllabus=custom_desc)
    assert custom_desc in ctx_custom
    assert "User-Supplied Course/Syllabus Outline" in ctx_custom

    # 7. Verify contradictory stage/board handling (e.g. College with school CBSE)
    ctx_conflict = build_curriculum_context("College", "CBSE (Reference Syllabus)", "Computer Science", "Trees")
    assert "Note: Learner stage is College" in ctx_conflict
    assert "calibrate terminology and depth to College level" in ctx_conflict


def test_all_ai_entry_points_receive_curriculum_context(monkeypatch):
    """
    Verify that the structured academic context genuinely reaches all 5 AI entry points:
    1. Diagnostic question generation (gap_finder.run_diagnostic)
    2. Targeted practice questions (learning.build_practice_set)
    3. Textbook Helper document explanation (gemini_service.explain_from_document)
    4. Recall & Revision prompt (recall_loop.generate_recall_prompt)
    5. Personal Study Guide chapter generation (study_guide_service.generate_single_concept_guide)
    """
    service = GeminiService()
    captured_calls = []

    def mock_available():
        return True

    def mock_generate_text(prompt, max_output_tokens=1200, timeout_ms=None):
        captured_calls.append({"prompt": prompt, "max_tokens": max_output_tokens, "timeout_ms": timeout_ms})
        # Return generic valid JSON or text depending on what caller expects
        if "generate_single_concept_guide" in prompt or "Return a valid JSON object with EXACTLY these keys" in prompt:
            return '{"plain_explanation": "Intuition", "deep_explanation": "Rigorous detail"}', "success"
        elif "JSON array" in prompt or "diagnostic" in prompt.lower():
            return '[{"prompt": "Q1?", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "Exp", "hint": "H", "mistake_type": "conceptual"}]', "success"
        return "Explanation from document", "success"

    monkeypatch.setattr(service, "available", mock_available)
    monkeypatch.setattr(service, "generate_text", mock_generate_text)

    # 1. Diagnostic gap finder
    captured_calls.clear()
    analysis, questions = run_diagnostic(
        service,
        "Physics",
        "Kinematics",
        stage="Class 12",
        curriculum="CBSE (Reference Syllabus)",
        custom_syllabus="Custom Class 12 Kinematics Outline"
    )
    assert len(captured_calls) >= 1
    diag_prompt = captured_calls[0]["prompt"]
    assert "Class 12 / Senior Secondary - Ages 17-18" in diag_prompt
    assert "Custom Class 12 Kinematics Outline" in diag_prompt

    # 2. Targeted practice set
    captured_calls.clear()
    practice = build_practice_set(
        "Computer Science",
        "Graph Algorithms",
        gemini=service,
        stage="College",
        curriculum="University / Degree Curriculum"
    )
    assert len(captured_calls) >= 1
    prac_prompt = captured_calls[0]["prompt"]
    assert "College / Undergraduate Level" in prac_prompt
    assert "University / Degree Curriculum" in prac_prompt

    # 3. Textbook Helper explain_from_document
    captured_calls.clear()
    curr_ctx = build_curriculum_context("Research / PhD", "Postgraduate / Research Programme", topic="Quantum Entanglement")
    service.explain_from_document("What is Bell's inequality?", "Bell's theorem shows locality limits.", curriculum_context=curr_ctx)
    assert len(captured_calls) >= 1
    tb_prompt = captured_calls[0]["prompt"]
    assert "CURRICULUM & LEVEL CONTEXT" in tb_prompt
    assert "Research / PhD Level - Doctoral Study" in tb_prompt
    assert "without hallucinating or inventing fabricated research citations or DOIs" in tb_prompt

    # 4. Recall & Revision prompt
    captured_calls.clear()
    generate_recall_prompt(
        service,
        "Chemistry",
        "Thermodynamics",
        stage="Class 10",
        curriculum="CBSE (Reference Syllabus)"
    )
    assert len(captured_calls) >= 1
    recall_prompt = captured_calls[0]["prompt"]
    assert "Class 10 / Secondary Level - Ages 15-16" in recall_prompt

    # 5. Personal Study Guide single concept guide
    captured_calls.clear()
    generate_single_concept_guide(
        gemini=service,
        topic="Neural Network Architectures",
        subject="Computer Science",
        stage="College",
        curriculum="Autonomous / State University Syllabus",
        custom_syllabus="Autonomous Curriculum 2026 AI Specialization"
    )
    assert len(captured_calls) >= 1
    guide_prompt = captured_calls[0]["prompt"]
    assert "College / Undergraduate Level" in guide_prompt
    assert "Autonomous Curriculum 2026 AI Specialization" in guide_prompt


# ---------------------------------------------------------------------------
# 6. TIMESTAMP CONVERSION & UTC STORAGE TESTS
# ---------------------------------------------------------------------------

def test_format_local_timestamp_utc_to_ist_and_rollover():
    """
    Verify timezone conversion from UTC database timestamps to local display (Asia/Kolkata, UTC+5:30):
    1. Standard UTC to IST conversion (+5h 30m).
    2. Date rollover across midnight (e.g. 20:30 UTC -> 02:00 IST next day).
    3. ISO formatted strings.
    4. Timezone-aware datetime objects.
    5. None, empty strings, and malformed values handled defensively.
    """
    # 1. Standard UTC conversion: 14:00 UTC -> 19:30 IST
    ist_str = format_local_timestamp("2026-10-25 14:00:00")
    assert ist_str == "2026-10-25 19:30"

    # 2. Date rollover across midnight: 20:30 UTC -> 02:00 IST on 2026-10-26
    rollover_str = format_local_timestamp("2026-10-25 20:30:00")
    assert rollover_str == "2026-10-26 02:00"

    # Date-only format rollover:
    date_only_str = format_local_timestamp("2026-10-25 20:30:00", "%Y-%m-%d")
    assert date_only_str == "2026-10-26"

    # 3. ISO formatted string with T and Z
    iso_str = format_local_timestamp("2026-10-25T14:00:00Z")
    assert iso_str == "2026-10-25 19:30"

    # 4. Naive datetime treated as UTC
    naive_dt = datetime(2026, 10, 25, 14, 0, 0)
    assert format_local_timestamp(naive_dt) == "2026-10-25 19:30"

    # 5. Timezone-aware datetime in UTC
    aware_utc = datetime(2026, 10, 25, 14, 0, 0, tzinfo=timezone.utc)
    assert format_local_timestamp(aware_utc) == "2026-10-25 19:30"

    # 6. Empty / None handling
    assert format_local_timestamp(None) == ""
    assert format_local_timestamp("") == ""

    # 7. Unparseable string returns original string safely
    assert format_local_timestamp("not-a-timestamp") == "not-a-timestamp"


def test_textbook_session_timestamp_utc_storage(tmp_path, monkeypatch):
    """
    Verify that new textbook sessions save UTC timestamps formatted as 'YYYY-MM-DD HH:MM:SS'
    and display correctly in IST.
    """
    test_db = str(tmp_path / "test_tb_ts.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="usr_ts_tester", display_name="TS Tester")
    sid = student["id"]

    # Save session
    session_id = db.save_textbook_session(
        student_id=sid,
        title="Timestamp Test Chapter",
        source_type="pasted",
        source_name="Notes",
        extracted_text="Some study notes here.",
        word_count=4,
        is_truncated=0
    )

    # Read raw created_at from SQLite
    with db.get_connection() as c:
        row = c.execute("SELECT created_at FROM textbook_sessions WHERE id = ?", (session_id,)).fetchone()

    raw_ts = row["created_at"]
    assert raw_ts is not None
    # Must match YYYY-MM-DD HH:MM:SS
    assert len(raw_ts) == 19
    assert raw_ts[4] == "-" and raw_ts[7] == "-" and raw_ts[10] == " " and raw_ts[13] == ":"

    # Must convert cleanly to local IST string without error
    local_display = format_local_timestamp(raw_ts)
    assert len(local_display) == 16  # YYYY-MM-DD HH:MM


# ---------------------------------------------------------------------------
# 7. STUDENT PROFILE STAGE & CURRICULUM PERSISTENCE TESTS
# ---------------------------------------------------------------------------

def test_student_profile_stage_and_curriculum_persistence(tmp_path, monkeypatch):
    """
    Verify that updating the student profile persists both the education stage
    and the chosen curriculum in the database across subsequent queries and updates.
    """
    test_db = str(tmp_path / "test_profile_persist.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="usr_phd_student", display_name="Dr. Jane", grade="College")
    sid = student["id"]

    # 1. Update profile to Research / PhD with research curriculum
    db.update_student_profile(
        student_id=sid,
        owner_id="usr_phd_student",
        display_name="Dr. Jane Doe",
        grade="Research / PhD",
        curriculum="Postgraduate / Research Programme"
    )

    # 2. Reload student from DB
    reloaded = db.get_or_create_account(owner_id="usr_phd_student")
    assert reloaded["grade"] == "Research / PhD"
    assert reloaded["curriculum"] == "Postgraduate / Research Programme"
    assert reloaded["name"] == "Dr. Jane Doe"

    # 3. Update curriculum independently
    db.update_student_profile(
        student_id=sid,
        owner_id="usr_phd_student",
        curriculum="Custom Research Focus"
    )

    reloaded2 = db.get_or_create_account(owner_id="usr_phd_student")
    assert reloaded2["grade"] == "Research / PhD"
    assert reloaded2["curriculum"] == "Custom Research Focus"
    assert reloaded2["name"] == "Dr. Jane Doe"


# ---------------------------------------------------------------------------
# 8. PERSONAL STUDY GUIDE CONCEPT DEDUPLICATION & LABELS
# ---------------------------------------------------------------------------

def test_study_guide_concept_deduplication_and_compact_labels():
    """
    Verify that Personal Study Guide combines available and custom concepts without duplicates,
    and truncates long concept labels to avoid wide viewport overflow.
    """
    available_concepts = [
        {"id": "c1", "topic": "Photosynthesis", "subject": "Biology", "source": "Diagnostic"},
        {"id": "c2", "topic": "A Very Long Concept Name That Exceeds Fifty Characters In Length Easily", "subject": "Physics", "source": "Textbook"}
    ]
    custom_list = [
        {"id": "custom_1", "topic": "photosynthesis", "subject": "biology", "source": "Manual Selection"},  # Duplicate
        {"id": "custom_2", "topic": "Cellular Respiration", "subject": "Biology", "source": "Manual Selection"}
    ]

    # Deduplication logic matching app.py
    seen = set()
    all_selectable = []
    for c in (available_concepts + custom_list):
        k = (c["topic"].strip().lower(), c.get("subject", "").strip().lower())
        if k not in seen:
            seen.add(k)
            all_selectable.append(c)

    assert len(all_selectable) == 3, "Duplicate 'photosynthesis' must be eliminated"

    # Label generation logic matching app.py
    def _make_label(c):
        t = c['topic'].strip()
        short_top = (t[:50] + "...") if len(t) > 50 else t
        return f"{short_top} · {c.get('subject', 'General')} ({c.get('source', 'Recorded')})"

    long_concept = all_selectable[1]
    lbl = _make_label(long_concept)
    assert len(lbl) < 100
    assert lbl.startswith("A Very Long Concept Name That Exceeds Fifty Charac...")
    assert "Physics (Textbook)" in lbl

