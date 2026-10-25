"""
Regression tests for Personal Study Guide concept selection, subject-aware deduplication,
stable selection identity, and resilient LaTeX/code response parsing.
"""

import json
import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest

import core.db as db
from services.study_guide_service import (
    get_available_guide_concepts,
    generate_single_concept_guide,
    create_study_guide_pdf
)


# ---------------------------------------------------------------------------
# 1. Subject-Aware Deduplication & Unique Stable IDs
# ---------------------------------------------------------------------------

def test_distinct_subjects_with_identical_topic_names(tmp_path, monkeypatch):
    """
    Ensure topics with identical names across distinct subjects (e.g. Mathematics - Vectors
    vs Physics - Vectors) receive unique IDs and are NOT merged or dropped.
    """
    test_db = str(tmp_path / "test_psg_subjects.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="owner_psg_test", display_name="Student Test")
    sid = student["id"]

    # Record mistake in Math Vectors
    db.save_attempt(sid, "Mathematics", "Vectors", "Cross product?", "0", "1", False, "calculation")
    # Record mistake in Physics Vectors
    db.save_attempt(sid, "Physics", "Vectors", "Resolving forces?", "0", "1", False, "conceptual")

    concepts = get_available_guide_concepts(sid)
    assert len(concepts) == 2, "Both Math Vectors and Physics Vectors must be retained"

    math_c = [c for c in concepts if c["subject"] == "Mathematics"][0]
    phys_c = [c for c in concepts if c["subject"] == "Physics"][0]

    assert math_c["id"] != phys_c["id"], "Internal concept IDs must be unique"
    assert math_c["topic"] == "Vectors"
    assert phys_c["topic"] == "Vectors"
    assert "calculation" in math_c["mistakes"]
    assert "conceptual" in phys_c["mistakes"]


def test_long_topic_titles_retained_with_stable_id(tmp_path, monkeypatch):
    """
    Ensure concepts with long titles (>50 chars) maintain stable IDs and intact topics.
    """
    test_db = str(tmp_path / "test_psg_long.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    db.DB_PATH = test_db
    db.init_db()

    student = db.get_or_create_account(owner_id="owner_psg_long", display_name="Long Test")
    sid = student["id"]

    long_title = "Electrochemical Cells and Standard Electrode Potentials at Non-Standard Conditions"
    db.save_attempt(sid, "Chemistry", long_title, "Nernst equation?", "0", "1", False, "calculation")

    concepts = get_available_guide_concepts(sid)
    assert len(concepts) == 1
    assert concepts[0]["topic"] == long_title
    assert len(concepts[0]["id"]) > 5
    assert "Electrochemical" in concepts[0]["id"] or "electrochemical" in concepts[0]["id"]


# ---------------------------------------------------------------------------
# 2. AppTest Streamlit Simulation: Selection, Deselection, Harmless Reruns
# ---------------------------------------------------------------------------

def simulate_psg_page_script():
    """
    Minimal script reproducing Bloom's Personal Study Guide UI logic from app.py.
    """
    import streamlit as st
    import re

    # Session state initialization
    if "psg_custom_list" not in st.session_state:
        st.session_state["psg_custom_list"] = []
    if "active_study_guide" not in st.session_state:
        st.session_state["active_study_guide"] = None

    # Mock available concepts from database
    available_concepts = [
        {"id": "gap_mathematics_vectors", "topic": "Vectors", "subject": "Mathematics", "source": "Gaps", "mistakes": ["calc"]},
        {"id": "gap_physics_vectors", "topic": "Vectors", "subject": "Physics", "source": "Gaps", "mistakes": ["concept"]},
        {"id": "saved_42", "topic": "Enzyme Kinetics and Lineweaver-Burk Double Reciprocal Plots", "subject": "Biochemistry", "source": "Saved", "mistakes": []}
    ]

    # Manual add section (before multiselect)
    with st.expander("➕ Add Custom Topics / Concepts Manually"):
        manual_topic = st.text_input("Concept Name:", key="manual_topic_input")
        manual_subj = st.text_input("Subject:", key="manual_subj_input")

        if st.button("Add to Guide Selection ➕", key="btn_add_manual"):
            clean_top = manual_topic.strip()
            subj_val = manual_subj.strip() or "General Academic"
            if clean_top:
                existing_pairs = {
                    (c.get("subject", "General Academic").strip().lower(), c["topic"].strip().lower())
                    for c in (available_concepts + st.session_state["psg_custom_list"])
                }
                if (subj_val.lower(), clean_top.lower()) in existing_pairs:
                    st.info("Already exists")
                else:
                    custom_id = f"custom_{len(st.session_state['psg_custom_list']) + 1}_{re.sub(r'[^a-zA-Z0-9]', '_', clean_top[:20])}"
                    new_item = {
                        "id": custom_id,
                        "topic": clean_top,
                        "subject": subj_val,
                        "source": "Manual Selection",
                        "mistakes": []
                    }
                    st.session_state["psg_custom_list"].append(new_item)
                    cur_sel = list(st.session_state.get("psg_concept_multiselect", []))
                    if custom_id not in cur_sel:
                        st.session_state["psg_concept_multiselect"] = cur_sel + [custom_id]
                    st.rerun()

    # Deduplicate combined
    seen = set()
    all_selectable = []
    for c in (available_concepts + st.session_state["psg_custom_list"]):
        k = (c.get("subject", "General").strip().lower(), c["topic"].strip().lower())
        if k not in seen:
            seen.add(k)
            all_selectable.append(c)

    id_to_concept = {c["id"]: c for c in all_selectable}
    concept_ids = [c["id"] for c in all_selectable]

    def _format_concept_option(cid):
        c = id_to_concept.get(cid)
        if not c:
            return str(cid)
        t = c["topic"].strip()
        short_top = (t[:50] + "...") if len(t) > 50 else t
        return f"{short_top} · {c.get('subject', 'General')} ({c.get('source', 'Recorded')})"

    if "psg_concept_multiselect" not in st.session_state:
        st.session_state["psg_concept_multiselect"] = concept_ids[:min(2, len(concept_ids))]
    else:
        st.session_state["psg_concept_multiselect"] = [
            cid for cid in st.session_state["psg_concept_multiselect"] if cid in id_to_concept
        ]

    selected_ids = st.multiselect(
        "Choose concepts:",
        options=concept_ids,
        format_func=_format_concept_option,
        key="psg_concept_multiselect"
    )

    selected_concept_objs = [id_to_concept[cid] for cid in selected_ids if cid in id_to_concept]
    st.session_state["_last_resolved_objs"] = selected_concept_objs

    # Action bar
    btn_disabled = (len(selected_concept_objs) == 0)
    generate_clicked = st.button("Generate Personal Study Guide ✨", disabled=btn_disabled, key="btn_generate")

    # Harmless other control
    st.checkbox("Show Advanced Formulas", key="chk_toggle")

    if st.session_state.get("psg_last_error"):
        st.error(f"⚠️ Study Guide compilation failed: {st.session_state['psg_last_error']}")
        if st.button("Retry Generation 🔄", key="btn_retry"):
            generate_clicked = True

    if generate_clicked:
        if st.session_state.get("fail_generation_flag"):
            st.session_state["psg_last_error"] = "Simulated API quota exceeded"
            st.rerun()
        else:
            st.session_state["active_study_guide"] = {
                "count": len(selected_concept_objs),
                "topics": [c["topic"] for c in selected_concept_objs]
            }
            st.session_state.pop("psg_last_error", None)


def test_apptest_selection_and_manual_addition():
    """
    Simulate AppTest workflow:
    1. Initial default concepts selected.
    2. Add manual concept without diagnostic history -> auto-selected.
    3. Both identical topic names (Math Vectors vs Phys Vectors) can be independently selected.
    4. Harmless control toggles preserve selection.
    5. Deselecting all disables the Generate button.
    6. Exactly selected concepts reach generation.
    """
    at = AppTest.from_function(simulate_psg_page_script).run()

    # Step 1: Default initial selection has 2 concepts
    assert at.session_state["psg_concept_multiselect"] == ["gap_mathematics_vectors", "gap_physics_vectors"]
    assert not at.button(key="btn_generate").disabled

    # Step 2: Add a manual concept
    at.text_input(key="manual_topic_input").input("Graph Neural Networks").run()
    at.text_input(key="manual_subj_input").input("Computer Science").run()
    at.button(key="btn_add_manual").click().run()

    # Check that new concept was added and automatically selected
    assert any("Graph Neural Networks" in c["topic"] for c in at.session_state["psg_custom_list"])
    custom_c = at.session_state["psg_custom_list"][0]
    assert custom_c["id"] in at.session_state["psg_concept_multiselect"]
    assert len(at.session_state["psg_concept_multiselect"]) == 3

    # Step 3: Harmless control toggle (checkbox) does not clear selection
    at.checkbox(key="chk_toggle").check().run()
    assert len(at.session_state["psg_concept_multiselect"]) == 3
    assert custom_c["id"] in at.session_state["psg_concept_multiselect"]

    # Step 4: Deselect physics vectors
    at.multiselect(key="psg_concept_multiselect").unselect("gap_physics_vectors").run()
    assert "gap_physics_vectors" not in at.session_state["psg_concept_multiselect"]
    assert "gap_mathematics_vectors" in at.session_state["psg_concept_multiselect"]
    assert custom_c["id"] in at.session_state["psg_concept_multiselect"]

    # Step 5: Click Generate -> verify EXACT concepts reached generation
    at.button(key="btn_generate").click().run()
    assert at.session_state["active_study_guide"] is not None
    assert at.session_state["active_study_guide"]["count"] == 2
    assert "Vectors" in at.session_state["active_study_guide"]["topics"]
    assert "Graph Neural Networks" in at.session_state["active_study_guide"]["topics"]

    # Step 6: Deselect remaining concepts -> button becomes disabled
    at.multiselect(key="psg_concept_multiselect").unselect("gap_mathematics_vectors").unselect(custom_c["id"]).run()
    assert at.session_state["psg_concept_multiselect"] == []
    assert at.button(key="btn_generate").disabled


def test_apptest_error_recovery_retains_selection():
    """
    Ensure that when guide compilation fails:
    1. Selected concepts are preserved in session state.
    2. An informative error message is displayed.
    3. A retry button is rendered.
    """
    at = AppTest.from_function(simulate_psg_page_script).run()
    initial_sel = list(at.session_state["psg_concept_multiselect"])
    assert len(initial_sel) > 0

    # Inject failure flag
    at.session_state["fail_generation_flag"] = True
    at.button(key="btn_generate").click().run()

    # Error occurred
    assert at.session_state.get("psg_last_error") == "Simulated API quota exceeded"
    # User's selection must be completely preserved!
    assert at.session_state["psg_concept_multiselect"] == initial_sel
    # Retry button is available
    assert at.button(key="btn_retry") is not None
    assert not at.button(key="btn_retry").disabled

    # Now resolve failure and click retry
    at.session_state["fail_generation_flag"] = False
    at.button(key="btn_retry").click().run()

    # Succeeded on retry
    assert at.session_state.get("active_study_guide") is not None
    assert at.session_state.get("psg_last_error") is None


# ---------------------------------------------------------------------------
# 3. Adversarial STEM/LaTeX & Code Parsing in Study Guide Service
# ---------------------------------------------------------------------------

class MockAdversarialGemini:
    """Mock Gemini service returning challenging technical output."""
    def __init__(self, raw_content):
        self.raw_content = raw_content

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=2000):
        return self.raw_content, "Mocked"


def test_generate_single_concept_guide_handles_latex():
    """
    Verify generate_single_concept_guide parses responses containing LaTeX equations
    with unescaped backslashes (\\frac, \\log, \\sum, \\times).
    """
    raw_ai = r"""
    ```json
    {
        "plain_explanation": "Entropy measures microscopic disorder in thermodynamics: S = k_B \ln(\Omega).",
        "deep_explanation": "In statistical mechanics, \frac{\partial S}{\partial E} = \frac{1}{T} and \sum_{i} P_i \log_2(P_i) represents Shannon entropy.",
        "why_it_matters": "Determines feasibility of spontaneous processes via \Delta G = \Delta H - T\Delta S.",
        "step_by_step_method": "1. Identify state variables.\n2. Compute \Delta S = \int \frac{dQ_{rev}}{T}.\n3. Verify units in J/K.",
        "worked_example": "Compute entropy change for reversible isothermal expansion of ideal gas.",
        "formulas": "\Delta S = n R \ln(V_2 / V_1)",
        "definitions": "Microstate: A specific configuration of particles in phase space.",
        "mnemonic": null,
        "common_mistakes": "Forgetting that Q must be reversible when calculating \Delta S.",
        "practice_questions": [
            {"question": "What is the unit of entropy?", "answer": "J/K", "explanation": "Joules per Kelvin."}
        ],
        "quick_summary": ["Entropy increases in isolated systems", "Second law of thermodynamics"],
        "source_reference": "Standard Thermodynamics"
    }
    ```
    """
    mock_gemini = MockAdversarialGemini(raw_ai)
    guide = generate_single_concept_guide(
        gemini=mock_gemini,
        topic="Entropy & Second Law",
        subject="Physics",
        stage="College"
    )

    assert guide["topic"] == "Entropy & Second Law"
    assert guide["subject"] == "Physics"
    assert r"\frac" in guide["deep_explanation"]
    assert "Entropy measures microscopic disorder" in guide["plain_explanation"]


def test_generate_single_concept_guide_handles_code_and_multiline():
    """
    Verify generate_single_concept_guide parses responses containing programming identifiers
    like build_heap, linked_list, and unescaped newlines in worked examples.
    """
    raw_ai = """
    {
        "plain_explanation": "A binary heap satisfies the heap invariant where parent nodes dominate child nodes.",
        "deep_explanation": "Building a heap with build_heap runs in O(n) time using sift_down, whereas repeated insertions take O(n log n).",
        "why_it_matters": "Foundation for priority queues, Dijkstra's shortest path, and Huffman coding.",
        "step_by_step_method": "1. Initialize array representation.\n2. Iterate backwards from floor(n/2) down to 0.\n3. Call sift_down(i) at each step.",
        "worked_example": "def build_heap(arr):\n    # Reorder array into heap\n    for i in range(len(arr)//2, -1, -1):\n        sift_down(arr, i)\n    return arr",
        "formulas": "Left child: 2i + 1; Right child: 2i + 2; Parent: (i - 1) // 2",
        "definitions": "Heap property: Key(parent) >= Key(child) for max-heap.",
        "mnemonic": null,
        "common_mistakes": "Confusing O(n) build_heap with O(n log n) heapsort.",
        "practice_questions": [
            {"question": "What is the time complexity of build_heap?", "answer": "O(n)", "explanation": "Bounded by sum of node heights."}
        ],
        "quick_summary": ["O(n) build time", "Array representation without pointers"],
        "source_reference": "Core Algorithms"
    }
    """
    mock_gemini = MockAdversarialGemini(raw_ai)
    guide = generate_single_concept_guide(
        gemini=mock_gemini,
        topic="Binary Heap Data Structure",
        subject="Computer Science",
        stage="College"
    )

    assert "build_heap" in guide["deep_explanation"]
    assert "sift_down" in guide["worked_example"]


def test_pdf_creation_with_adversarial_characters():
    """
    Verify that create_study_guide_pdf renders valid PDF bytes without crashing on
    quotes, em-dashes, and math symbols.
    """
    sample_section = {
        "topic": "Entropy & Statistical Mechanics",
        "subject": "Physics",
        "plain_explanation": "Concept intuition with “smart quotes” and — em-dashes.",
        "deep_explanation": "Formulas with fractions: dS >= dQ/T and S = k_B * ln(W).",
        "why_it_matters": "Universal principle governing spontaneity.",
        "step_by_step_method": "1. Check boundary.\n2. Compute integral.\n3. Verify sign.",
        "worked_example": "Problem: Isothermal expansion.\nSolution: dS = nR ln(2).",
        "formulas": "dS = dQ / T; S = k_B ln(W)",
        "definitions": "Microstate: Specific atomic configuration.",
        "mnemonic": None,
        "common_mistakes": "Confusing system entropy with universe entropy.",
        "practice_questions": [
            {"question": "What is the unit of S?", "answer": "J/K", "explanation": "Joules per Kelvin."}
        ],
        "quick_summary": ["dS_isolated >= 0", "Absolute zero: S -> 0"],
        "source_reference": "Core Physical Chemistry"
    }

    pdf_bytes = create_study_guide_pdf(
        guide_sections=[sample_section],
        student_name="Test Student",
        grade="College",
        curriculum="University / Degree Curriculum"
    )

    assert pdf_bytes is not None
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")
