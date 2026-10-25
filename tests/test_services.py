import pymupdf as fitz
import pytest
from services.pdf_service import extract_pdf_text, find_relevant_context
from services.gemini_service import GeminiService

def test_pdf_extraction_valid():
    # Create a small in-memory PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Bloom AI Learning Companion Test Page")
    pdf_bytes = doc.tobytes()
    doc.close()

    text, info = extract_pdf_text(pdf_bytes)
    assert "Bloom AI Learning Companion Test Page" in text
    assert "1 page(s)" in info

def test_pdf_extraction_corrupted():
    text, info = extract_pdf_text(b"not a valid pdf content")
    assert text == ""
    assert "could not be read" in info

def test_pdf_relevant_context_finder():
    full_text = "[Page 1]\nIntroduction to basic biology concepts.\n\n[Page 2]\nPhotosynthesis converts light into chemical energy using chlorophyll.\n\n[Page 3]\nCell division involves mitosis and meiosis."
    relevant = find_relevant_context(full_text, "photosynthesis and chlorophyll", max_chars=100)
    assert "Photosynthesis" in relevant

def test_gemini_service_unavailable_state():
    gs = GeminiService()
    assert gs.DEFAULT_MODEL == "gemini-3.8-flash"
    # Without an API key, available() must be False and generate_text must return informative notice
    if not gs.api_key:
        assert gs.available() is False
        text, msg = gs.generate_text("Hello")
        assert text is None
        assert "unavailable" in msg.lower()

def test_gemini_config_status_does_not_reveal_key():
    gs = GeminiService()
    status = gs.get_config_status()
    assert isinstance(status, dict)
    assert "configured" in status
    assert "source" in status
    assert "model" in status
    assert "status" in status
    # Ensure raw secret is never exposed in any dictionary value
    if gs.api_key:
        for val in status.values():
            assert gs.api_key not in str(val)

def test_gemini_placeholder_key_treated_as_unconfigured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your-gemini-api-key-here")
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {})
    gs = GeminiService()
    assert gs.available() is False
    assert gs.api_key is None
    cfg = gs.get_config_status()
    assert cfg["configured"] is False
