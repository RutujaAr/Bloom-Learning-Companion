import os
import logging
import pytest
import streamlit as st
from services.gemini_service import GeminiService
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import generate_recall_prompt


# ---------------------------------------------------------------------------
# 1. Default model is exactly 'gemini-3.5-flash-lite'
# ---------------------------------------------------------------------------
def test_default_model_is_gemini_35_flash_lite(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(st, "secrets", {})
    service = GeminiService()
    assert service.DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert service.model == "gemini-3.5-flash-lite"


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
    service = GeminiService(model="gemini-3.5-flash-lite")
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
    assert service.model == "gemini-3.5-flash-lite"
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
        type("NotFoundError", (Exception,), {"code": 404, "message": "models/gemini-3.5-flash-lite is not found for project 12345"})(),
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
    service = GeminiService(model="gemini-3.5-flash-lite")
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
    service = GeminiService(model="gemini-3.5-flash-lite")
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
    assert "model=gemini-3.5-flash-lite" in log_output
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
    custom_model = "gemini-3.5-flash-lite"
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


# ---------------------------------------------------------------------------
# 9. Diagnostic error reporting distinguishes HTTP 400, 401, 403, 404, and 429
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("http_code,api_message,expected_category", [
    (
        400,
        "INVALID_ARGUMENT: max_output_tokens must be positive",
        "invalid_request"
    ),
    (
        401,
        "API_KEY_INVALID: unauthenticated call",
        "authentication"
    ),
    (
        403,
        "PERMISSION_DENIED: caller does not have permission",
        "authentication"
    ),
    (
        404,
        "models/gemini-3.5-flash-lite is not found for API version v1beta",
        "model_not_found"
    ),
    (
        429,
        "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20",
        "quota"
    ),
])
def test_diagnostic_error_reporting_distinguishes_http_codes(monkeypatch, http_code, api_message, expected_category):
    """
    Ensure diagnostic error reporting extracts HTTP status code and Google's error detail,
    clearly distinguishing HTTP 400, 401, 403, 404, and 429 while preserving categories.
    """
    service = GeminiService(model="gemini-3.5-flash-lite")
    service.api_key = "test-api-key-safe"

    class MockHttpError(Exception):
        def __init__(self, code, message):
            super().__init__(f"{code} Error: {message}")
            self.code = code
            self.message = message

    class MockFailingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise MockHttpError(http_code, api_message)

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: MockFailingClient())

    ok, diag_msg = service.test_connection()
    assert ok is False

    # 1. Status code is accurately recorded and distinguished
    assert service._last_error_code == http_code
    assert service.last_metrics["last_error_code"] == http_code
    assert service.last_metrics["attempts"][0]["code"] == http_code
    assert f"HTTP {http_code}" in diag_msg

    # 2. Existing error categories are preserved
    assert service._last_error_category == expected_category
    assert service.last_metrics["last_error_category"] == expected_category
    assert f"category: {expected_category}" in diag_msg

    # 3. Google's error detail is recorded in diagnostic output
    assert service._last_error_detail is not None
    assert service.last_metrics["last_error_detail"] is not None
    assert "Detail:" in diag_msg


def test_diagnostic_secrets_redaction(monkeypatch):
    """
    Verify that API keys, authorization headers, and learner prompts are NEVER logged or displayed.
    """
    secret_key = "AQ.Ab8RN6I2W1y2spvHWJ6Jki7d5GWqzeGKPQd7uZl-acmP-1Ql5Q"
    service = GeminiService(model="gemini-3.5-flash-lite")
    service.api_key = secret_key

    class SecretLeakingError(Exception):
        def __init__(self):
            super().__init__(f"401 API_KEY_INVALID: key={secret_key} with Bearer secret_auth_token_999 for prompt secret_learner_prompt_text")
            self.code = 401
            self.message = f"API_KEY_INVALID: key={secret_key} with Authorization: Bearer secret_auth_token_999 for prompt secret_learner_prompt_text"

    class MockLeakingClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                raise SecretLeakingError()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: MockLeakingClient())

    ok, diag_msg = service.test_connection()
    assert ok is False

    # Status code is captured
    assert service._last_error_code == 401
    assert "HTTP 401" in diag_msg

    # Secrets and sensitive prompt text must be completely redacted
    assert secret_key not in diag_msg
    assert "secret_auth_token_999" not in diag_msg
    assert "secret_learner_prompt_text" not in diag_msg
    assert "[REDACTED" in diag_msg

    # Also check service attributes and metrics
    assert secret_key not in str(service._last_error_detail)
    assert "secret_auth_token_999" not in str(service._last_error_detail)
    assert "secret_learner_prompt_text" not in str(service._last_error_detail)
    assert secret_key not in str(service.last_metrics)


