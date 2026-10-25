import os
import logging
import pytest
import streamlit as st
from services.gemini_service import GeminiService
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import generate_recall_prompt


# ---------------------------------------------------------------------------
# 1. Default model is exactly 'gemini-3.8-flash'
# ---------------------------------------------------------------------------
def test_default_model_is_gemini_38_flash(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(st, "secrets", {})
    service = GeminiService()
    assert service.DEFAULT_MODEL == "gemini-3.8-flash"
    assert service.model == "gemini-3.8-flash"


# ---------------------------------------------------------------------------
# 2. Explicit GEMINI_MODEL override is respected
# ---------------------------------------------------------------------------
def test_gemini_model_override_via_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "custom-experimental-model")
    monkeypatch.setattr(st, "secrets", {})
    service = GeminiService()
    assert service.model == "custom-experimental-model"


def test_gemini_model_override_via_secrets(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(st, "secrets", {"GEMINI_MODEL": "secrets-specified-model"})
    service = GeminiService()
    assert service.model == "secrets-specified-model"


def test_gemini_model_override_via_constructor():
    service = GeminiService(model="explicit-constructor-model")
    assert service.model == "explicit-constructor-model"


# ---------------------------------------------------------------------------
# 3. No silent fallback to gemini-2.5-flash occurs on failure
# ---------------------------------------------------------------------------
def test_no_silent_fallback_on_api_error(monkeypatch):
    service = GeminiService(model="gemini-3.8-flash")
    service.api_key = "dummy-test-key"

    class FailingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise RuntimeError("504 DEADLINE_EXCEEDED: upstream timeout")

    # Patch google.genai Client
    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FailingClient())

    ans, status = service.generate_text("Test prompt")
    # Must fail safely without switching self.model to another model
    assert ans is None
    assert service.model == "gemini-3.8-flash"
    assert "2.5" not in service.model
    assert "The response took too long" in status


# ---------------------------------------------------------------------------
# 4. Learner-facing errors are friendly and never expose raw API exceptions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("simulated_error,expected_substring", [
    (
        type("QuotaError", (Exception,), {"code": 429, "message": "Resource has been exhausted (e.g. check quota)."})(),
        "temporarily unable to generate a response"
    ),
    (
        type("AuthError", (Exception,), {"code": 401, "message": "API_KEY_INVALID: unauthenticated call"})(),
        "temporarily unavailable"
    ),
    (
        type("NotFoundError", (Exception,), {"code": 404, "message": "models/gemini-3.8-flash is not found for project 12345"})(),
        "temporarily unavailable"
    ),
    (
        type("TimeoutError", (Exception,), {"code": 504, "message": "DEADLINE_EXCEEDED: operation timed out after 120s"})(),
        "took too long"
    ),
    (
        type("BadRequestError", (Exception,), {"code": 400, "message": "INVALID_ARGUMENT: contents must not be empty"})(),
        "couldn't complete that request"
    ),
    (
        type("ServerError", (Exception,), {"code": 500, "message": "INTERNAL_SERVER_ERROR"})(),
        "having a little trouble responding"
    ),
])
def test_learner_facing_errors_friendly_and_sanitized(monkeypatch, simulated_error, expected_substring):
    service = GeminiService(model="gemini-3.8-flash")
    service.api_key = "dummy-test-key"

    class MockFailingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise simulated_error

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: MockFailingClient())

    raw, status = service.generate_text("Explain topic")
    assert raw is None

    # Verify learner-facing message is clean and friendly
    assert expected_substring in status

    # Verify no raw status codes, paths, or leakages exist in status
    assert "404" not in status
    assert "504" not in status
    assert "429" not in status
    assert "401" not in status
    assert "500" not in status
    assert "secrets.toml" not in status
    assert "GEMINI_API_KEY" not in status
    assert "Traceback" not in status


# ---------------------------------------------------------------------------
# 5. Diagnostic logging does not expose API keys or sensitive data
# ---------------------------------------------------------------------------
def test_diagnostic_logging_safe(caplog, monkeypatch):
    dummy_key = "dummy-sanitized-secret-key-xyz-99"
    service = GeminiService(model="gemini-3.8-flash")
    service.api_key = dummy_key

    class MockErrClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise ConnectionError("Connection refused by peer")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: MockErrClient())

    with caplog.at_level(logging.WARNING, logger="bloom.gemini"):
        service.generate_text("Super sensitive student test prompt")

    log_output = caplog.text
    # Log must record category and model
    assert "category=" in log_output
    assert "model=gemini-3.8-flash" in log_output
    # Log must NEVER contain secret key or student prompt
    assert dummy_key not in log_output
    assert "Super sensitive student test prompt" not in log_output


# ---------------------------------------------------------------------------
# 6. Timeouts and transient failures handled without indefinite retries
# ---------------------------------------------------------------------------
def test_timeout_and_retry_configuration(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_MS", "45000")
    monkeypatch.setattr(st, "secrets", {})
    service = GeminiService()
    assert service.timeout_ms == 45000

    captured_options = {}

    class InspectClient:
        def __init__(self, api_key=None, http_options=None):
            captured_options["http_options"] = http_options

        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                class Response:
                    text = "OK"
                return Response()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", InspectClient)
    service.api_key = "dummy-key"
    service.generate_text("Hi")

    opts = captured_options.get("http_options")
    assert opts is not None
    assert opts.timeout == 45000
    assert opts.retry_options is not None
    # Bounded SDK retry configuration; never retry 504/408 timeouts or auth/quota
    assert opts.retry_options.attempts <= 2
    assert 429 not in opts.retry_options.http_status_codes
    assert 401 not in opts.retry_options.http_status_codes
    assert 504 not in opts.retry_options.http_status_codes
    assert 408 not in opts.retry_options.http_status_codes


# ---------------------------------------------------------------------------
# 7. Existing fallback learning features still work when Gemini is unavailable
# ---------------------------------------------------------------------------
def test_offline_fallback_features_remain_functional():
    unconfigured_service = GeminiService()
    unconfigured_service.api_key = None

    # Diagnostic question generation recovers with curated bank
    questions, status = run_diagnostic(unconfigured_service, "Mathematics", "Algebra", "Standard", 3)
    assert len(questions) == 3
    assert "Built-in" in status

    # Paper pattern mistake analysis recovers with structured recommendations
    mistake_data = analyze_test(
        unconfigured_service,
        results=[],
        subject="Mathematics",
        topic="Quadratic Equations",
        manual_types=["Conceptual misunderstanding", "Calculation / careless error"],
        score=65
    )
    assert "mistakes" in mistake_data
    assert len(mistake_data["mistakes"]) == 2

    # Active recall prompt recovers with offline framework
    recall_chal = generate_recall_prompt(unconfigured_service, "Science", "Cell Division")
    assert "challenge" in recall_chal
    assert "model_answer" in recall_chal
    assert "offline fallback" in recall_chal["source"].lower()


# ---------------------------------------------------------------------------
# 8. Model labels in UI reflect actual configured model
# ---------------------------------------------------------------------------
def test_model_label_reflects_actual_configured_model(monkeypatch):
    custom_model = "gemini-3.8-flash"
    service = GeminiService(model=custom_model)
    service.api_key = "dummy-key"

    class EchoClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                class Resp:
                    text = "Generated explanation."
                return Resp()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: EchoClient())

    ans, status = service.explain_from_document("What is osmosis?", "Osmosis is water diffusion.")
    # Model ID must be safely sanitized from learner-facing status
    assert "AI-generated" in status
    assert custom_model not in status
    assert service.model == custom_model
