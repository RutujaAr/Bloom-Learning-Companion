import pytest
from streamlit.testing.v1 import AppTest

def test_overview_start_diagnostic_button_navigation(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_nav.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    core.db.init_db()

    from pathlib import Path
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": "usr_test_nav_learner",
        "name": "Learner",
        "email": "learner@example.com",
        "auth_type": "local"
    }
    at.run()

    # Check that initial page is Overview
    assert at.session_state["nav_page"] == "Overview"
    assert at.session_state.get("sidebar_radio") == "Overview"

    # Locate the "Start Diagnostic Assessment" button on Overview
    start_btn = None
    for b in at.button:
        if "Start Diagnostic Assessment" in b.label:
            start_btn = b
            break

    assert start_btn is not None, "Button 'Start Diagnostic Assessment' must be rendered on Overview"

    # Click the button and simulate rerun
    start_btn.click().run()

    # Assert that navigation state and sidebar radio widget updated to 'Find my gaps'
    assert at.session_state["nav_page"] == "Find my gaps"
    assert at.session_state["sidebar_radio"] == "Find my gaps"


def test_diagnostic_submission_when_already_recorded_regression(tmp_path, monkeypatch):
    """
    Regression test for: NameError: name 'results' is not defined.
    When a diagnostic assessment has already been submitted (diagnostic_submitted = True),
    clicking Submit Diagnostic must show the already-submitted notice without re-running
    recording logic or crashing with NameError.
    """
    test_db = str(tmp_path / "test_diag_dup.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    core.db.init_db()

    from pathlib import Path
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": "usr_test_diag_dup_learner",
        "name": "Learner",
        "email": "learner@example.com",
        "auth_type": "local"
    }
    at.session_state["nav_page"] = "Find my gaps"
    at.session_state["sidebar_radio"] = "Find my gaps"
    at.session_state["diagnostic"] = {
        "stage": "Class 10",
        "curriculum": "CBSE (Verified 2024-25)",
        "subject": "Mathematics",
        "topic": "Algebra",
        "level": "Standard",
        "count": 1,
        "questions": [
            {
                "id": "q_test1",
                "prompt": "What is 2+2?",
                "options": ["3", "4", "5"],
                "answer": "4",
                "explanation": "2+2=4",
                "hint": "Basic addition",
                "mistake_type": "calculation"
            }
        ],
        "source": "AI-generated"
    }
    # Mark diagnostic as already submitted/recorded
    at.session_state["diagnostic_submitted"] = True
    at.session_state["diagnostic_result"] = {
        "results": [{"question": at.session_state["diagnostic"]["questions"][0], "answer": "4", "correct": True}],
        "score": 100,
        "analysis": {"summary": "Completed", "mistakes": []}
    }
    at.run()
    assert not at.exception, f"App crashed on initial load: {at.exception}"

    # Submit the form again when diagnostic_submitted is True
    submit_btn = None
    for b in at.button:
        if "Submit Diagnostic" in b.label:
            submit_btn = b
            break
    assert submit_btn is not None, "Submit Diagnostic button must be present"
    submit_btn.click().run()

    # Crucial assertion: Must not crash with NameError: name 'results' is not defined
    assert not at.exception, f"Regression exception occurred: {at.exception}"
    # Verify the already-submitted info notification is displayed
    assert any("already been submitted and recorded" in info.value for info in at.info)


def test_profile_panel_displays_clean_profile_without_any_id(tmp_path, monkeypatch):
    """
    Verify that user profile panel in sidebar displays only student's name, username,
    and stage/grade badge, and does NOT display any student ID, database row number,
    owner_id, account key, or internal identifier anywhere in the profile UI.
    """
    test_db = str(tmp_path / "test_profile_label.db")
    monkeypatch.setenv("BLOOM_DB_PATH", test_db)
    import core.db
    core.db.DB_PATH = test_db
    core.db.init_db()

    # Create account with test identifier
    student = core.db.create_user_account(
        username="rutuja",
        password_hash="dummy_hash",
        display_name="Rutuja",
        grade="College",
        owner_id="usr_rutuja_test"
    )

    from pathlib import Path
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": "usr_rutuja_test",
        "username": "rutuja",
        "name": "Rutuja",
        "email": "rutuja@example.edu",
        "auth_type": "account"
    }
    at.run()
    assert not at.exception

    # Find the sidebar markdown panel
    panel_markdowns = [m.value for m in at.sidebar.markdown]
    profile_panels = [m for m in panel_markdowns if "👤 Rutuja" in m]
    assert len(profile_panels) == 1, "Profile panel should be rendered in sidebar"
    panel_text = profile_panels[0]

    # Verify only name, grade badge, and username are displayed
    assert "👤 Rutuja" in panel_text
    assert "College" in panel_text
    assert "@rutuja" in panel_text

    # Verify NO user ID, row number, owner_id, or internal identifier is displayed
    assert "Student ID" not in panel_text
    assert f"ID: #{student['id']}" not in panel_text
    assert f"Student #{student['id']}" not in panel_text
    assert "usr_rutuja_test" not in panel_text
    assert "Account Key" not in panel_text

    # Verify Edit Profile section does not display Account Key or internal ID
    sidebar_captions = [c.value for c in at.sidebar.caption]
    assert not any("Account Key" in cap for cap in sidebar_captions)
    assert not any("usr_rutuja_test" in cap for cap in sidebar_captions)



