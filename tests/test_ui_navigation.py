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