# ---------------------------------------------------------------------------
# 10. Diagnostic-question generation timeout (30s) vs connectivity check (10s)
# ---------------------------------------------------------------------------
def test_diagnostic_timeout_adjustment_for_diagnostic_operation_only(monkeypatch):
    """
    Verify smallest safe timeout adjustment for diagnostic question generation (30s)
    while keeping simple connectivity checks and standard operations short (10s).
    """
    monkeypatch.delenv("DIAGNOSTIC_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("GEMINI_TIMEOUT_MS", raising=False)
    monkeypatch.setattr(st, "secrets", {})

    service = GeminiService()
    assert service.diagnostic_timeout_ms == 30000
    assert service.connectivity_timeout_ms == 10000
    assert service.timeout_ms == 10000

    cfg = service.get_config_status()
    assert cfg["diagnostic_timeout_ms"] == 30000
    assert cfg["connectivity_timeout_ms"] == 10000
    assert cfg["timeout_ms"] == 10000

    captured_timeouts = []

    class MockInspectClient:
        def __init__(self, api_key=None, http_options=None):
            if http_options:
                captured_timeouts.append(http_options.timeout)

        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                class Response:
                    text = '[{"prompt": "What is 2+2?", "options": ["3", "4", "5", "6"], "answer": "4", "explanation": "2+2=4", "hint": "Basic math", "mistake_type": "calculation"}]'
                return Response()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", MockInspectClient)
    service.api_key = "dummy-safe-key"

    # 1. Simple connectivity check: MUST be kept short (10s = 10000ms)
    captured_timeouts.clear()
    ok, _ = service.test_connection()
    assert ok is True
    assert len(captured_timeouts) == 1
    assert captured_timeouts[0] == 10000

    # 2. General non-diagnostic request: standard default (10s = 10000ms)
    captured_timeouts.clear()
    service.generate_text("Explain cellular respiration in simple terms.")
    assert len(captured_timeouts) == 1
    assert captured_timeouts[0] == 10000

    # 3. Diagnostic-question generation prompt: dedicated safe budget (30s = 30000ms)
    captured_timeouts.clear()
    diag_prompt = (
        "Target Topic: Machine learning\n"
        "PEDAGOGICAL & EXAM STANDARDS:\n"
        "Number of Questions: 3\n"
        "Return ONLY a valid JSON array of objects with keys: prompt, options, answer, explanation, hint, mistake_type"
    )
    service.generate_text(diag_prompt)
    assert len(captured_timeouts) == 1
    assert captured_timeouts[0] == 30000

    # 4. Explicit generate_diagnostic method: dedicated safe budget (30s = 30000ms)
    captured_timeouts.clear()
    service.generate_diagnostic("Generate diagnostic items")
    assert len(captured_timeouts) == 1
    assert captured_timeouts[0] == 30000


def test_timeout_no_duplicate_retries_preserves_latency_and_quota(monkeypatch):
    """
    Verify that when an HTTP 504 / timeout occurs during Gemini requests:
    - Exactly 1 attempt is made (no duplicate retry)
    - Latency is bounded and does not multiply
    - Quota is preserved
    """
    service = GeminiService(timeout_ms=500, diagnostic_timeout_ms=500)
    service.api_key = "dummy-safe-key"

    call_count = 0

    class TimeoutSimClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise TimeoutError("504 DEADLINE_EXCEEDED: upstream timeout")

    import google.genai
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: TimeoutSimClient())

    ans, status = service.generate_text("Test prompt", timeout_ms=500)
    assert ans is None
    assert "took too long" in status.lower()

    # Crucial: Exactly 1 attempt made, never doubled!
    assert call_count == 1
    assert service.last_metrics["attempt_count"] == 1
    assert service.last_metrics["timeout_occurred"] is True
    assert service.last_metrics["last_error_category"] == "timeout"
    assert service.last_metrics["last_error_code"] == 504


def test_diagnostic_timeout_override_via_env(monkeypatch):
    """
    Verify that DIAGNOSTIC_TIMEOUT_MS can be customized via environment or secrets
    independently from GEMINI_TIMEOUT_MS.
    """
    monkeypatch.setenv("DIAGNOSTIC_TIMEOUT_MS", "35000")
    monkeypatch.setenv("GEMINI_TIMEOUT_MS", "15000")
    monkeypatch.setattr(st, "secrets", {})

    service = GeminiService()
    assert service.diagnostic_timeout_ms == 35000
    assert service.timeout_ms == 15000
    assert service.connectivity_timeout_ms == 10000

